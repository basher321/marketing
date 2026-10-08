# SPEC-BE-041: E-Commerce — Orders List

Status: IMPLEMENTED (2026-09-30), plan approved by the user; verified on live Postgres (rolled-back txn).

## Purpose
Back the E-Commerce page's **Orders** tab (SPEC-FE-026). The mockup shows only the tab label, so the columns follow the order lists in Shopify, WooCommerce and BigCommerce (order number, date, customer, channel, items, total, payment, status). They are limited to what the live `orders` table actually holds.

## Scope
In scope: one read-only, paginated, filterable list endpoint.

Not in scope: order detail page, status changes (confirm/ship/cancel/refund), editing, creating orders, export, and fulfillment/tracking updates. Status changes need their own spec because they have side effects (inventory commit and release, customer notifications).

## Contract
`GET /api/v1/orders?status=&q=&limit=25&offset=0` → 200
```
{ total: int, items: [{
    id, order_number, placed_at,            # placed_at in UTC
    customer_name: str | null,
    channel,                                # live channel_type
    item_count: int,                        # SUM(order_items.quantity)
    total: float, currency,                 # total_cents -> major units via Decimal
    payment_method: str | null, payment_status: str | null,
    status,                                 # live order_status
    tracking_number: str | null
}] }
```
- `status` (optional): one live `order_status` value (pending, confirmed, processing, shipped, delivered, cancelled, refunded). Any other value gets a 422.
- `q` (optional, 1–100 chars, trimmed): case-insensitive match on `order_number`, customer first/last name, email or phone.
- `limit` 1–100 (default 25), `offset` ≥ 0 (default 0).
- `total` is the count of all matching orders, before `limit`/`offset`.

## Functional rules
1. Tenant filtering on `orders.tenant_id`. Joined customers and order items are also filtered by tenant.
2. Order: `placed_at` descending, then `order_number` descending, so ties sort the same way every time.
3. `customer_name` = `first_name + ' ' + last_name`, trimmed. If that is empty, use email, then phone. If there's no customer (guest order, `customer_id` NULL), return null and let the frontend show "Guest". Soft-deleted customers still show their name, because it's historical order data.
4. `item_count` is computed with one grouped subquery, with no N+1 queries. An order with no items has `item_count` 0.
5. Money: `total_cents` is converted to a `float` in major units through `Decimal`, and `currency` comes from the order row.
6. `payment_status` is NULL for every dev-shop order today. It is returned as-is and never inferred.
7. The `Order` model gains mappings for the live columns this needs: `order_number`, `channel` (enum `channel_type`, `create_type=False`), `payment_method`, `payment_status`, `tracking_number`. No other columns change.

## Edge cases
- A tenant with no orders gets `{total: 0, items: []}`.
- An `offset` past the end gets `{total: N, items: []}`.
- Another tenant's orders never appear, and `total` never counts them.

## Acceptance criteria
1. Returns only the caller's tenant's orders, newest first, with every field above matching the DB row.
2. `status` filters exactly, and an invalid value returns 422.
3. `q` matches order number and customer name/email/phone, case-insensitively.
4. `total` equals the matching row count, independent of `limit`/`offset`.
5. `item_count` equals SUM(quantity) of that order's items, and the list uses no per-row queries.
6. `/orders/metrics` and `/orders/revenue-24h` are unchanged.

## Target files
- backend/app/models/order.py (map 5 more live columns)
- backend/app/schemas/order.py
- backend/app/services/order_service.py
- backend/app/api/v1/orders.py
