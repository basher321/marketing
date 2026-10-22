"""Business type, hand-made products, categories and payments (SPEC-BE-111).

- The business type is stored in `tenants.settings.ecommerce`. A suggestion is
  made only from evidence (a connected store, shipping zones, stock rows, product
  weights) and is never saved as confirmed: only PUT /ecommerce/config confirms.
- Product fields a type doesn't use are refused (422), so data never mixes.
- Stock is set through inventory_service.adjust_on_hand, so every change is an
  audited inventory movement (SPEC-BE-005).
"""
import json
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.audit import write_audit_log
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.ecommerce import CategoryCreate, CategoryPatch, ProductCreate, ProductPatch
from app.utils import business_types as bt

logger = structlog.get_logger(__name__)


def _uuid_or_404(value: str | None, what: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except ValueError:
        raise NotFoundError(f"{what} not found.") from None


def _tenant(db: Session, tenant_id: str) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundError("Company not found.")
    return tenant


def _stored(tenant: Tenant) -> dict[str, Any]:
    return dict((tenant.settings or {}).get("ecommerce") or {})


def business_type(db: Session, tenant_id: str) -> str:
    stored = _stored(_tenant(db, tenant_id))
    value = stored.get("business_type")
    return value if value in bt.TYPES else bt.DEFAULT_TYPE


# ---------------------------------------------------------------------------
# Suggestion (FR2) and config (FR3/FR4)
# ---------------------------------------------------------------------------
def suggest(db: Session, tenant_id: str) -> dict[str, Any]:
    p = {"t": tenant_id}
    stores = [r[0] for r in db.execute(text(
        "SELECT DISTINCT provider::text FROM integrations WHERE tenant_id = :t "
        "AND provider IN ('shopify', 'woocommerce') AND status = 'connected'"), p)]
    zones = db.execute(text("SELECT count(*) FROM shipping_zones WHERE tenant_id = :t"), p).scalar() or 0
    stock_rows = db.execute(text("SELECT count(*) FROM inventory WHERE tenant_id = :t"), p).scalar() or 0
    weighed = db.execute(text(
        "SELECT count(*) FROM products WHERE tenant_id = :t AND deleted_at IS NULL AND weight_grams > 0"), p).scalar() or 0
    names = {"shopify": "Shopify", "woocommerce": "WooCommerce"}
    reasons: list[str] = [f"A connected {names[s]} store." for s in stores]
    if zones:
        reasons.append(f"{zones} shipping zone(s) are set up.")
    if reasons:
        if stock_rows:
            reasons.append("Products have stock levels.")
        return {"type": "online_retail", "reasons": reasons}
    if stock_rows or weighed:
        reasons = []
        if stock_rows:
            reasons.append("Products have stock levels.")
        if weighed:
            reasons.append(f"{weighed} product(s) have a weight.")
        reasons.append("No shipping is set up, so it looks like a shop customers visit.")
        return {"type": "physical_store", "reasons": reasons}
    return {"type": None, "reasons": []}


def get_config(db: Session, tenant_id: str) -> dict[str, Any]:
    tenant = _tenant(db, tenant_id)
    stored = _stored(tenant)
    confirmed = bool(stored.get("confirmed")) and stored.get("business_type") in bt.TYPES
    current = stored["business_type"] if confirmed else bt.DEFAULT_TYPE
    at = stored.get("confirmed_at")
    return {
        "business_type": current,
        "confirmed": confirmed,
        "confirmed_at": datetime.fromisoformat(at) if confirmed and at else None,
        "suggestion": suggest(db, tenant_id),
        "tabs": bt.tabs(current),
        "product_fields": bt.product_fields(current),
        "order_fields": bt.order_fields(current),
        "types": [{"key": k, "label": v["label"], "description": v["description"]} for k, v in bt.TYPES.items()],
    }


def save_config(db: Session, tenant_id: str, actor: User, business_type_key: str) -> dict[str, Any]:
    tenant = _tenant(db, tenant_id)
    before = _stored(tenant).get("business_type")
    settings = dict(tenant.settings or {})
    settings["ecommerce"] = {
        "business_type": business_type_key, "confirmed": True, "confirmed_by": str(actor.id),
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
    }
    tenant.settings = settings
    flag_modified(tenant, "settings")
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=str(actor.id), action="ecommerce.business_type_set",
                    resource_type="tenant", resource_id=tenant_id,
                    metadata={"from": before, "to": business_type_key})
    return get_config(db, tenant_id)


# ---------------------------------------------------------------------------
# Products by hand (FR5)
# ---------------------------------------------------------------------------
def _cents(value: Decimal | None) -> int | None:
    return None if value is None else int(value * 100)


def _major(cents: int | None) -> float | None:
    return None if cents is None else float(Decimal(cents) / 100)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80] or "product"


def _unique_slug(db: Session, tenant_id: str, base: str, exclude: str | None = None) -> str:
    slug, n = base, 1
    while db.execute(text("SELECT 1 FROM products WHERE tenant_id = :t AND slug = :s AND (CAST(:x AS uuid) IS NULL OR id <> CAST(:x AS uuid))"),
                     {"t": tenant_id, "s": slug, "x": exclude}).first():
        n += 1
        slug = f"{base}-{n}"
    return slug


def _check_fields(btype: str, data: dict[str, Any], creating: bool) -> None:
    spec = bt.TYPES[btype]
    for field, value in data.items():
        if value is None or field not in bt.FIELD_LABELS:
            continue
        if field not in spec["fields"]:
            raise AppError(bt.unused_message(btype, field), 422)
    if creating:
        missing = [bt.FIELD_LABELS[f][0] for f in spec["required"] if data.get(f) in (None, "")]
        if missing:
            raise AppError(f"Required: {', '.join(missing)}.", 422)
    if data.get("compare_at_price") is not None and data.get("price") is not None \
            and data["compare_at_price"] <= data["price"]:
        raise AppError("The compare-at price must be higher than the price.", 422)


def _category(db: Session, tenant_id: str, category_id: str | None) -> str | None:
    if not category_id:
        return None
    cid = _uuid_or_404(category_id, "Category")
    if not db.execute(text("SELECT 1 FROM product_categories WHERE tenant_id = :t AND id = :c"),
                      {"t": tenant_id, "c": cid}).first():
        raise NotFoundError("Category not found.")
    return cid


def _images(db: Session, tenant_id: str, media_ids: list[str] | None, title: str) -> list[dict[str, Any]] | None:
    if media_ids is None:
        return None
    from app.services import media_service

    assets = media_service.media_rows(db, tenant_id, [str(m) for m in media_ids], kinds=("image",)) if media_ids else []
    if len(assets) != len(set(media_ids)):
        raise AppError("Some images aren't in your media library.", 422)
    return [{"media_id": str(a.id), "url": media_service.signed_url(str(a.id), 24 * 365), "alt": title} for a in assets]


def _default_variant(db: Session, tenant_id: str, product_id: str) -> Any:
    return db.execute(text(
        "SELECT id, sku FROM product_variants WHERE tenant_id = :t AND product_id = :p "
        "ORDER BY is_default DESC, display_order, created_at LIMIT 1"), {"t": tenant_id, "p": product_id}).first()


def _default_location(db: Session, tenant_id: str) -> str:
    row = db.execute(text(
        "SELECT id FROM inventory_locations WHERE tenant_id = :t AND active ORDER BY is_default DESC, created_at LIMIT 1"),
        {"t": tenant_id}).scalar()
    if row:
        return str(row)
    return str(db.execute(text(
        "INSERT INTO inventory_locations (tenant_id, name, code, is_default) VALUES (:t, 'Main location', 'MAIN', true) "
        "ON CONFLICT (tenant_id, code) DO UPDATE SET active = true RETURNING id"), {"t": tenant_id}).scalar_one())


def _set_stock(db: Session, tenant_id: str, actor: User, variant_id: str, stock: int) -> None:
    from app.services import inventory_service

    location = _default_location(db, tenant_id)
    inv = db.execute(text(
        "SELECT id FROM inventory WHERE tenant_id = :t AND variant_id = :v AND location_id = :l"),
        {"t": tenant_id, "v": variant_id, "l": location}).scalar()
    if inv is None:
        inv = db.execute(text(
            "INSERT INTO inventory (tenant_id, variant_id, location_id, on_hand) VALUES (:t, :v, :l, 0) RETURNING id"),
            {"t": tenant_id, "v": variant_id, "l": location}).scalar_one()
    inventory_service.adjust_on_hand(db, tenant_id, str(actor.id), str(inv), stock, "Set on the product form")


def _sku_taken(db: Session, tenant_id: str, sku: str, exclude: str | None = None) -> bool:
    return db.execute(text(
        "SELECT 1 FROM products WHERE tenant_id = :t AND lower(sku) = lower(:s) "
        "AND (CAST(:x AS uuid) IS NULL OR id <> CAST(:x AS uuid)) "
        "UNION SELECT 1 FROM product_variants WHERE tenant_id = :t AND lower(sku) = lower(:s) "
        "AND (CAST(:x AS uuid) IS NULL OR product_id <> CAST(:x AS uuid))"),
        {"t": tenant_id, "s": sku, "x": exclude}).first() is not None


def create_product(db: Session, tenant_id: str, actor: User, payload: ProductCreate) -> dict[str, Any]:
    btype = business_type(db, tenant_id)
    data = payload.model_dump()
    _check_fields(btype, data, creating=True)
    sku = str(payload.sku)
    if _sku_taken(db, tenant_id, sku):
        raise ConflictError(f"A product with SKU {sku} already exists.")
    tenant = _tenant(db, tenant_id)
    currency = (tenant.currency or "USD").strip()
    title = str(payload.title)
    images = _images(db, tenant_id, payload.media_ids, title) or []
    # Catalogue products may have no price ("price on request"): the column is NOT NULL,
    # so 0 is stored and the flag says it is on request.
    price_cents = _cents(payload.price)
    metadata: dict[str, Any] = {"created_from": "product_form"}
    if price_cents is None:
        metadata["price_on_request"] = True
    if payload.delivery_note:
        metadata["delivery_note"] = payload.delivery_note
    product_id = str(db.execute(text(
        "INSERT INTO products (tenant_id, sku, title, slug, description, category_id, status, default_price_cents, "
        "compare_at_price_cents, cost_cents, currency, weight_grams, images, metadata, created_by, updated_by) "
        "VALUES (:t, :sku, :title, :slug, :descr, :cat, CAST(:st AS product_status), :price, :compare, :cost, :cur, "
        ":weight, CAST(:images AS jsonb), CAST(:meta AS jsonb), :actor, :actor) RETURNING id"),
        {"t": tenant_id, "sku": sku, "title": title, "slug": _unique_slug(db, tenant_id, _slugify(title)),
         "descr": payload.description, "cat": _category(db, tenant_id, payload.category_id),
         "st": payload.status or "draft", "price": price_cents or 0, "compare": _cents(payload.compare_at_price),
         "cost": _cents(payload.cost), "cur": currency, "weight": payload.weight_grams, "images": json.dumps(images),
         "meta": json.dumps(metadata), "actor": str(actor.id)}).scalar_one())
    # One default variant so orders and stock have something to point at.
    variant_id = str(db.execute(text(
        "INSERT INTO product_variants (tenant_id, product_id, sku, price_cents, compare_at_price_cents, cost_cents, "
        "weight_grams, is_default) VALUES (:t, :p, :sku, :price, :compare, :cost, :weight, true) RETURNING id"),
        {"t": tenant_id, "p": product_id, "sku": sku, "price": price_cents or 0,
         "compare": _cents(payload.compare_at_price), "cost": _cents(payload.cost),
         "weight": payload.weight_grams}).scalar_one())
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=str(actor.id), action="product.created",
                    resource_type="product", resource_id=product_id, metadata={"sku": sku, "business_type": btype})
    if payload.stock is not None:
        _set_stock(db, tenant_id, actor, variant_id, payload.stock)
    logger.info("product.created", tenant_id=tenant_id, product_id=product_id)
    return get_product(db, tenant_id, product_id)


def _product_row(db: Session, tenant_id: str, product_id: str, lock: bool = False) -> Any:
    pid = _uuid_or_404(product_id, "Product")
    row = db.execute(text(
        "SELECT * FROM products WHERE tenant_id = :t AND id = :p AND deleted_at IS NULL" + (" FOR UPDATE" if lock else "")),
        {"t": tenant_id, "p": pid}).mappings().first()
    if row is None:
        raise NotFoundError("Product not found.")
    return row


def update_product(db: Session, tenant_id: str, actor: User, product_id: str, payload: ProductPatch) -> dict[str, Any]:
    btype = business_type(db, tenant_id)
    row = _product_row(db, tenant_id, product_id, lock=True)
    changes = payload.model_dump(exclude_unset=True)
    _check_fields(btype, changes, creating=False)
    price = changes["price"] if "price" in changes else (_major(row["default_price_cents"]) if not (row["metadata"] or {}).get("price_on_request") else None)
    compare = changes.get("compare_at_price", _major(row["compare_at_price_cents"]))
    if compare is not None and price is not None and Decimal(str(compare)) <= Decimal(str(price)):
        raise AppError("The compare-at price must be higher than the price.", 422)
    for f in bt.TYPES[btype]["required"]:
        if f in changes and changes[f] in (None, ""):
            raise AppError(f"{bt.FIELD_LABELS[f][0]} is required.", 422)
    if "sku" in changes and changes["sku"] != row["sku"] and _sku_taken(db, tenant_id, changes["sku"], str(row["id"])):
        raise ConflictError(f"A product with SKU {changes['sku']} already exists.")
    sets: dict[str, Any] = {}
    meta = dict(row["metadata"] or {})
    if "title" in changes:
        sets["title"] = changes["title"]
    if "description" in changes:
        sets["description"] = changes["description"]
    if "sku" in changes:
        sets["sku"] = changes["sku"]
    if "category_id" in changes:
        sets["category_id"] = _category(db, tenant_id, changes["category_id"])
    if "price" in changes:
        sets["default_price_cents"] = _cents(changes["price"]) or 0
        if changes["price"] is None:
            meta["price_on_request"] = True
        else:
            meta.pop("price_on_request", None)
    if "compare_at_price" in changes:
        sets["compare_at_price_cents"] = _cents(changes["compare_at_price"])
    if "cost" in changes:
        sets["cost_cents"] = _cents(changes["cost"])
    if "weight_grams" in changes:
        sets["weight_grams"] = changes["weight_grams"]
    if changes.get("status"):
        sets["status"] = changes["status"]
    if "delivery_note" in changes:
        meta["delivery_note"] = changes["delivery_note"]
    if "media_ids" in changes:
        sets["images"] = json.dumps(_images(db, tenant_id, changes["media_ids"] or [], changes.get("title") or row["title"]))
    sets["metadata"] = json.dumps(meta)
    assignments = ", ".join(
        f"{k} = CAST(:{k} AS jsonb)" if k in ("images", "metadata") else
        (f"{k} = CAST(:{k} AS product_status)" if k == "status" else f"{k} = :{k}") for k in sets)
    db.execute(text(f"UPDATE products SET {assignments}, updated_by = :actor, updated_at = now() WHERE id = :id"),
               {**sets, "actor": str(actor.id), "id": str(row["id"])})
    # The default variant follows the product's price, cost, weight (and SKU when it matched).
    variant = _default_variant(db, tenant_id, str(row["id"]))
    stock_variant = str(variant.id) if variant is not None else None
    if variant is not None:
        mapping = {"price_cents": "default_price_cents", "compare_at_price_cents": "compare_at_price_cents",
                   "cost_cents": "cost_cents", "weight_grams": "weight_grams"}
        vsets = {vk: sets[pk] for vk, pk in mapping.items() if pk in sets}
        if "sku" in sets and variant.sku == row["sku"]:
            vsets["sku"] = sets["sku"]
        if vsets:
            db.execute(text("UPDATE product_variants SET " + ", ".join(f"{k} = :{k}" for k in vsets)
                            + ", updated_at = now() WHERE id = :v"), {**vsets, "v": str(variant.id)})
    elif changes.get("stock") is not None:
        stock_variant = str(db.execute(text(
            "INSERT INTO product_variants (tenant_id, product_id, sku, price_cents, cost_cents, is_default) "
            "VALUES (:t, :p, :sku, :price, :cost, true) RETURNING id"),
            {"t": tenant_id, "p": str(row["id"]), "sku": sets.get("sku", row["sku"]),
             "price": sets.get("default_price_cents", row["default_price_cents"]),
             "cost": sets.get("cost_cents", row["cost_cents"])}).scalar_one())
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=str(actor.id), action="product.updated",
                    resource_type="product", resource_id=str(row["id"]), metadata={"fields": sorted(changes)})
    if changes.get("stock") is not None and stock_variant is not None:
        _set_stock(db, tenant_id, actor, stock_variant, int(changes["stock"]))
    return get_product(db, tenant_id, str(row["id"]))


def archive_product(db: Session, tenant_id: str, actor: User, product_id: str) -> None:
    row = _product_row(db, tenant_id, product_id, lock=True)
    db.execute(text("UPDATE products SET status = 'archived', updated_by = :a, updated_at = now() WHERE id = :p"),
               {"a": str(actor.id), "p": str(row["id"])})
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=str(actor.id), action="product.archived",
                    resource_type="product", resource_id=str(row["id"]), metadata={"sku": row["sku"]})


def get_product(db: Session, tenant_id: str, product_id: str) -> dict[str, Any]:
    row = _product_row(db, tenant_id, product_id)
    category = db.execute(text("SELECT name FROM product_categories WHERE tenant_id = :t AND id = :c"),
                          {"t": tenant_id, "c": row["category_id"]}).scalar() if row["category_id"] else None
    stock = db.execute(text(
        "SELECT sum(i.on_hand) FROM inventory i JOIN product_variants v ON v.id = i.variant_id AND v.tenant_id = :t "
        "WHERE i.tenant_id = :t AND v.product_id = :p"), {"t": tenant_id, "p": str(row["id"])}).scalar()
    meta = row["metadata"] or {}
    on_request = bool(meta.get("price_on_request"))
    return {
        "id": str(row["id"]), "sku": row["sku"], "title": row["title"], "description": row["description"],
        "category_id": str(row["category_id"]) if row["category_id"] else None, "category": category,
        "price": None if on_request else _major(row["default_price_cents"]), "price_on_request": on_request,
        "compare_at_price": _major(row["compare_at_price_cents"]), "cost": _major(row["cost_cents"]),
        "currency": str(row["currency"]).strip(), "stock": int(stock) if stock is not None else None,
        "weight_grams": row["weight_grams"],
        "images": [i for i in (row["images"] or []) if isinstance(i, dict)],
        "status": row["status"], "delivery_note": meta.get("delivery_note"),
        "updated_at": row["updated_at"].astimezone(timezone.utc),
    }


# ---------------------------------------------------------------------------
# Categories (FR6), over the live product_categories table
# ---------------------------------------------------------------------------
def _cat_unique_slug(db: Session, tenant_id: str, base: str, exclude: str | None = None) -> str:
    slug, n = base, 1
    while db.execute(text("SELECT 1 FROM product_categories WHERE tenant_id = :t AND slug = :s "
                          "AND (CAST(:x AS uuid) IS NULL OR id <> CAST(:x AS uuid))"),
                     {"t": tenant_id, "s": slug, "x": exclude}).first():
        n += 1
        slug = f"{base}-{n}"
    return slug


def list_categories(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    rows = db.execute(text(
        "SELECT c.id, c.name, c.slug, c.description, c.parent_id, "
        "(SELECT count(*) FROM products p WHERE p.tenant_id = :t AND p.category_id = c.id AND p.deleted_at IS NULL "
        " AND p.status <> 'archived') AS n "
        "FROM product_categories c WHERE c.tenant_id = :t ORDER BY c.display_order, lower(c.name)"), {"t": tenant_id})
    return [{"id": str(r.id), "name": r.name, "slug": r.slug, "description": r.description,
             "parent_id": str(r.parent_id) if r.parent_id else None, "product_count": int(r.n)} for r in rows]


def _name_taken(db: Session, tenant_id: str, name: str, exclude: str | None = None) -> bool:
    return db.execute(text("SELECT 1 FROM product_categories WHERE tenant_id = :t AND lower(name) = lower(:n) "
                           "AND (CAST(:x AS uuid) IS NULL OR id <> CAST(:x AS uuid))"),
                      {"t": tenant_id, "n": name, "x": exclude}).first() is not None


def create_category(db: Session, tenant_id: str, actor: User, payload: CategoryCreate) -> dict[str, Any]:
    if _name_taken(db, tenant_id, payload.name):
        raise ConflictError(f"A category called {payload.name} already exists.")
    parent = _category(db, tenant_id, payload.parent_id)
    cid = str(db.execute(text(
        "INSERT INTO product_categories (tenant_id, parent_id, name, slug, description) "
        "VALUES (:t, :p, :n, :s, :d) RETURNING id"),
        {"t": tenant_id, "p": parent, "n": payload.name, "s": _cat_unique_slug(db, tenant_id, _slugify(payload.name)),
         "d": payload.description}).scalar_one())
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=str(actor.id), action="category.created",
                    resource_type="product_category", resource_id=cid, metadata={"name": payload.name})
    return next(c for c in list_categories(db, tenant_id) if c["id"] == cid)


def update_category(db: Session, tenant_id: str, actor: User, category_id: str, payload: CategoryPatch) -> dict[str, Any]:
    cid = _category(db, tenant_id, category_id)
    assert cid is not None
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("name"):
        if _name_taken(db, tenant_id, changes["name"], cid):
            raise ConflictError(f"A category called {changes['name']} already exists.")
        db.execute(text("UPDATE product_categories SET name = :n, slug = :s, updated_at = now() WHERE id = :c"),
                   {"n": changes["name"], "s": _cat_unique_slug(db, tenant_id, _slugify(changes["name"]), cid), "c": cid})
    if "description" in changes:
        db.execute(text("UPDATE product_categories SET description = :d, updated_at = now() WHERE id = :c"),
                   {"d": changes["description"], "c": cid})
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=str(actor.id), action="category.updated",
                    resource_type="product_category", resource_id=cid, metadata={"fields": sorted(changes)})
    return next(c for c in list_categories(db, tenant_id) if c["id"] == cid)


# ---------------------------------------------------------------------------
# Payments (FR7)
# ---------------------------------------------------------------------------
def list_payments(db: Session, tenant_id: str, status: str | None, days: int | None, limit: int,
                  offset: int) -> dict[str, Any]:
    where = "o.tenant_id = :t"
    p: dict[str, Any] = {"t": tenant_id, "lim": limit, "off": offset}
    if status:
        where += " AND coalesce(o.payment_status, 'unpaid') = :s"
        p["s"] = status
    if days:
        where += " AND o.placed_at >= now() - make_interval(days => :d)"
        p["d"] = days
    total = db.execute(text(f"SELECT count(*) FROM orders o WHERE {where}"), p).scalar() or 0
    sums = {r.s: float(Decimal(r.cents or 0) / 100) for r in db.execute(text(
        f"SELECT coalesce(o.payment_status, 'unpaid') AS s, sum(o.total_cents) AS cents FROM orders o WHERE {where} "
        "GROUP BY 1"), p)}
    rows = db.execute(text(
        "SELECT o.id, o.order_number, o.placed_at, o.status::text AS status, o.payment_method, o.payment_status, "
        "o.metadata->'payment'->>'reference' AS reference, o.total_cents, o.currency, "
        "nullif(trim(concat_ws(' ', c.first_name, c.last_name)), '') AS name, c.phone "
        f"FROM orders o LEFT JOIN customers c ON c.id = o.customer_id AND c.tenant_id = :t WHERE {where} "
        "ORDER BY o.placed_at DESC LIMIT :lim OFFSET :off"), p)
    return {"total": int(total), "sums": sums, "items": [{
        "order_id": str(r.id), "order_number": r.order_number, "customer_name": r.name or r.phone,
        "placed_at": r.placed_at.astimezone(timezone.utc), "status": r.status, "payment_method": r.payment_method,
        "payment_status": r.payment_status or "unpaid", "reference": r.reference,
        "total": float(Decimal(r.total_cents) / 100), "currency": str(r.currency).strip(),
    } for r in rows]}


def set_payment(db: Session, tenant_id: str, actor: User, order_id: str, payment_status: str, method: str | None,
                reference: str | None) -> None:
    from app.services import order_service

    order = order_service.get_order(db, tenant_id, order_id, lock=True)
    before = order.payment_status
    order.payment_status = payment_status
    if method:
        order.payment_method = method
    meta = dict(order.extra_metadata or {})
    meta["payment"] = {"reference": reference, "set_by": str(actor.id),
                       "set_at": datetime.now(timezone.utc).isoformat(), "from": before}
    order.extra_metadata = meta
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=str(actor.id), action="order.payment_updated",
                    resource_type="order", resource_id=str(order.id),
                    metadata={"from": before, "to": payment_status, "reference": reference})
