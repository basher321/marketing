# SPEC-BE-107: Order lifecycle — create orders, allowed status changes, status history

Status: IMPLEMENTED (2026-10-22), approved 2026-10-21. Verified on the local DB, rolled back: AC1-AC5 in a 61-check run shared with SPEC-BE-108 (61/61). ruff/mypy at the baseline. Deviation: order lines are flushed one by one (insertmanyvalues can't match String(36) ids to native uuids). Production DDL: `backend/deploy/sql/2026-10-21_orders_sms_expenses.sql`, applied by the cPanel `setup.sh`. The UI part is SPEC-FE-073. The SMS confirmation
step is SPEC-BE-108.

## The problem

- `GET /orders` lists orders (SPEC-BE-041), but nothing creates an order, changes its status or records
  who changed it. There is no Orders page.
- The live `order_status` enum is pending, confirmed, processing, shipped, delivered, cancelled, refunded.
  The master prompt (2026-10-21) needs two more stages: **waiting for the customer's confirmation** and
  **returned**.

## Decisions

- Stage 1 "Order placed" = `pending`. Stage 2 "Confirmation SMS sent" = the new `awaiting_confirmation`.
  Stage 3 = `confirmed` or `cancelled`. Stage 4 = processing → shipped → delivered, and the new `returned`.
  `refunded` stays as it is.
- Inventory is **not** changed by this spec. Reserving stock on order is a separate decision; it is listed
  under "Not in this spec".
- Orders synced from Shopify/WooCommerce keep their store's status; this spec covers orders created in
  PilotSonic (`channel` any of the live `channel_type` values, default `web`).

## Additive DDL

```sql
ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'awaiting_confirmation' AFTER 'pending';
ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'returned' AFTER 'delivered';

CREATE TABLE order_status_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  order_id uuid NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  from_status text,                       -- null for the "placed" event
  to_status text NOT NULL,
  actor_type text NOT NULL CHECK (actor_type IN ('user','system','customer_sms','store_sync')),
  actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  reason text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX order_status_events_order_idx ON order_status_events (tenant_id, order_id, created_at);
CREATE UNIQUE INDEX orders_idempotency_idx ON orders (tenant_id, (metadata->>'idempotency_key'))
  WHERE metadata ? 'idempotency_key';
```

## Requirements

- **FR1 Allowed changes** (one table in `order_service.TRANSITIONS`, documented in a comment):

  | From | To |
  |---|---|
  | pending | awaiting_confirmation (only via SPEC-BE-108), confirmed, cancelled |
  | awaiting_confirmation | confirmed, cancelled |
  | confirmed | processing, cancelled |
  | processing | shipped, cancelled |
  | shipped | delivered, returned |
  | delivered | returned, refunded |
  | returned | refunded |
  | cancelled, refunded | — (final) |

  Anything else → 409 with "An order that is `<from>` can't become `<to>`." The same status → 409.
- **FR2 Who.** Create and the normal forward steps: agent+. Cancel after `confirmed`, `returned` and
  `refunded`: manager+ (403 otherwise). Viewer: read only.
- **FR3 `POST /orders`** (agent+, `Idempotency-Key` header optional):
  - Body: `customer` = `{id}` or `{name, phone?, email?, address?}` (phone or email required); `items[]` =
    `{variant_id | product_id, quantity ≥ 1, unit_price?}`; `discount?`, `shipping?`, `tax?` (major units);
    `payment_method?`, `payment_status?` (`unpaid` default, `paid`, `cod`); `channel?`; `notes?`.
  - Customer: an `id` must belong to the company (404). Otherwise found by phone (E.164, SPEC-BE-108's
    normaliser) then email, else created.
  - Items: the variant/product must belong to the company and not be archived (422 per line). `unit_price`
    defaults to the variant price, then the product price. Each `order_items.product_snapshot` stores sku,
    title, variant label and **`cost_cents`** at that moment (variant cost, else product cost, else null),
    which SPEC-BE-110 uses for cost of goods.
  - Totals are computed on the server: subtotal = Σ line totals; total = subtotal − discount + shipping + tax.
    The client never sends a total. Currency = the company's currency.
  - `order_number`: the company's next number (`max + 1`, starting at 1001), under a per-company
    `pg_advisory_xact_lock`.
  - The customer's `order_count`, `lifetime_value_cents`, `first_order_at`, `last_order_at` are updated.
  - One `order_status_events` row (`null → pending`, actor user) and an audit entry.
  - Same `Idempotency-Key` again → the first order, 200, nothing new.
  - After commit, SPEC-BE-108's auto-confirmation runs when the company has it on.
- **FR4 `GET /orders/{id}`** → the order, items, customer summary, `status_history[]` (oldest first, with
  actor name), `confirmation` (SPEC-BE-108) and `allowed_next[]` (statuses this user may set now). Another
  company's id → 404.
- **FR5 `POST /orders/{id}/status`** `{to, reason?, tracking_number?, tracking_url?}`: checks FR1/FR2, sets
  `fulfilled_at` (shipped), `delivered_at`, `cancelled_at`; writes the event and an audit entry; row-locks the
  order (`SELECT … FOR UPDATE`) so two clicks can't both apply. `cancelled` and `returned` need a reason.
- **FR6 `PATCH /orders/{id}`** (agent+): notes, tags, tracking, shipping address, payment status. Never
  status or totals. Audited.
- **FR7 `GET /orders`** keeps its shape and adds `confirmation_state` per row and the new statuses to the
  `status` filter. `GET /orders/metrics` is unchanged.
- **FR8 Command Chat.** `InspectOrdersParams.status` accepts the two new values (see SPEC-BE-114).

## Acceptance criteria (live DB, rolled back)

1. Creating an order with a new customer creates the customer, items with cost snapshots, server totals,
   number 1001, one history event; the same Idempotency-Key returns the same order.
2. Every allowed change in FR1 works and writes history with the actor; every other one is 409.
3. An agent cancelling a confirmed order is 403; a manager can.
4. Another company's order/customer/product id is 404 everywhere.
5. Two concurrent status changes: one wins, the other is 409.

## Files

`models/order.py` (+ `OrderStatusEvent`), `schemas/order.py`, `services/order_service.py`,
`api/v1/orders.py`, `ai/command_actions.py` (status literal only).

## Not in this spec

Reserving/decrementing stock on order; editing items after creation; partial shipments; Shopify/Woo order sync.
