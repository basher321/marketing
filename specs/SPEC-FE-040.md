# SPEC-FE-040: Shipping engine UI — status, import/sync, guided setup, validation

Status: IMPLEMENTED, NOT YET VERIFIED ON THE LIVE DB (2026-10-01). The plan was approved as recommended (all 9 decisions). Done: ruff/mypy at baseline, the app imports, `next build` passes, and the logic was checked in-process with `httpx.MockTransport` (no DB). Still open: the additive DDL and the rolled-back live-Postgres acceptance run, both blocked by the session's permission rules. The user must run the DDL, then re-run verification. Backend: SPEC-BE-058. Keeps the existing Shipping tab on /ecommerce (`components/ecommerce/shipping-zones.tsx`) and makes it functional.

## Screens
- **Status bar** at the top of the Shipping tab (`GET /shipping/status`):
  - The store (Shopify, WooCommerce or none) and a mode badge: Synced from Shopify · Local setup · Setup required.
  - Last sync time and result, counts, and an expandable error list.
  - "Sync now" and "Re-detect" buttons (manager+).
- **3A, detected:** after a store connects, or on Re-detect, a preview dialog lists what will be imported: zones → methods, each with type, price, threshold and conditions. A second list shows what is "Not available through the API". "Import" runs `POST /shipping/sync`.
- **3B, setup required:** a 4-step guided wizard:
  1. **Where you ship:** zones, with a country picker and optional regions.
  2. **Methods per zone:**
     - Flat rate.
     - Free shipping, with a minimum order.
     - Carrier-calculated, only if a carrier is connected.
     - Local pickup: location and instructions.
     - Local delivery: radius or regions, plus a fee.
     - Each method also takes conditions (order subtotal or weight ranges), a delivery time (SLA) and a cutoff.
  3. **Review:** runs `POST /shipping/validate`. Errors block; warnings are shown.
  4. **Activate:** `POST /shipping/setup`, with an "Also create this in my store" checkbox when a store is connected.
- **Zones table** (existing) gains:
  - A source badge, the method type, and a conditions summary.
  - A validation icon, with the issues on hover.
  - A lock and a "Managed by Shopify" note on rows the store API can't update (SPEC-BE-058 decision 2).
  - An edit dialog for rates: name, price, free-over, conditions, SLA.

## Acceptance criteria
Run in headless Edge against the running backend and the live Postgres. Store calls are answered by the backend's fixture transport.
1. **Shipping-A:** connecting a fixture store that has a shipping config shows the detected preview. Import creates the zones, which appear in the table with source badges, and the status bar shows the last sync.
2. **Shipping-B:** with an empty store (or no store), the guided wizard appears and blocks on validation errors. Activate creates a valid configuration, and makes the store calls when the checkbox is on.
3. Sync errors appear in the status bar, and Sync now updates the last sync time.
4. `npx tsc --noEmit` passes.

## Target files
Existing: `components/ecommerce/shipping-zones.tsx`, `app/(app)/ecommerce/page.tsx`, `lib/api/shipping.ts`, `lib/types/shipping.ts`.

**New files (need approval):** `components/ecommerce/shipping-setup-wizard.tsx`, `components/ecommerce/shipping-status-bar.tsx`.
