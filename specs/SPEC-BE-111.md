# SPEC-BE-111: Business type — adaptive e-commerce tabs, fields and product validation

Status: IMPLEMENTED (2026-10-22). 34/34 rolled-back checks. A product made by hand gets one default variant; setting stock creates the default location 'Main location' (code MAIN) when none exists. UI in SPEC-FE-075.

## The problem

E-Commerce has five fixed tabs (Products, Orders, Inventory, Pricing Rules, Shipping). Products can't be
created or edited by hand (SPEC-BE-008 removed CRUD; only AI listings create them, SPEC-BE-097). Every
company sees the same fields whatever it sells.

## Business types (registry `utils/business_types.py`, the only place they're defined)

| Type | Tabs | Product fields | Notes |
|---|---|---|---|
| `online_retail` | Products, Categories, Inventory, Orders, Customers, Shipping, Payments, Pricing Rules | name, description, SKU, category, price, compare-at (discount), cost, stock, weight, images, status | price required |
| `physical_store` | Products, Categories, Inventory, Orders, Customers, Payments, Pricing Rules | same, no weight | no Shipping tab; orders default to pickup |
| `catalog` | Products, Categories, Customers, Orders (labelled "Enquiries") | name, description, SKU, category, price (optional = "price on request"), images, status | no stock, no shipping |
| `digital` | Products, Categories, Orders, Customers, Payments | name, description, SKU, category, price, compare-at, images, status, delivery note | no stock, weight or shipping |
| `other` | as `online_retail` | as `online_retail` | |

Labels are English and Bengali. Hiding a tab hides it only; no data is deleted.

## Requirements

- **FR1 Stored setting.** `tenants.settings.ecommerce = {business_type, confirmed: bool, confirmed_by,
  confirmed_at}`. No DDL.
- **FR2 Suggestion, never a silent decision.** `ecommerce_service.suggest(db, tenant_id)` →
  `{type | null, reasons[]}` from evidence only: a connected Shopify/WooCommerce store, shipping zones,
  inventory rows, product weights. No evidence → `null` and the UI asks the user to choose. A suggestion is
  shown until the user confirms; it is never saved as `confirmed`.
- **FR3 `GET /ecommerce/config`** → `{business_type, confirmed, suggestion, tabs[] {key, label}, product_fields[]
  {key, label, required, type}, order_fields[], types[] (all choices with descriptions)}`. Unconfirmed
  companies get `online_retail` tabs plus `confirmed: false`.
- **FR4 `PUT /ecommerce/config {business_type}`** (manager+, audited) sets and confirms it.
- **FR5 Products by hand** (manager+, audited): `POST /products`, `PATCH /products/{id}` with the fields the
  company's type allows. A field the type doesn't use → 422 ("Digital products don't have stock"). Required
  fields per the table. SKU unique per company (409). Price/compare-at in major units → cents.
  Compare-at must be higher than price. Images = media library ids (SPEC-BE-074). Stock sets the default
  location's inventory through the existing adjust path (SPEC-BE-005) so it is audited. `DELETE` archives.
- **FR6 Categories.** `GET /product-categories`, `POST`, `PATCH /{id}` (manager+) over the live
  `product_categories` table (map the live columns first). `GET /products` gains `category` and `?category_id`.
- **FR7 Payments tab.** `GET /orders/payments?status=unpaid|paid|cod|refunded&range` → orders with payment
  method, status, total; `POST /orders/{id}/payment {payment_status, method?, reference?}` (agent+, audited,
  stored in `orders.payment_status` / `metadata.payment`).

## Acceptance criteria (live DB, rolled back)

1. A company with a Shopify connection gets suggestion `online_retail` with the reason; a new empty company
   gets `null`; neither is confirmed until PUT.
2. Each type returns its tabs and fields; `catalog` accepts a product with no price; `digital` refuses stock.
3. Product create/edit/archive, duplicate SKU 409, compare-at lower than price 422, another company's product 404.
4. Categories and payments routes work and are company-scoped.

## Files

New: `utils/business_types.py`, `services/ecommerce_service.py`, `api/v1/ecommerce.py`,
`schemas/ecommerce.py`, `api/v1/product_categories.py`. Changed: `services/product_service.py`,
`api/v1/products.py`, `schemas/product.py`, `models/product.py` (category mapping), `api/v1/orders.py`,
`services/order_service.py`, `api/router.py`.
