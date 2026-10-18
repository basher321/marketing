"""Product catalog list (SPEC-BE-008)."""
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import func, select, text
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


# ---------------------------------------------------------------------------
# AI product listings and website publishing (SPEC-BE-098)
# ---------------------------------------------------------------------------
_HTML_TAG = re.compile(r"</?([a-zA-Z0-9]+)(\s[^>]*)?>")
_ALLOWED_TAGS = {"p", "ul", "li", "strong", "em", "br"}


def _clean_html(html: str) -> str:
    """Keeps only <p>, <ul>, <li>, <strong>, <em>, <br> (no attributes); text
    between tags is escaped; scripts and styles are dropped with their content."""
    import html as htmllib

    source = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", html or "")
    out: list[str] = []
    pos = 0
    for m in _HTML_TAG.finditer(source):
        out.append(htmllib.escape(htmllib.unescape(source[pos:m.start()]), quote=False))
        name = m.group(1).lower()
        if name in _ALLOWED_TAGS:
            out.append(f"</{name}>" if m.group(0).startswith("</") else f"<{name}>")
        pos = m.end()
    out.append(htmllib.escape(htmllib.unescape(source[pos:]), quote=False))
    return "".join(out).strip()


def _unsupported_numbers(text_value: str, allowed: set[Decimal]) -> bool:
    from app.ai.command_guard import numbers_in

    return any(n not in allowed for n in numbers_in(text_value))


def _strip_numbers(text_value: str, allowed: set[Decimal]) -> str:
    """Drops each sentence with a number the input doesn't have (SPEC-BE-098 AC2)."""
    parts = re.split(r"(?<=[.!?।])\s+", text_value)
    return " ".join(p for p in parts if not _unsupported_numbers(p, allowed)).strip()


def _slugify(value: str) -> str:
    import unicodedata

    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:80] or "product"


def _unique(db: Session, tenant_id: str, column: str, base: str) -> str:
    value, n = base, 2
    while db.execute(text(f"SELECT 1 FROM products WHERE tenant_id = :t AND {column} = :v"),  # noqa: S608 - fixed column names
                     {"t": tenant_id, "v": value}).first():
        value, n = f"{base}-{n}", n + 1
    return value


def _vision_images(db: Session, tenant_id: str, media_ids: list[str]) -> list[tuple[str, bytes]]:
    """Up to 4 photos, scaled to 1024 px for the vision model."""
    import io

    from PIL import Image

    from app.services import media_service

    out: list[tuple[str, bytes]] = []
    for asset in media_service.media_rows(db, tenant_id, media_ids[:4], kinds=("image",)):
        img: Any = Image.open(io.BytesIO(media_service.read_bytes(asset)))
        img.thumbnail((1024, 1024))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88)
        out.append(("image/jpeg", buf.getvalue()))
    return out


def create_ai_listing(db: Session, tenant_id: str, actor_user_id: str | None, p: Any) -> dict[str, Any]:
    """Writes the listing with the company's AI (vision when there are photos)
    and saves it as a draft product. Price, SKU and weight come only from the
    user; every number the AI writes must be in the input or on the product."""
    from app.ai import command_actions as ca
    from app.ai.command_guard import numbers_in
    from app.ai.llm_client import LLMProviderError, llm_client
    from app.ai.prompts.product_listing import LISTING_SYSTEM, listing_user
    from app.ai.retrieval import get_brand_voice
    from app.core.audit import write_audit_log
    from app.core.exceptions import AppError
    from app.models.tenant import Tenant
    from app.services import media_service
    from app.utils.locale_data import format_money

    tenant = db.get(Tenant, tenant_id)
    currency = (p.currency or (tenant.currency if tenant else None) or "USD").strip().upper()
    price_cents = int((Decimal(str(p.price)) * 100).to_integral_value())
    compare_cents = int((Decimal(str(p.compare_at_price)) * 100).to_integral_value()) if p.compare_at_price else None
    media_ids = [str(m) for m in p.media_ids or []]
    assets = media_service.media_rows(db, tenant_id, media_ids, kinds=("image",)) if media_ids else []
    if p.new_sku and db.execute(text("SELECT 1 FROM products WHERE tenant_id = :t AND sku = :s"), {"t": tenant_id, "s": p.new_sku}).first():
        raise AppError(f"A product with SKU {p.new_sku} already exists.", 409)
    if not assets and not (p.name or p.details):
        raise AppError("Give the product's photos or details to write the listing from.", 422)
    brand = get_brand_voice(db, tenant_id)
    extra = {k: str(v) for k, v in (("Brand", p.brand), ("Category", p.category), ("Weight (grams)", p.weight_grams)) if v}
    user = listing_user(p.name, p.details, format_money(price_cents, currency),
                        format_money(compare_cents, currency) if compare_cents else None,
                        brand.brand_name, brand.primary_language or "en", brand.tone, extra)
    try:
        if assets:
            out = llm_client.complete_vision(LISTING_SYSTEM, user, _vision_images(db, tenant_id, media_ids), max_tokens=2000,
                                             db=db, tenant_id=tenant_id)
        else:
            out = llm_client.complete_with_usage(LISTING_SYSTEM, user, 2000, 90.0, db=db, tenant_id=tenant_id, temperature=0.4)
            if out.is_mock:
                raise LLMProviderError("No AI model is configured.")
        data = ca.parse_llm_json(out.text)
    except LLMProviderError as exc:
        raise AppError(f"The AI couldn't write the listing ({str(exc)[:160]}).", 503) from None

    # Numbers: only what the merchant gave or what is printed on the product.
    source = " ".join(str(x) for x in (p.name, p.details, p.price, p.compare_at_price, p.weight_grams, p.brand, p.category,
                                         data.get("visible_text")) if x)
    allowed = numbers_in(source)

    def clean(value: Any, limit: int) -> str:
        return _strip_numbers(" ".join(str(value or "").split()), allowed)[:limit].strip()

    title = clean(data.get("title"), 70) or (p.name or "New product")[:70]
    short = clean(data.get("short_description"), 220)
    html = _clean_html(str(data.get("description_html") or ""))
    if _unsupported_numbers(re.sub(r"<[^>]+>", " ", html), allowed):
        # Drop just the paragraph / list item with the unsupported number, then any list left empty.
        html = re.sub(r"<(p|li)>(.*?)</\1>",
                      lambda m: "" if _unsupported_numbers(re.sub(r"<[^>]+>", " ", m.group(2)), allowed) else m.group(0),
                      html, flags=re.S)
        html = re.sub(r"<ul>\s*</ul>", "", html)
    features = [f for f in (clean(x, 90) for x in (data.get("features") or [])[:8]) if f]
    raw_specs: dict[str, Any] = data["specifications"] if isinstance(data.get("specifications"), dict) else {}
    specs = {k: v for k, v in ((clean(k, 40), clean(v, 120)) for k, v in raw_specs.items()) if k and v}
    tags = sorted({t for t in (clean(x, 40).lower() for x in (data.get("tags") or [])[:12]) if t})
    seo_title = clean(data.get("seo_title"), 60) or title[:60]
    seo_description = clean(data.get("seo_description"), 160) or short[:160]
    sku = (p.new_sku or "").strip() or _unique(db, tenant_id, "sku", (_slugify(title)[:16].upper().strip("-") or "SKU") + "-AI")
    slug = _unique(db, tenant_id, "slug", _slugify(title))
    images = [{"media_id": str(a.id), "url": media_service.signed_url(str(a.id), 24 * 365), "alt": title} for a in assets]
    metadata = {
        "features": features, "specifications": specs, "category_suggestion": clean(data.get("category"), 60),
        "product_type": clean(data.get("product_type"), 80), "visible_text": str(data.get("visible_text") or "")[:300],
        "ai": {"model": out.model, "provider": out.provider, "generated_at": datetime.now(timezone.utc).isoformat(),
               "source_media": media_ids, "language": brand.primary_language},
    }
    product_id = str(db.execute(text(
        "INSERT INTO products (tenant_id, sku, title, slug, description, short_description, brand, status, default_price_cents, "
        "compare_at_price_cents, currency, weight_grams, tags, images, seo_title, seo_description, metadata, created_by, updated_by) "
        "VALUES (:t, :sku, :title, :slug, :descr, :short, :brand, 'draft', :price, :compare, :cur, :weight, :tags, "
        "CAST(:images AS jsonb), :seo_t, :seo_d, CAST(:meta AS jsonb), :actor, :actor) RETURNING id"),
        {"t": tenant_id, "sku": sku, "title": title, "slug": slug, "descr": html, "short": short or None, "brand": p.brand,
         "price": price_cents, "compare": compare_cents, "cur": currency, "weight": p.weight_grams, "tags": tags,
         "images": json.dumps(images), "seo_t": seo_title, "seo_d": seo_description, "meta": json.dumps(metadata),
         "actor": actor_user_id}).scalar_one())
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor_user_id, action="product.ai_listing_created",
                    resource_type="product", resource_id=product_id, metadata={"sku": sku, "model": out.model, "photos": len(assets)})
    logger.info("ai_listing_created", tenant_id=tenant_id, product_id=product_id, photos=len(assets))
    return {"summary": f"Draft listing “{title}” saved (SKU {sku}, {format_money(price_cents, currency)}).",
            "product_id": product_id, "sku": sku, "skus": [sku], "title": title, "link": "/ecommerce?tab=products",
            "data": [{"title": title, "sku": sku, "price": float(Decimal(price_cents) / 100), "currency": currency,
                      "features": len(features), "photos": len(assets), "status": "draft"}]}


def publish_product(db: Session, tenant_id: str, actor_user_id: str | None, product_id: str | None, sku: str | None) -> dict[str, Any]:
    """Our catalogue (status active + the web channel) and, when a store is
    connected, Shopify/WooCommerce first: a store failure changes nothing."""
    import uuid

    from app.core.audit import write_audit_log
    from app.core.exceptions import AppError, ConflictError, NotFoundError
    from app.integrations import store_products
    from app.services import integration_service, media_service

    if product_id:
        try:
            uuid.UUID(product_id)
        except ValueError:
            raise NotFoundError("Product not found.") from None
    where = "id = :v" if product_id else "sku = :v"
    args: dict[str, Any] = {"v": product_id or sku}
    row = db.execute(text(
        "SELECT id, sku, title, description, short_description, brand, default_price_cents, compare_at_price_cents, currency, "
        "tags, images, seo_title, seo_description, metadata, external_ids, status "
        f"FROM products WHERE tenant_id = :t AND deleted_at IS NULL AND {where}"),  # noqa: S608 - fixed where clauses
        {"t": tenant_id, **args}).mappings().first()
    if row is None:
        raise NotFoundError("Product not found.")
    if not row["title"] or not row["default_price_cents"] or row["default_price_cents"] <= 0:
        raise ConflictError("The product needs a title and a price before it can be published.")
    store = integration_service.store_connection(db, tenant_id)
    store_out: dict[str, Any] | None = None
    notes: list[str] = []
    if store:
        urls: list[str] = []
        try:
            for img in row["images"] or []:
                if isinstance(img, dict) and img.get("media_id"):
                    urls.append(media_service.platform_url(media_service.require(db, tenant_id, str(img["media_id"]))))
        except ConflictError as exc:
            urls = []
            notes.append(f"The photos weren't sent to the store: {exc.detail}")
        product = {
            "title": row["title"], "description": row["description"], "short_description": row["short_description"],
            "brand": row["brand"], "price_cents": int(row["default_price_cents"]), "compare_at_cents": row["compare_at_price_cents"],
            "sku": row["sku"], "tags": list(row["tags"] or []), "seo_title": row["seo_title"],
            "seo_description": row["seo_description"], "category": (row["metadata"] or {}).get("category_suggestion"),
            "external_ids": row["external_ids"] or {},
        }
        try:
            store_out = store_products.publish(store, product, urls)
        except store_products.StoreError as exc:
            name = {"shopify": "Shopify", "woocommerce": "WooCommerce"}.get(store["provider"], store["provider"])
            raise AppError(f"Not published: {name} said: {exc.message}", 502) from None
    external = dict(row["external_ids"] or {})
    if store_out:
        external[store_out["provider"]] = store_out["external_id"]
    db.execute(text(
        "UPDATE products SET status = 'active', updated_by = :actor, external_ids = CAST(:ext AS jsonb), "
        "channels = CASE WHEN 'web'::channel_type = ANY(channels) THEN channels ELSE array_append(channels, 'web'::channel_type) END "
        "WHERE tenant_id = :t AND id = :id"),
        {"actor": actor_user_id, "ext": json.dumps(external), "t": tenant_id, "id": row["id"]})
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor_user_id, action="product.published", resource_type="product",
                    resource_id=str(row["id"]), metadata={"sku": row["sku"], "store": store_out})
    where_to = "your website"
    if store_out:
        name = {"shopify": "Shopify", "woocommerce": "WooCommerce"}.get(store_out["provider"], store_out["provider"])
        where_to += f" and {name}" + (" (updated)" if store_out["updated"] else "")
    return {"summary": " ".join([f"Published “{row['title']}” on {where_to}.", *notes]), "product_id": str(row["id"]),
            "sku": row["sku"], "link": (store_out or {}).get("url") or "/ecommerce?tab=products"}
