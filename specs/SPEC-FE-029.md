# SPEC-FE-029: E-Commerce — Shipping Tab

Status: IMPLEMENTED (2026-09-30), plan approved by the user; verified E2E in headless Edge against the running backend + live Postgres (test zone, rates and audit rows removed afterwards). Depends on SPEC-BE-043.

Implementation notes: countries show by name via the built-in Intl.DisplayNames ("BD" -> "Bangladesh"). The 403 message was checked with a simulated 403, since dev-shop has no non-manager user; the backend 403s are covered by the SPEC-BE-043 verification.

## Purpose
Fill the E-Commerce page's **Shipping** tab. It follows Shopify's "Shipping zones & rates": one card per zone (where you ship), each with a table of its rates.

## Functional rules
1. **Header row:** "N zones", plus "+ New zone" (`.btn .btn-sm`) which opens an inline form: name, country codes (comma-separated, for example "BD"), and regions (comma-separated, optional).
2. **Zone card** (`.card`): the zone name in bold, "Bangladesh · Dhaka, Chattogram" muted below (country codes with regions, or "All regions"), and a table of its rates.
3. **Rate columns:** Rate name, Carrier, Price ("Free" when 0, otherwise ৳ formatting), Free over ("৳2,000" or "—"), Delivery ("1–2 days", "3 days", or "—"), Order cutoff ("HH:MM" or "—"), Status badge (active → success, inactive → neutral), and Enable/Disable.
4. **"+ Add rate"** on each zone card opens an inline form with name, carrier, price, free-over, min and max days, and cutoff time. The frontend checks match the backend's, and backend 422 messages are shown inline.
5. Enable/Disable calls `PATCH /shipping/rates/{id}`. A 403 on any write shows "Only managers and above can change shipping settings."
6. A zone with no rates shows "No rates yet" inside its card. Loading, empty ("No shipping zones yet — add a zone to start offering delivery.") and error states.

## Acceptance criteria (verified E2E)
1. The cards and rates match `shipping_zones` and `shipping_policies` in the DB, with money in major units.
2. Creating a zone and a rate through the UI persists exactly those rows (cents, arrays, time) plus audit rows. Toggling flips `active`. The test rows are deleted afterwards unless the user wants to keep them.
3. Invalid input (for example max days < min days) shows an error and writes nothing.

## Target files
- app/(app)/ecommerce/page.tsx
- components/ecommerce/shipping-zones.tsx (new)
- lib/api/shipping.ts (new)
- lib/types/shipping.ts (new)
