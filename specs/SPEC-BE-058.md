# SPEC-BE-058: Shipping engine — detect, import/sync from the store, or guided setup

Status: IMPLEMENTED, VERIFIED ON THE LIVE DB (2026-10-01). The plan was approved as recommended (all 9 decisions). Done: ruff/mypy at baseline, the app imports, `next build` passes, and the logic was checked in-process with `httpx.MockTransport` (no DB). The additive DDL was applied 2026-10-01. Live-DB verified 2026-10-01 after a fix: activation checks now validate the zone last (an overlap was never attributed to it), and POST /shipping/zones and /zones/{id}/rates run the same check (they created active rows unvalidated). Shopify local pickup is not imported (listed as unsupported). Source: Developer Change Spec §1 and the diagram's "SHIPPING REQUIREMENT" (1 Detect store → 2 Read current shipping config → 3A import/sync or 3B guided setup → 4 Validate → 5 Save + monitor). SPEC-BE-057 stays reserved for the read-only Meta MCP (SPEC-BE-054). Frontend: SPEC-FE-040. Command Chat shipping commands: SPEC-BE-059.

Implementation notes: added `POST /shipping/setup/validate` (dry-run for the wizard's Review step). The country-overlap check covers local zones only, because Shopify product profiles legitimately share countries. Store zones with no methods are imported inactive.

## Purpose
Today the Shipping tab (SPEC-BE-043) is local-only: zones and flat rates typed by hand, no connection to the store, no validation, no sync. This spec makes it functional:
1. **Detect:** when a store integration (Shopify or WooCommerce) is connected or re-tested, read its shipping configuration.
2. **3A — existing config:** import zones, methods, rates, free-shipping thresholds, carrier-calculated methods and local pickup/delivery that the store's API exposes, then keep them in sync.
3. **3B — no usable config** (or no store, e.g. a plain website): a guided setup creates zones, methods, rates, free-shipping thresholds and pickup/local delivery in our DB, and — for a connected store — pushes it to the store (open decision 2).
4. **Validate** before a zone/method is active.
5. **Save + monitor:** sync status, last sync, errors and audit logs.

## Store APIs (checked 2026-10-01; each call through one client per platform with an SSRF-guarded httpx client and an injectable `client_factory`, like `meta_ads.py`)
- **Shopify** (Admin GraphQL, version from a new `SHOPIFY_API_VERSION` setting, default `2026-07`; scopes `read_shipping` + `write_shipping`):
  - Read: `deliveryProfiles { profileLocationGroups { locationGroupZones { zone { id name countries { code { countryCode restOfWorld } provinces { code name } } } methodDefinitions { id name active description rateProvider { ... on DeliveryRateDefinition { price { amount currencyCode } } ... on DeliveryParticipant { carrierService { id name } fixedFee { amount } percentageOfRateFee } } methodConditions { field operator conditionCriteria { ... on MoneyV2 { amount } ... on Weight { value unit } } } } } } }`, plus `locations { localPickupSettingsV2 { pickupTime instructions } }` and `carrierServices`.
  - Write (3B push / chat updates): `deliveryProfileUpdate` on the general profile (add/update zones and method definitions).
  - Auth: the existing SPEC-BE-052 Shopify credentials. Note the known gap (memory, 2026-10-01): stores created after 2026-01-01 use a Dev Dashboard client ID/secret with 24-hour tokens; this spec adds the client-credentials token refresh (`POST https://{shop}/admin/oauth/access_token` with `grant_type=client_credentials`) when those fields are saved, and keeps the static admin token for older stores.
- **WooCommerce** (REST v3, consumer key/secret from SPEC-BE-052):
  - Read: `GET /wp-json/wc/v3/shipping/zones`, `/shipping/zones/{id}/locations`, `/shipping/zones/{id}/methods` (method ids `flat_rate`, `free_shipping` with `min_amount`/`requires`, `local_pickup`), `/shipping_methods`, `/shipping/classes`.
  - Write: the same endpoints' POST/PUT/DELETE.
- **No store connected:** the merchant's own website / manual store; 3B guided setup only, nothing is pushed.

"Detected" = the store returned at least one zone with at least one active method. Zero zones, or only zones with no active methods → "no usable setup" → 3B.

## Data model (live DB changes — need approval, open decision 1)
```sql
ALTER TABLE shipping_zones
  ADD COLUMN IF NOT EXISTS source varchar(20) NOT NULL DEFAULT 'local',      -- local | shopify | woocommerce
  ADD COLUMN IF NOT EXISTS external_id varchar(255),
  ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb;     -- profile name, rest_of_world, raw ids
ALTER TABLE shipping_policies
  ADD COLUMN IF NOT EXISTS source varchar(20) NOT NULL DEFAULT 'local',
  ADD COLUMN IF NOT EXISTS external_id varchar(255),
  ADD COLUMN IF NOT EXISTS method_type varchar(30) NOT NULL DEFAULT 'flat_rate',
     -- flat_rate | free_shipping | carrier_calculated | local_pickup | local_delivery
  ADD COLUMN IF NOT EXISTS conditions jsonb NOT NULL DEFAULT '{}'::jsonb,   -- {min_subtotal_cents, max_subtotal_cents, min_weight_g, max_weight_g}
  ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb;     -- carrier service, fees, pickup instructions, validation result
CREATE UNIQUE INDEX IF NOT EXISTS shipping_zones_source_external
  ON shipping_zones (tenant_id, source, external_id) WHERE external_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS shipping_policies_source_external
  ON shipping_policies (tenant_id, source, external_id) WHERE external_id IS NOT NULL;
```
Existing rows become `source='local'`, `method_type='flat_rate'`; SPEC-BE-043 behavior is unchanged for them.

Mapping rules (each a code comment):
- Shopify zone → one `shipping_zones` row per (profile, location group, zone); name = zone name, prefixed with the profile name when it isn't the general profile. Countries → `country_codes`; provinces → `regions` (names); "Rest of world" → `country_codes = []` + `metadata.rest_of_world = true`.
- Shopify method with a fixed price → `flat_rate` (price 0 → `free_shipping`); a `TOTAL_PRICE GREATER_THAN_OR_EQUAL` condition → `conditions.min_subtotal_cents` (a free method with that condition is the store's **free-shipping threshold**; it is also shown as `free_over` on the zone's paid rates for the existing UI). Weight conditions → `min/max_weight_g`. Carrier service → `carrier_calculated`, `rate_cents = 0` and `metadata.carrier_service` (the price is computed by the carrier at checkout, never by us).
- WooCommerce: `flat_rate.cost` → `rate_cents` (only plain numbers; a cost formula like `10 + [qty]*2` is imported as `metadata.cost_formula` and flagged in validation as "formula — edit in WooCommerce"); `free_shipping.min_amount` → `free_shipping` + `min_subtotal_cents`; `local_pickup` → `local_pickup`.
- Money: store currency must equal the tenant currency; otherwise the import stops with a validation error (no conversion).
- Checkout rules the APIs expose (conditions above, pickup instructions) are imported. Anything else the API doesn't expose (e.g. Shopify checkout customizations / Functions) is **not** imported, and the result lists it as "not available through the API".

## Contract (`/api/v1`, manager+ for writes, all audited)
- `GET /shipping/status` → `{store: {provider, connected, account_name}|null, detected: bool|null, mode: "synced"|"local"|"setup_required", last_sync_at, last_sync_status: "ok"|"partial"|"failed"|null, errors: [...], counts: {zones, methods}, unsupported: [...]}`.
- `POST /shipping/detect` → reads the store config **without writing** → `{detected, preview: {zones: [...with methods...]}, unsupported, warnings}`.
- `POST /shipping/sync` → imports/updates (upsert by `external_id`; zones/methods deleted in the store are deactivated here, not deleted) → `{created, updated, deactivated, errors, last_sync_at}`.
- Automatic detection: `integration_service` runs `detect` after a Shopify/WooCommerce connection saves or tests OK; when detected, it runs `sync` (3A). The scheduler's `sync_tasks.py` (inert stub today) re-syncs every 6 hours.
- `GET /shipping/zones` (existing) gains `source`, `external_id`, and per-rate `method_type`, `conditions`, `validation: {ok, issues}`, `read_only`.
- Guided setup (3B): `POST /shipping/setup` body `{zones: [{name, country_codes, regions, methods: [{name, method_type, carrier, rate, free_over?, conditions?, sla_days_min?, sla_days_max?, cutoff_time?, pickup?: {location_name, instructions}}]}], push_to_store: bool}` → validates all, then creates everything in one transaction (and pushes to the store first when `push_to_store`, rolling back on a store error, 502). Existing `POST /shipping/zones`, `POST /shipping/zones/{id}/rates` stay for single additions and now accept `method_type`/`conditions`.
- `PATCH /shipping/rates/{id}` (existing, active toggle) extended with `name, rate, free_over, conditions, sla_*`. For a store-sourced rate the change is pushed to the store first (open decision 2), else 409 "Managed by {store}".
- `POST /shipping/validate` → validates the tenant's whole configuration → `{ok, issues: [{zone_id, rate_id, code, message, severity}]}`.

## Validation rules (before activation; `active=true` is refused while any `error` exists)
- error: zone with no countries and not rest-of-world; a country in two active zones of the same source (overlap); zone with no active method; negative rate; `min_subtotal` ≥ `max_subtotal`; `sla_days_min` > `sla_days_max`; free_shipping with no threshold **and** another paid method in the same zone without a reason flag (warns, see below); store currency ≠ tenant currency.
- warning: free shipping with no minimum; carrier-calculated method with no carrier connected; cost formula imported; pickup method with no instructions.
- Validation results are stored on each row (`metadata.validation`) and shown in the UI.

## Sync status, monitoring, audit
- `integrations.last_sync_at` / `last_error` for the store integration, plus `integrations.metadata.shipping_sync = {last_success_at, status, counts, errors: [last 20], unsupported}`.
- Audit: `shipping.detected`, `shipping.synced`, `shipping.sync_failed`, `shipping.setup_completed`, `shipping_zone.create`, `shipping_rate.create|update|enable|disable`, `shipping.pushed_to_store`. Each audit row carries `source` and counts, never credentials.

## Open decisions (recommendation first)
1. **Schema change.** *Recommend:* the additive DDL above. *Alternative:* keep the store mapping in `integrations.metadata.shipping_map` and squeeze method type/conditions into names — not reliable.
2. **Sync direction.** *Recommend:* two-way for supported fields — the store is the source of truth on import; edits made here to a store-sourced rate are pushed to the store first (WooCommerce: full; Shopify: `deliveryProfileUpdate` on rate price/name/conditions/active) and refused (409) for what the API can't write. *Alternative (smaller):* import-only; store-sourced rows are read-only here ("Edit in Shopify").
3. **Shopify 24-hour tokens.** *Recommend:* add client-credentials refresh now (needed for any store created after 2026-01-01). It touches the SPEC-BE-052 Shopify form (2 new optional fields) — SPEC-BE-052 gets an amendment note.
4. **Re-sync frequency.** *Recommend:* every 6 hours + on connect + on demand. Webhooks (Shopify has no shipping-profile webhook) are out of scope.

## Acceptance criteria (live Postgres, rolled-back transaction, store APIs answered by `httpx.MockTransport`)
1. **A:** Shopify fixture with 2 profiles / 3 zones / flat + free-over-threshold + carrier-calculated + pickup → `detect` previews them; `sync` creates the documented rows (method types, conditions, rest-of-world); re-sync is idempotent; a method removed from the fixture → deactivated. Same for a WooCommerce fixture (flat, free with `min_amount`, local pickup, cost formula flagged).
2. Connecting/testing a store integration triggers detect → sync automatically.
3. **B:** store with zero zones → `status.mode = "setup_required"`; `POST /shipping/setup` with a valid config creates it (and with `push_to_store` sends the documented store calls); an invalid config (overlapping countries, min > max) → 422 listing every issue, nothing written.
4. Validation blocks activating a zone with an error; warnings don't block.
5. Status endpoint reports last sync, counts, errors; a store 401 → `last_sync_status = failed`, `last_error` set, audit `shipping.sync_failed`.
6. **C** (via SPEC-BE-059): chat reads and updates shipping through these same service functions.
7. Tenant isolation; SSRF guard on store URLs; no credential in responses/logs; ruff/mypy no new errors.

## Target files
`services/shipping_service.py`, `models/shipping.py`, `schemas/shipping.py`, `api/v1/shipping.py`, `services/integration_service.py` (auto-detect hook, Shopify token refresh), `integrations/verify.py` (Shopify form fields), `integrations/shopify.py` and `integrations/woocommerce.py` (stubs become the shipping clients), `workers/tasks/sync_tasks.py`, `workers/schedules.py`, `config.py` (`SHOPIFY_API_VERSION`) + `specs/SPEC-BE-002/003.md`. No new files.
