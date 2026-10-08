# SPEC-BE-042: E-Commerce — Pricing Rules (realign + list/create/toggle)

Status: IMPLEMENTED (2026-09-30), plan approved by the user; verified on live Postgres (rolled-back txn).

## Purpose
Back the E-Commerce page's **Pricing Rules** tab (SPEC-FE-028). The existing `PricingRule` model, schema and service were written for an imagined schema (`rule_type` string, `actions`, `is_active`), so `GET/POST /pricing/rules` fail against the live `pricing_rules` table. This spec realigns them and provides what automatic-discount screens usually offer (Shopify Discounts, WooCommerce Dynamic Pricing): list, create, enable/disable.

## Scope
In scope: realign the model to the live table; `GET` list; `POST` create; `PATCH` enable/disable.

Not in scope: applying rules to prices at checkout or order time. The existing `evaluate_price()` is unused and incompatible with the live table, so it is removed; a real pricing engine gets its own spec. Also out of scope: delete, full edit, and creating `tiered`, `category` or `tag` rules. Those can still appear in the list if they exist in the DB.

## Live table (authoritative)
`pricing_rules`: name, description, scope `pricing_scope` (sku, category, all, tag), scope_ids uuid[], rule_type `pricing_rule_type` (percent_discount, fixed_discount, tiered, fixed_price), value numeric, min_quantity, conditions jsonb, starts_at, ends_at, priority, enabled, created_by.

## Contract
`GET /api/v1/pricing/rules` → 200 `{ count, currency, items: [PricingRuleRead] }`
```
PricingRuleRead = { id, name, description, rule_type, value: float, scope, scope_count: int,
  min_quantity, starts_at, ends_at, priority, enabled,
  state: "active" | "scheduled" | "expired" | "disabled" }
```
- `currency` is the tenant's currency (`tenants.currency`). Fixed amounts are in that currency.
- `scope_count` = `len(scope_ids)`, which lets the frontend show "3 products". For `all` it is 0.

`POST /api/v1/pricing/rules` (manager+) → 201 `PricingRuleRead`
```
{ name (1-255), description?, rule_type: percent_discount | fixed_discount | fixed_price,
  value > 0 (percent_discount: <= 100), scope: all | sku,
  product_ids: uuid[] (required non-empty when scope = sku, must be [] when all),
  min_quantity? >= 1, starts_at?, ends_at? (> starts_at), priority 0-1000 (default 0) }
```
`PATCH /api/v1/pricing/rules/{id}` (manager+) with body `{ enabled: bool }` → 200 `PricingRuleRead`. Another tenant's rule or an unknown id returns 404.

## Functional rules
1. **`value` units:** a percentage for `percent_discount`. For `fixed_discount`/`fixed_price` it is an amount in **major units** of the tenant currency, since the column is `numeric`, not `*_cents`. This mapping is documented as a code comment.
2. **`scope = sku`:** `scope_ids` stores **product ids**, since `products.sku` is the SKU the Products tab shows. Each id must be a non-deleted product of the same tenant; otherwise the request gets a 422 that names the bad ids.
3. **`state`** is derived at request time, in UTC. `disabled` if `enabled` is false. Otherwise `scheduled` if `starts_at` > now, `expired` if `ends_at` <= now, else `active`.
4. List order: `enabled` first, then `priority` descending, then `created_at` descending.
5. `created_by` = the acting user. Timestamps come back in UTC.
6. Create and toggle each write an `audit_log` entry through `write_audit_log()` (`pricing_rule.create` and `pricing_rule.enable`/`pricing_rule.disable`) in the same commit.
7. Validation lives in the Pydantic schemas. The service only does the tenant/product ownership checks.

## Acceptance criteria
1. `GET` returns only this tenant's rules, with the correct `state` for all four cases, and an empty list for a tenant with none.
2. `POST` persists a row matching the input exactly (enum values, `scope_ids` = product ids, `created_by`) plus one audit row. A viewer or agent gets 403, invalid input gets 422, and another tenant's product id gets 422.
3. `PATCH` flips `enabled` and writes an audit row. Another tenant's rule returns 404.
4. `evaluate_price` is removed, and nothing else referenced it.

## Target files
- backend/app/models/pricing.py
- backend/app/schemas/pricing.py
- backend/app/services/pricing_service.py
- backend/app/api/v1/pricing.py
