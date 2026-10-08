Purpose
Implement the product catalog list, matching exactly what the E-Commerce
page's Products table shows: SKU, Product, Price, Channel, and Status, for
the caller's tenant. Stock is already covered by SPEC-BE-005 and is
explicitly out of scope here.

Scope
The existing stub files for the products domain: app/models/product.py,
the matching file under app/schemas/, app/services/product_service.py, and
app/api/v1/products.py. No new files or folders. No create, update, or
delete of products, no variant management, no pricing rules, no category
or tag management - none of that is rendered in the HTML's Products table.

Contract
After this step: a request returns the caller's tenant's products, each
with SKU, product name, price, the channel(s) it is listed on, and its
status - the five columns the HTML table shows other than Stock, which the
existing inventory endpoint already serves.

Functional rules
- List endpoint returns products for the caller's tenant only, each with:
  SKU, product name (title), price, channel list, and status.
- Price is formatted the same way price is already handled elsewhere in
  this codebase - do not invent a new money-formatting convention.
- Status is the product's own stored status field (draft/active/archived/
  out_of_stock, or whatever values the existing model defines) - it is
  never derived or recomputed from stock.
- Sort order: most recently updated first, consistent with the sort
  convention used in the conversations list (SPEC-BE-007), unless the
  existing model already defines an explicit display-order field.
- Every query filters by tenant_id explicitly, per this codebase's
  existing service convention.

Edge cases
- If the existing product model does not carry a distinct "channels"
  field, approximate using the closest available field and document the
  exact mapping as a code comment - never fabricate channel data that
  isn't backed by a real column.
- A product with no channels assigned returns an empty list for that
  field, not a placeholder string.
- A product belonging to another tenant never appears in the list.

Non-functional rules
No new files or folders - fill in the four existing stub files only. Follow
the existing service pattern: plain functions, explicit db and tenant_id
parameters, no classes. Type hints on every function. No print statements -
structlog only. No test framework exists yet, so verification is manual.

Acceptance criteria
- The list endpoint returns only the caller's tenant's products, each with
  SKU, product name, price, channel(s), and status.
- If channel data is approximated from another field, the mapping rule is
  documented as a code comment.
- A product belonging to a different tenant never appears in the list,
  verified with two tenants.
- No create, update, delete, variant, pricing-rule, or category/tag-
  management endpoint exists as a result of this spec.

Assumptions
app/models/product.py, the matching schema file, product_service.py, and
api/v1/products.py already exist as stub files with correct signatures
(per CLAUDE.md's "structurally stubbed" list) - this spec fills their
bodies in, it does not create them. Stock display is already handled by
SPEC-BE-005's inventory endpoint and is not duplicated here.

Target files (all existing - none added, none removed):
backend/app/models/product.py
backend/app/schemas/product.py
backend/app/services/product_service.py
backend/app/api/v1/products.py

Amendment (2026-09-29, for SPEC-FE-011's Stock column)
Each list item also carries `stock` (SUM of inventory.available over the product's
variants and locations; null when the product has no inventory rows) and
`low_stock` (true when any of those rows has available <= reorder_point - the same
rule as GET /inventory/low-stock, SPEC-BE-005). Reason: /inventory rows carry only
variant_id, with no sku or product id, so the frontend could not join stock to
products; the spec forbids a frontend-invented low-stock cutoff. Computed in one
grouped query, tenant-scoped on inventory.tenant_id. Files: schemas/product.py,
services/product_service.py.
