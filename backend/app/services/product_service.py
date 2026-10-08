"""Product catalog list (SPEC-BE-008)."""
from datetime import timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.inventory import Inventory
from app.models.product import Product, ProductVariant

logger = structlog.get_logger(__name__)


def list_products(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    products = (
        db.query(Product)
        .filter(Product.tenant_id == tenant_id, Product.deleted_at.is_(None))
        .order_by(Product.updated_at.desc(), Product.id)
        .all()
    )
    # Stock per product in one grouped query: inventory rows reached via product_variants,
    # tenant-scoped on inventory.tenant_id and restricted to this tenant's product ids.
    # Only product_variants.id/product_id are referenced (the ProductVariant model maps
    # other columns the live table lacks).
    stock: dict[str, tuple[int, bool]] = {}
    if products:
        rows = db.execute(
            select(
                ProductVariant.product_id,
                func.sum(Inventory.available),
                func.bool_or(Inventory.available <= Inventory.reorder_point),
            )
            .join(Inventory, Inventory.variant_id == ProductVariant.id)
            .where(
                Inventory.tenant_id == tenant_id,
                ProductVariant.product_id.in_([p.id for p in products]),
            )
            .group_by(ProductVariant.product_id)
        ).all()
        stock = {str(pid): (int(total or 0), bool(low)) for pid, total, low in rows}
    logger.info("products_listed", tenant_id=tenant_id, count=len(products))
    return [
        {
            "id": str(p.id),
            "sku": p.sku,
            "title": p.title,
            # Cents -> major units via Decimal so e.g. 79000 becomes exactly 790.0.
            "price": float(Decimal(p.default_price_cents) / 100),
            "currency": p.currency,
            "channels": list(p.channels or []),
            "status": p.status,
            # Normalized to UTC; Postgres returns TIMESTAMPTZ in the server's zone.
            "updated_at": p.updated_at.astimezone(timezone.utc),
            "stock": stock[str(p.id)][0] if str(p.id) in stock else None,
            "low_stock": stock[str(p.id)][1] if str(p.id) in stock else False,
        }
        for p in products
    ]


# Command Chat `update_product` action (SPEC-BE-059): status and/or title for the
# tenant's products matched by SKU. Unknown SKUs -> 404 naming them; nothing is
# changed unless every SKU matches. One audit row per product.
def update_products(
    db: Session,
    tenant_id: str,
    actor_user_id: str,
    skus: list[str],
    status: str | None = None,
    title: str | None = None,
) -> list[dict[str, Any]]:
    from app.core.audit import write_audit_log
    from app.core.exceptions import NotFoundError

    products = (
        db.query(Product)
        .filter(Product.tenant_id == tenant_id, Product.sku.in_(skus), Product.deleted_at.is_(None))
        .with_for_update()
        .all()
    )
    unknown = sorted(set(skus) - {p.sku for p in products})
    if unknown:
        raise NotFoundError(f"Unknown SKU(s): {', '.join(unknown)}.")
    changed = []
    for product in products:
        before = {"status": product.status, "title": product.title}
        if status is not None:
            product.status = status
        if title is not None and len(products) == 1:
            product.title = title
        changed.append({"id": str(product.id), "sku": product.sku, "status": product.status, "title": product.title})
        write_audit_log(
            db,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="product.update",
            resource_type="product",
            resource_id=str(product.id),
            metadata={"sku": product.sku, "before": before, "after": {"status": product.status, "title": product.title}},
        )
    logger.info("products_updated", tenant_id=tenant_id, count=len(changed))
    return changed
