Purpose
Implement real stock tracking for products, matching exactly what the frontend
HTML shows: a Stock column on the E-Commerce Products table (with a danger
badge for low stock and a warn badge for out of stock), and a "Low-stock
alerts" count on the Dashboard's E-Commerce engine card. Nothing beyond that
view is in scope.

Scope
The existing stub files for the inventory domain: app/models/inventory.py,
the matching file under app/schemas/, app/services/inventory_service.py, and
app/api/v1/inventory.py. No new files or folders. No multi-location logic,
no reorder-quantity automation, no purchase-order flow - none of that is
shown in the HTML.

Contract
After this step: a request for a tenant's inventory returns, per product
variant, on_hand, available, and reorder_point; a request for low-stock items
returns only variants where available <= reorder_point; an authorized user
can adjust on_hand for one variant and the change is reflected immediately
and recorded.

Functional rules
- List endpoint returns stock for every variant belonging to the caller's
  tenant only - on_hand, available, reorder_point.
- Low-stock endpoint returns only variants where available <= reorder_point,
  for the caller's tenant only - this is the number the Dashboard's
  "Low-stock alerts" count is drawn from.
- Adjust endpoint changes on_hand for one variant, requires manager role or
  above (existing role hierarchy), returns the updated row.
- Every adjustment writes one row to inventory_movements and one entry via
  the existing write_audit_log() function - do not invent a new audit
  mechanism, use the one that already exists in core/audit.py.
- Every query and mutation filters by tenant_id explicitly, per this
  codebase's existing service convention - no ORM-level auto filter exists.

Edge cases
- Adjusting on_hand below zero is rejected with a clear error, nothing is
  written.
- Adjusting a variant that does not belong to the caller's tenant returns
  404, not the other tenant's row and not a permission error that would
  confirm the row exists.
- available is computed as on_hand minus committed, matching the existing
  database column - do not recompute this differently in application code.

Non-functional rules
No new files or folders - fill in the four existing stub files only. Follow
the existing service pattern: plain functions, explicit db and tenant_id
parameters, no classes. Type hints on every function. No print statements -
structlog only. No test framework exists yet, so verification is manual.

Acceptance criteria
- GET the list endpoint returns only the caller's tenant's variants with
  on_hand, available, reorder_point.
- GET the low-stock endpoint returns only variants where
  available <= reorder_point.
- The adjust endpoint succeeds for a manager-role user, fails with a
  permission error for a viewer-role user.
- A successful adjustment produces one new inventory_movements row and one
  new audit_log row.
- Adjusting a variant belonging to a different tenant returns 404.
- Adjusting on_hand to a negative value is rejected, no row is written.

Assumptions
app/models/inventory.py, the matching schema file, inventory_service.py, and
api/v1/inventory.py already exist as stubs with correct signatures (per
CLAUDE.md's "structurally stubbed" list) - this spec fills their bodies in,
it does not create them. The inventory and inventory_movements tables already
exist in the database. core/audit.write_audit_log() and
dependencies.require_permission() already exist and work as documented in
CLAUDE.md.

Target files (all existing - none added, none removed):
backend/app/models/inventory.py
backend/app/schemas/inventory.py
backend/app/services/inventory_service.py
backend/app/api/v1/inventory.py

Amendment (2026-09-30, IMPLEMENTED after plan approval, for SPEC-FE-027's Inventory tab)
GET /inventory, GET /inventory/low-stock and the adjust response carry, in addition
to the existing fields: `committed`, `sku` (product_variants.sku, falling back to
products.sku), `product_title` (products.title), `variant_label` (the variant's
`attributes` values joined with " / ", or null when empty), `location_name`
(inventory_locations.name) and `low_stock` (available <= reorder_point, the same rule
as /low-stock). The existing fields are unchanged, so the dashboard's low-stock card
keeps working. Reason: rows currently carry only variant_id/location_id UUIDs, so
the tab can't show which product a row is. The data comes from one joined query with
no N+1, every join filtered by tenant. List order is changed from `id` to product
title, then sku, then location name, so the table reads naturally. Adjust behavior
(manager+, movement row, audit row) is unchanged; the audit write already targets the
live `audit_log` table. Files: schemas/inventory.py, services/inventory_service.py,
api/v1/inventory.py.
Implementation notes (2026-09-30): product_variants is read through a SQLAlchemy Core
table of the live columns the service needs (id, tenant_id, product_id, sku,
attributes), because the ProductVariant ORM model in models/product.py is still
misaligned: it has no tenant_id or attributes, and it has name/price columns that
don't exist live. models/product.py is outside this amendment's files. Bug found and
fixed: every adjust failed on the live DB, because the audit metadata carried
variant_id/location_id as uuid.UUID objects, which can't be serialized to jsonb. They
are now stringified. Verified on live Postgres in a rolled-back transaction.
