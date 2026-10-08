Purpose
Implement order count metrics, matching exactly what the frontend HTML shows:
the Dashboard's "Orders" card, the E-Commerce engine card's "Orders (24h)"
count, and the Analytics page's "Orders (7d)" count with its percentage
delta. The HTML never renders an actual orders table or order detail view -
only these counts - so nothing beyond counts is in scope.

Scope
The existing stub files for the orders domain: app/models/order.py,
app/schemas/order.py, app/services/order_service.py, and
app/api/v1/orders.py. No new files or folders. No order list endpoint, no
order detail endpoint, no create/update/refund/fulfill logic - none of that
is rendered anywhere in the HTML.

Contract
After this step: a single request returns, for the caller's tenant, the
total order count, the count in the last 24 hours, the count in the last 7
days, and the percentage change of the last-7-day count versus the
preceding 7-day period.

Functional rules
- One endpoint returns four numbers for the caller's tenant only: total
  order count (all time), count in the last 24 hours, count in the last 7
  days, and the percentage delta of the last-7-day count versus the 7 days
  before that.
- All four numbers are computed only from the orders table, filtered by
  tenant_id - no other table is touched.
- Counts are computed against the order's placed_at timestamp, in UTC,
  consistent with how timestamps are stored elsewhere in this codebase.
- No endpoint in this spec lists individual orders, returns order detail,
  or creates, updates, refunds, or fulfills an order.

Edge cases
- A tenant with zero orders returns all counts as 0 and the percentage
  delta as 0 - not a division-by-zero error.
- Counts for one tenant never include another tenant's orders.

Non-functional rules
No new files or folders - fill in the four existing stub files only. Follow
the existing service pattern: plain functions, explicit db and tenant_id
parameters, no classes. Type hints on every function. No print statements -
structlog only. No test framework exists yet, so verification is manual.

Acceptance criteria
- The endpoint returns total, last_24h, last_7d, and the 7-day percentage
  delta for the caller's tenant only.
- A tenant with zero orders gets all-zero counts and a 0 percent delta, no
  error.
- Calling the endpoint as tenant A never reflects tenant B's order counts,
  verified with two tenants.
- No list, detail, create, update, refund, or fulfill endpoint exists as a
  result of this spec.

Assumptions
The orders table already exists per the database schema. app/models/order.py,
app/schemas/order.py, app/services/order_service.py, and
app/api/v1/orders.py already exist as stub files with correct signatures
(per CLAUDE.md's "structurally stubbed" list) - this spec fills their
bodies in, it does not create them.

Target files (all existing - none added, none removed):
backend/app/models/order.py
backend/app/schemas/order.py
backend/app/services/order_service.py
backend/app/api/v1/orders.py
