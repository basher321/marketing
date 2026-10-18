"""Publishing a catalogue product to the connected store (SPEC-BE-098 FR3b).

Shopify (GraphQL Admin API, the integration's token): productCreate with media,
then the default variant's price/compare-at price/SKU via
productVariantsBulkUpdate; productUpdate when the product was published before
(its id is in products.external_ids.shopify), so re-publishing never makes a
duplicate. A failure after productCreate deletes the new product again.

WooCommerce (REST v3): POST /products, or PUT /products/{id} when published
before. Woo's regular_price is the compare-at price when there is a discount,
with sale_price the selling price.

Image URLs must be public (S3, or a public https PUBLIC_BASE_URL); without
them the product is published without images and the caller says so.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.integrations import shopify, woocommerce


class StoreError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _money(cents: int | None) -> str | None:
    return None if cents is None else str((Decimal(int(cents)) / 100).quantize(Decimal("0.01")))


_CREATE = """
mutation Create($product: ProductCreateInput!, $media: [CreateMediaInput!]) {
  productCreate(product: $product, media: $media) {
    product { id handle onlineStoreUrl variants(first: 1) { nodes { id } } }
    userErrors { field message }
  }
}"""
_UPDATE = """
mutation Update($product: ProductUpdateInput!) {
  productUpdate(product: $product) {
    product { id handle onlineStoreUrl variants(first: 1) { nodes { id } } }
    userErrors { field message }
  }
}"""
_VARIANT = """
mutation Variant($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkUpdate(productId: $productId, variants: $variants) {
    productVariants { id }
    userErrors { field message }
  }
}"""
_DELETE = """
mutation Delete($input: ProductDeleteInput!) { productDelete(input: $input) { deletedProductId userErrors { field message } } }"""


def _user_errors(data: dict[str, Any], key: str) -> None:
    errors = (data.get(key) or {}).get("userErrors") or []
    if errors:
        raise StoreError("Shopify refused it: " + "; ".join(str(e.get("message")) for e in errors[:3]))


def _shopify(fields: dict[str, str], product: dict[str, Any], image_urls: list[str]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": product["title"], "descriptionHtml": product.get("description") or "", "status": "ACTIVE",
        "tags": product.get("tags") or [], "vendor": product.get("brand") or None, "productType": product.get("category") or None,
        "seo": {"title": product.get("seo_title") or None, "description": product.get("seo_description") or None},
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    existing = (product.get("external_ids") or {}).get("shopify")
    created = False
    try:
        if existing:
            data = shopify.graphql(fields, _UPDATE, {"product": {"id": existing, **payload}})
            _user_errors(data, "productUpdate")
            node = data["productUpdate"]["product"]
        else:
            media = [{"originalSource": u, "mediaContentType": "IMAGE", "alt": product["title"][:250]} for u in image_urls]
            data = shopify.graphql(fields, _CREATE, {"product": payload, "media": media or None})
            _user_errors(data, "productCreate")
            node = data["productCreate"]["product"]
            created = True
        variant = (node.get("variants") or {}).get("nodes") or []
        if variant:
            v: dict[str, Any] = {"id": variant[0]["id"], "price": _money(product["price_cents"]),
                                 "inventoryItem": {"sku": product["sku"]}}
            if product.get("compare_at_cents"):
                v["compareAtPrice"] = _money(product["compare_at_cents"])
            data = shopify.graphql(fields, _VARIANT, {"productId": node["id"], "variants": [v]})
            _user_errors(data, "productVariantsBulkUpdate")
    except (shopify.ShopifyError, StoreError, KeyError, TypeError) as exc:
        if created:
            try:  # all-or-nothing: remove the half-made product
                shopify.graphql(fields, _DELETE, {"input": {"id": node["id"]}})
            except Exception:  # noqa: BLE001 - the original error is what matters
                pass
        message = getattr(exc, "message", None) or f"Shopify answered unexpectedly ({type(exc).__name__})."
        raise StoreError(str(message)) from None
    return {"provider": "shopify", "external_id": node["id"], "url": node.get("onlineStoreUrl"), "updated": bool(existing)}


def _woo(fields: dict[str, str], product: dict[str, Any], image_urls: list[str]) -> dict[str, Any]:
    price, compare = product["price_cents"], product.get("compare_at_cents")
    body: dict[str, Any] = {
        "name": product["title"], "type": "simple", "status": "publish", "sku": product["sku"],
        "description": product.get("description") or "", "short_description": product.get("short_description") or "",
        "tags": [{"name": t} for t in product.get("tags") or []],
    }
    if compare and compare > price:
        body.update(regular_price=_money(compare), sale_price=_money(price))
    else:
        body.update(regular_price=_money(price), sale_price="")
    if image_urls:
        body["images"] = [{"src": u} for u in image_urls]
    existing = (product.get("external_ids") or {}).get("woocommerce")
    try:
        out = woocommerce.request(fields, "PUT" if existing else "POST", f"/products/{existing}" if existing else "/products", json=body)
    except woocommerce.WooError as exc:
        raise StoreError(exc.message) from None
    if not isinstance(out, dict) or not out.get("id"):
        raise StoreError("WooCommerce didn't return the product.")
    return {"provider": "woocommerce", "external_id": str(out["id"]), "url": out.get("permalink"), "updated": bool(existing)}


def publish(store: dict[str, Any], product: dict[str, Any], image_urls: list[str]) -> dict[str, Any]:
    """{provider, external_id, url, updated}; raises StoreError (nothing left half-made)."""
    if store["provider"] == "shopify":
        return _shopify(store["fields"], product, image_urls)
    if store["provider"] == "woocommerce":
        return _woo(store["fields"], product, image_urls)
    raise StoreError(f"Publishing to {store['provider']} isn't supported.")
