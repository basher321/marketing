# SPEC-BE-061: Shipping zones may share a country when their regions differ

Status: IMPLEMENTED (2026-10-02), plan approved. Verified on the live DB (rolled-back transaction, real tokens, nothing persisted).

Implementation notes (found while verifying; same file, in scope):
- `setup()` saved every wizard zone with `regions=[]`, discarding the regions the user typed. It now saves them.
- An existing zone's own problem blocked the wizard's Review and Activate. For example, a zone added with "+ Add zone" and no methods yet caused it. The guided setup now blocks only on issues in the zones being set up, including their overlaps with existing zones. Existing zones' issues still show on the Shipping tab.
- Existing zones are validated first, so an overlap is reported on the new zone.
- Min > max delivery days is still rejected by the request schema (422) before validation, as before. Amends SPEC-BE-058's overlap rule. No frontend change is needed (SPEC-FE-040's wizard already sends `regions`).

## Problem (reproduced 2026-10-02 on the live DB, rolled-back transaction)
On E-Commerce › Shipping › Set up shipping, the **Review** step reports "BD is also in the active zone “Inside Dhaka”" and **Activate** is refused (422) whenever two zones share a country. That happens even when their regions differ: "Inside Dhaka" (Dhaka) + "Outside Dhaka" (Chattogram, Sylhet) is refused. That split is the setup the wizard's own placeholders suggest ("e.g. Inside Dhaka", "Dhaka, Gazipur"). It also blocks adding any second zone for a country that already has one. Single-zone setups and every method type (flat, free, carrier, pickup, local delivery) pass, so the methods themselves are fine.

Cause: `shipping_service.validate_config` keys the overlap check on (source, country) only and ignores `regions`. `_activation_errors` (used by `POST /shipping/zones`) doesn't pass the zone's regions into the check at all.

## Functional rules
1. Two **active local** zones overlap on a country only when both list it, **and** one of these holds:
   - either zone has no regions for it (that zone covers the whole country), or
   - their region lists share a name. Names are compared trimmed and case-insensitively, so "Dhaka" = "dhaka ".
2. An overlap is still an error, and the message names the shared regions: `BD (Dhaka) is also in the active zone “X”.` When a whole-country zone is involved, it says `BD is also covered by the active zone “X”.`
3. Store-sourced zones (Shopify/WooCommerce) stay exempt, as today. Inactive zones never count.
4. `POST /shipping/zones` and `POST /shipping/setup` (and its `/validate` dry run) use the same rule. The new zone's `regions` are passed into the check.
5. A zone's regions are matched as a flat list. Regions are not mapped to their countries, which is fine when a zone has one country. For a multi-country zone with regions, any shared region name counts as an overlap. That's the conservative choice, documented as a code comment.

## Acceptance criteria (live DB, rolled-back transaction, `TestClient`, real tokens)
1. Inside Dhaka [BD: Dhaka] + Outside Dhaka [BD: Chattogram, Sylhet] in one setup → validate `ok: true`, setup 201, 2 zones.
2. [BD: Dhaka] + [BD: dhaka ] → error naming Dhaka. [BD: Dhaka] + [BD, no regions] → error.
3. An existing active zone [BD: Dhaka] then `POST /shipping/zones` [BD: Gazipur] → 201, and [BD: Dhaka] → 422.
4. An inactive zone doesn't block. Store-sourced zones don't block.
5. Every other SPEC-BE-058 validation rule behaves as before (regression run of the previous cases: no countries, negative price, min ≥ max, SLA order, the free-shipping and carrier warnings).
6. ruff/mypy add no new errors.

## Target files
- backend/app/services/shipping_service.py (`validate_config`, `_activation_errors`, `create_zone`, `_zone_struct` if it omits regions)
