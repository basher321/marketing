"""Stock listing, low-stock detection, and on_hand adjustment (SPEC-BE-005)."""
from typing import Any

import structlog
from sqlalchemy import String, and_, column, func, table
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Query, Session

from app.core.audit import write_audit_log
from app.core.exceptions import AppError, NotFoundError
from app.models.inventory import Inventory, InventoryLocation, InventoryMovement
from app.models.product import Product

logger = structlog.get_logger(__name__)

# product_variants is read through a Core table of only the live columns used
# here: the ProductVariant ORM model is still misaligned with the live table
# (no tenant_id/attributes mapped; name/price columns that don't exist live).
_variants = table(
    "product_variants",
    column("id", String),
    column("tenant_id", String),
    column("product_id", String),
    column("sku", String),
    column("attributes", JSONB),
)


def _rows_query(db: Session, tenant_id: str) -> Query[Any]:
    # One joined query (no N+1), every join tenant-scoped (SPEC-BE-005
    # amendment, 2026-09-30): each inventory row with its variant SKU, product
    # title, variant attributes and location name. Order: product title, SKU,
    # location name (id as the final tie-breaker).
    return (
        db.query(
            Inventory,
            _variants.c.sku,
            Product.sku,
            Product.title,
            _variants.c.attributes,
            InventoryLocation.name,
        )
        .join(
            _variants,
            and_(_variants.c.id == Inventory.variant_id, _variants.c.tenant_id == tenant_id),
        )
        .join(Product, and_(Product.id == _variants.c.product_id, Product.tenant_id == tenant_id))
        .join(
            InventoryLocation,
            and_(
                InventoryLocation.id == Inventory.location_id,
                InventoryLocation.tenant_id == tenant_id,
            ),
        )
        .filter(Inventory.tenant_id == tenant_id)
        .order_by(Product.title, _variants.c.sku, InventoryLocation.name, Inventory.id)
    )


def _to_dict(row: Any) -> dict[str, Any]:
    record, variant_sku, product_sku, title, attributes, location_name = row
    # variant_label: the variant's attribute values joined with " / " (e.g.
    # "L / Blue"); None when the variant has no attributes.
    values = [str(v) for v in (attributes or {}).values() if v not in (None, "")]
    return {
        "id": record.id,
        "variant_id": record.variant_id,
        "location_id": record.location_id,
        "on_hand": record.on_hand,
        "committed": record.committed,
        "available": record.available,
        "reorder_point": record.reorder_point,
        # The variant's own SKU, falling back to the product SKU.
        "sku": variant_sku or product_sku,
        "product_title": title,
        "variant_label": " / ".join(values) or None,
        "location_name": location_name,
        # Same rule as GET /inventory/low-stock: the database-generated
        # `available` column against reorder_point, never on_hand - committed.
        "low_stock": record.available <= record.reorder_point,
    }


def list_inventory(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    return [_to_dict(r) for r in _rows_query(db, tenant_id).all()]


def low_stock_items(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    # Compares against the database-generated `available` column, never a
    # recomputed on_hand - committed.
    rows = _rows_query(db, tenant_id).filter(Inventory.available <= Inventory.reorder_point)
    return [_to_dict(r) for r in rows.all()]


def adjust_on_hand(
    db: Session,
    tenant_id: str,
    actor_user_id: str,
    inventory_id: str,
    new_on_hand: int,
    reason: str | None = None,
) -> dict[str, Any]:
    if new_on_hand < 0:
        raise AppError("on_hand cannot be negative.")

    record = (
        db.query(Inventory)
        .filter(Inventory.tenant_id == tenant_id, Inventory.id == inventory_id)
        .with_for_update()
        .first()
    )
    if record is None:
        # Same response whether the row is missing or belongs to another
        # tenant, so the caller can't probe for other tenants' rows.
        raise NotFoundError("Inventory record not found.")

    previous_on_hand = record.on_hand
    previous_available = record.available
    record.on_hand = new_on_hand
    record.updated_at = func.now()
    db.add(
        InventoryMovement(
            tenant_id=tenant_id,
            inventory_id=record.id,
            movement_type="adjustment",
            quantity=new_on_hand - previous_on_hand,
            reason=reason,
            performed_by=actor_user_id,
        )
    )
    # write_audit_log commits, so the on_hand change, the movement row, and the
    # audit row land in a single commit.
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="inventory.adjust",
        resource_type="inventory",
        resource_id=record.id,
        # Live uuid columns load as uuid.UUID, which the jsonb metadata can't
        # serialize: stringify them (every adjust failed before, 2026-09-30).
        metadata={
            "variant_id": str(record.variant_id),
            "location_id": str(record.location_id),
            "previous_on_hand": previous_on_hand,
            "new_on_hand": new_on_hand,
            "reason": reason,
        },
    )
    db.refresh(record)
    logger.info(
        "inventory_adjusted",
        tenant_id=tenant_id,
        inventory_id=record.id,
        previous_on_hand=previous_on_hand,
        new_on_hand=new_on_hand,
    )
    result = _to_dict(_rows_query(db, tenant_id).filter(Inventory.id == record.id).one())
    _fire_inventory_low(db, tenant_id, record, previous_available, result)
    return result


def product_sales_30d(db: Session, tenant_id: str, product_id: str) -> tuple[int, int]:
    """(units, revenue cents) sold for a product in the last 30 days (SPEC-BE-060):
    order_items of this tenant's orders placed in the last 30 days, status not
    cancelled/refunded, reached via order_items.variant_id -> product_variants."""
    from sqlalchemy import text

    row = db.execute(
        text(
            "SELECT COALESCE(SUM(oi.quantity), 0), COALESCE(SUM(oi.line_total_cents), 0) "
            "FROM order_items oi JOIN orders o ON o.id = oi.order_id AND o.tenant_id = :t "
            "JOIN product_variants v ON v.id = oi.variant_id AND v.tenant_id = :t "
            "WHERE oi.tenant_id = :t AND v.product_id = :p "
            "AND o.placed_at >= now() - interval '30 days' "
            "AND o.status NOT IN ('cancelled', 'refunded')"
        ),
        {"t": tenant_id, "p": product_id},
    ).one()
    return int(row[0]), int(row[1])


def _fire_inventory_low(
    db: Session, tenant_id: str, record: Inventory, previous_available: int | None, row: dict[str, Any]
) -> None:
    # Live trigger inventory_low (SPEC-BE-060). The dispatcher decides per
    # workflow whether the change crossed its threshold; here we only build the
    # context. Runs after the adjust committed.
    from app.workflow_engine.dispatcher import fire

    product_id = db.execute(
        _variants.select().with_only_columns(_variants.c.product_id).where(
            _variants.c.id == record.variant_id, _variants.c.tenant_id == tenant_id
        )
    ).scalar()
    if product_id is None or previous_available is None:
        return
    units, revenue = product_sales_30d(db, tenant_id, str(product_id))
    fire(
        db,
        tenant_id,
        "inventory_low",
        {
            "_previous_available": previous_available,
            "product": {
                "id": str(product_id),
                "sku": row["sku"],
                "title": row["product_title"],
                "units_sold_30d": units,
                "revenue_30d_cents": revenue,
            },
            "inventory": {
                "available": row["available"],
                "committed": row["committed"],
                "location": row["location_name"],
            },
        },
    )
