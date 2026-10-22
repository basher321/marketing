# SPEC-FE-073: Orders and Customers pages — lifecycle, SMS confirmation, customer record

Status: IMPLEMENTED (2026-10-22). `tsc` + `next build` clean; browser E2E (headless Chrome, test backend with dev fakes) covered create order → auto SMS → signed customer reply → confirmed → processing → shipped → delivered, the customer record and Settings › SMS. Backend SPEC-BE-107, 108, 109.

## Requirements

- **Orders page `/orders`** (E-Commerce's Orders tab links here; the tab stays and shows the same list):
  - Filters: status chips (All, Placed, Waiting for confirmation, Confirmed, Processing, Shipped, Delivered,
    Returned, Cancelled, Refunded), search, date range. Paged table: number, customer, items, total,
    **status badge**, **SMS position** (Confirmed / Cancelled / Waiting / Not sent), placed.
  - **New order** drawer: customer search-or-create (name, phone, email, address), product/variant lines with
    quantity and price (defaults from the product), discount, shipping, tax, payment method/status, notes.
    The total preview is labelled "Calculated by the server on save". Sends an `Idempotency-Key`.
- **Order detail `/orders/[id]`:** items, totals, customer card (→ customer record), status badge, a
  **stage tracker** (Placed → SMS sent → Customer reply → Processing → Shipped → Delivered, with Returned /
  Cancelled branches), action buttons from `allowed_next` only (reason box for cancel/return, tracking fields
  for shipped), **Send / follow up confirmation SMS** with the SMS status and error, the SMS thread, and the
  status history (time, from → to, who: user / customer by SMS / system).
- **Customers page `/customers`:** search, paged list (name, phone, email, orders, lifetime value, last order).
  **Record `/customers/[id]`:** profile (editable), current order with badge and SMS position, order history,
  status history, SMS confirmation history, conversations (→ inbox thread).
- **Settings → SMS** card: status (`not_configured` / `no_number` / `blocked` / `ready` with the number), the
  auto-confirm toggle, language, template with placeholders and a live segment counter.
- Badge colours from tokens only. Empty, loading and error states for every list; 403/409/429 messages shown as
  returned.

## Verification

`npx tsc --noEmit`, `npm run build`, browser E2E against the running backend with dev fakes: create order →
SMS sent → simulate signed Twilio reply → confirmed shows on order and customer record.

## Files

New: `app/(app)/orders/page.tsx`, `app/(app)/orders/[id]/page.tsx`, `app/(app)/customers/page.tsx`,
`app/(app)/customers/[id]/page.tsx`, `components/orders/*`, `lib/api/orders.ts` (extend), `lib/api/customers.ts`,
`lib/api/sms.ts`, `lib/types/{orders,customers,sms}.ts`. Changed: `app/(app)/ecommerce/page.tsx`,
`app/(app)/settings/page.tsx`.
