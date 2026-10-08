# SPEC-FE-027: E-Commerce — Inventory Tab

Status: IMPLEMENTED (2026-09-30), plan approved by the user; verified E2E in headless Edge against the running backend + live Postgres (test adjusts reverted, their movement/audit rows removed). Depends on the SPEC-BE-005 amendment (2026-09-30).

Implementation notes: the Adjust editor opens as an extra row under the item. A negative quantity is blocked by the input's min=0 before any request is sent. The 403 message was checked with a simulated 403 response, since dev-shop has no non-manager user; the backend 403 itself is covered by the SPEC-BE-005 verification.

## Purpose
Fill the E-Commerce page's **Inventory** tab. It follows the Shopify inventory screen: a stock level per product variant and location, with a quick on-hand adjustment.

## Functional rules
1. **Toolbar:** a "Low stock only" checkbox that filters the fetched list client-side on the backend's `low_stock` flag, plus a count such as "6 items · 2 low stock".
2. **Columns:** Product (`product_title`, with `variant_label` muted below it when present), SKU, Location, On hand, Committed, Available, Reorder point, Status, and Adjust.
3. **Status badge** (from backend fields only, never a frontend cutoff): available ≤ 0 → danger "Out of stock", `low_stock` → warn "Low stock", otherwise success "In stock".
4. **Adjust:** clicking "Adjust" (`.btn-secondary .btn-sm`) turns the row into an inline editor: a new on-hand number (≥ 0), an optional reason, and Save/Cancel. Save calls `POST /api/v1/inventory/{id}/adjust`. On success, the row updates from the response and the products list and dashboard low-stock queries are invalidated, because their stock numbers change too. On failure, the backend message is shown inline and the typed value stays. A 403 shows "Only managers and above can adjust stock." The frontend has no current-user role today, so the button is shown to everyone and the backend enforces permission.
5. Loading, empty ("No inventory records yet") and error states follow the Products-table pattern.

## Acceptance criteria (verified E2E)
1. The rows match dev-shop's `inventory` rows joined to their product, variant and location in the DB.
2. The low-stock filter and badges match `available <= reorder_point` exactly.
3. An adjust as the owner updates the row, and the DB shows the new `on_hand`, one `inventory_movements` row and one `audit_log` row. The test value is then set back to the original. A negative value is rejected with no DB change.
4. The Products tab's Stock column reflects the adjustment without a reload.

## Target files
- app/(app)/ecommerce/page.tsx
- components/ecommerce/inventory-table.tsx (new)
- lib/api/inventory.ts (new)
- lib/types/inventory.ts (new)
