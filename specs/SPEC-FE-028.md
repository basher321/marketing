# SPEC-FE-028: E-Commerce — Pricing Rules Tab

Status: IMPLEMENTED (2026-09-30), plan approved by the user; verified E2E in headless Edge against the running backend + live Postgres (test rules and their audit rows removed afterwards). Depends on SPEC-BE-042.

Implementation notes: start and end use the browser's datetime-local input (viewer local time) and are sent as UTC instants. FastAPI 422 field errors are shown as their messages. The 403 message was checked with a simulated 403, since dev-shop has no non-manager user; the backend 403s are covered by the SPEC-BE-042 verification.

## Purpose
Fill the E-Commerce page's **Pricing Rules** tab with a list of automatic discount and price rules, plus a way to add one. This is modelled on Shopify's automatic discounts and WooCommerce's dynamic pricing.

## Functional rules
1. **Header row:** "N rules" on the left, "+ New rule" (`.btn .btn-sm`) on the right.
2. **Columns:** Rule (name, with description muted below it), Type (Percent off / Fixed amount off / Fixed price / Tiered), Value ("10% off", "৳50 off", "৳500"; tiered shows "—"), Applies to ("All products", or "N products" / "N categories" / "N tags" from `scope_count`), Min qty ("—" when null), Schedule ("Always", "From Oct 1", "Until Oct 31", "Oct 1 – Oct 31"), Priority, Status badge (active → success, scheduled → warn, expired/disabled → neutral), and an Enable/Disable button.
3. **Enable/Disable** calls `PATCH /pricing/rules/{id}` and updates the row from the response. A 403 shows "Only managers and above can change pricing rules."
4. **"+ New rule"** opens an inline form above the table, in the FAQ-form style (`.form-row`), with exactly the create schema's fields. They are: name, description, type (the 3 creatable types), value (the label switches between "%" and the currency), applies to (All products, or Specific products as a checkbox list of the tenant's products from the existing `GET /products`), min quantity, start and end date-time, and priority. The frontend runs the same checks as the backend (value > 0, ≤ 100 for percent, at least one product for specific, end after start), but the backend is the authority and its 422 messages are shown inline. On success the list is refetched and the form resets.
5. Loading, empty ("No pricing rules yet — create one to discount products automatically.") and error states.

## Acceptance criteria (verified E2E)
1. The list matches `pricing_rules` in the DB, including the derived state.
2. Creating an "all products, 10% off" rule and a "specific products, ৳50 off" rule through the UI persists exactly those rows plus audit rows. Toggling one flips `enabled`. The test rules are deleted from the DB afterwards unless the user wants to keep them.
3. Invalid input shows an error and writes nothing.

## Target files
- app/(app)/ecommerce/page.tsx
- components/ecommerce/pricing-rules.tsx (new)
- lib/api/pricing.ts (new)
- lib/types/pricing.ts (new)
