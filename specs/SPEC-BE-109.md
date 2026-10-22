# SPEC-BE-109: Customer record — profile, orders, conversations, SMS and status history

Status: IMPLEMENTED (2026-10-22). Verified with BE-110 in a 44-check rolled-back run (44/44). UI in SPEC-FE-073.

## The problem

`GET /customers` is a flat list and `POST /customers` creates one (SPEC-BE-007). Nothing shows one customer's
orders, messages, SMS confirmations and order history together.

## Requirements

- **FR1 `GET /customers`** keeps its response shape (a list) and gains optional `q` (name, phone, email),
  `limit` (default 50, ≤ 200) and `offset`. `X-Total-Count` header carries the total.
- **FR2 `GET /customers/{id}`** → `{customer: {id, name, phone, email, address (default_address), city,
  country_code, tags, accepts_marketing, sms_opt_out, order_count, lifetime_value, currency, created_at},
  current_order: {id, order_number, status, confirmation_state} | null` (the newest order that isn't final),
  `orders[]` (newest first: number, status, confirmation_state, total, placed_at, tracking),
  `status_history[]` (all the customer's `order_status_events`, newest first, ≤ 100, with order number and
  actor), `sms[]` (≤ 100, direction, kind, body, status, interpreted, at, order number),
  `conversations[]` (channel, status, topic, last message preview and time, unread count)}`. Another
  company's id → 404. Deleted customers (`deleted_at`) → 404.
- **FR3 `PATCH /customers/{id}`** (agent+): name, phone, email, address, tags, accepts_marketing. Phone is
  normalised (SPEC-BE-108 FR3); email stays unique per company (409). Audited.
- **FR4 Consistency.** Every order status change (SPEC-BE-107) and SMS (SPEC-BE-108) is written in the same
  transaction as the order change, so the record never shows a status the order doesn't have.

## Acceptance criteria (live DB, rolled back)

1. A customer with two orders, SMS and a conversation returns all of them, newest first, with the right
   current order.
2. `q` finds by phone digits, name or email; paging works.
3. Another company's customer is 404; a duplicate email on PATCH is 409.

## Files

`schemas/customer.py`, `services/customer_service.py`, `api/v1/customers.py`.
