Purpose
Implement the Dashboard's "Revenue (24h)" card, matching exactly: total
revenue in the trailing 24 hours for the caller's tenant, and the
percentage change vs. the preceding 24-hour period.

Scope
The existing stub files for the orders domain: app/models/order.py,
app/schemas/order.py, app/services/order_service.py, and
app/api/v1/orders.py - the same four files SPEC-BE-006 uses; this spec
adds one more function and route to that domain, not a new file. No new
files or folders. No order list, detail, create, update, refund, or
fulfill endpoint exists as a result of this spec either, consistent with
SPEC-BE-006 - only the revenue (24h) figure is in scope.

Contract
After this step: a request returns, for the caller's tenant, total
revenue in the trailing 24 hours and the percentage change vs. the
preceding 24-hour period.

Functional rules
- Revenue (24h) = sum of order totals for the caller's tenant with
  placed_at in the trailing 24 hours (UTC), using the same 24-hour window
  definition SPEC-BE-006 already uses for its last_24h count.
- Percentage delta = the change vs. the preceding 24-hour period (the 24
  hours before that), computed the same way SPEC-BE-006 computes its
  delta.
- Every query filters by tenant_id explicitly, per this codebase's
  existing service convention.

Edge cases
- A tenant with zero orders in the trailing 24 hours and/or the preceding
  24-hour period returns 0 for revenue and a 0 (or documented) percent
  delta - never a division-by-zero error.
- An order belonging to another tenant never contributes to another
  tenant's revenue figure.

Non-functional rules
No new files or folders - fill in the four existing stub files only. Follow
the existing service pattern: plain functions, explicit db and tenant_id
parameters, no classes. Type hints on every function. No print statements -
structlog only. No test framework exists yet, so verification is manual.

Acceptance criteria
- The endpoint returns revenue (24h) and its percentage delta for the
  caller's tenant only.
- A tenant with zero orders in the relevant windows gets 0 revenue and a
  0 (or documented) delta, no error.
- An order belonging to a different tenant never affects the result,
  verified with two tenants.
- No list, detail, create, update, refund, or fulfill endpoint exists as
  a result of this spec.

Assumptions
app/models/order.py, the matching schema file, order_service.py, and
api/v1/orders.py already exist as stub files with correct signatures (per
CLAUDE.md's "structurally stubbed" list) and already carry SPEC-BE-006's
code - this spec adds to their bodies without disturbing that existing
code. The orders table already exists in the database.

Target files (all existing - none added, none removed):
backend/app/models/order.py
backend/app/schemas/order.py
backend/app/services/order_service.py
backend/app/api/v1/orders.py
