# SPEC-BE-043: E-Commerce — Shipping Zones & Rates (realign + list/create/toggle)

Status: IMPLEMENTED (2026-09-30), plan approved by the user; verified on live Postgres (rolled-back txn).

Implementation note: country codes are validated as two letters (A-Z) after upper-casing, not against a full ISO 3166 list, since no country-list dependency is installed.

## Purpose
Back the E-Commerce page's **Shipping** tab (SPEC-FE-029). The existing models are misaligned with the live DB. The model has `ShippingPolicy.description`, and `ShippingZone.policy_id`/`rate` pointing the wrong way. In the live DB, **a zone has many policies (rates)** through `shipping_policies.zone_id`. So `GET/POST /shipping-policies` fail today. This spec follows the Shopify and WooCommerce pattern: shipping **zones** (where you ship), each with **rates** (carrier, price, free-over threshold, delivery time).

## Scope
In scope: realign both models; list zones with their nested rates; create a zone; create a rate in a zone; enable/disable a rate.

Not in scope: calculating shipping on orders, delete, full edit, and editing zone regions after creation.

## Contract
The router prefix changes from `/shipping-policies` to `/shipping`. No frontend code calls the old path.

`GET /api/v1/shipping/zones` → 200
```
{ currency, zones: [{ id, name, country_codes: [str], regions: [str], active,
    rates: [{ id, name, carrier, rate: float, free_over: float | null,
              sla_days_min, sla_days_max, cutoff_time: "HH:MM" | null, active }] }] }
```
`POST /api/v1/shipping/zones` (manager+) → 201 zone (with `rates: []`)
`{ name (1-255), country_codes: [ISO-3166 alpha-2, >= 1, upper-cased], regions: [str] (default []) }`

`POST /api/v1/shipping/zones/{zone_id}/rates` (manager+) → 201 rate
`{ name, carrier (1-255), rate >= 0, free_over? > 0, sla_days_min? >= 0, sla_days_max? >= sla_days_min, cutoff_time? "HH:MM" }`

`PATCH /api/v1/shipping/rates/{rate_id}` (manager+) with body `{ active: bool }` → 200 rate

Another tenant's zone or rate returns 404.

## Functional rules
1. Money: `rate_cents`/`free_over_cents` are converted to and from major units through `Decimal`, in the **tenant currency** (`tenants.currency`). The table has no currency column.
2. `regions` is stored as a JSON array of strings, for example `["Dhaka", "Chattogram"]`. It is optional, and an empty list means the whole country.
3. Zone order: `name`. Rate order within a zone: `rate_cents`, then `name`. Rates are loaded in one query, with no N+1 queries.
4. Tenant filtering on both tables. When a rate is created, the zone must belong to the caller's tenant.
5. Creating a zone or rate and toggling a rate each write an `audit_log` entry (`shipping_zone.create`, `shipping_rate.create`, `shipping_rate.enable`/`.disable`).
6. `cutoff_time` is a local time of day (the tenant's timezone) and is returned as "HH:MM".

## Acceptance criteria
1. `GET` returns this tenant's zones with their rates nested correctly and money in major units. A tenant with no zones gets `zones: []`.
2. The create endpoints persist rows that match the input exactly (cents, arrays, time) and write one audit row each. Viewer/agent gets 403, invalid input gets 422 (for example `sla_days_max < min`, or a bad country code).
3. Creating a rate in another tenant's zone returns 404. `PATCH` on another tenant's rate returns 404.
4. `PATCH` flips `active` and writes an audit row.

## Target files
- backend/app/models/shipping.py
- backend/app/schemas/shipping.py
- backend/app/services/shipping_service.py
- backend/app/api/v1/shipping.py
