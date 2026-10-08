Purpose
Implement the Analytics page's Sales summary and Revenue-by-day chart,
matching exactly: Revenue (7d) with its percentage delta, Orders (7d),
AOV, Refund Rate with its delta, and the 7-bar Revenue by Day chart. The
Ads, Engagement, and Customer Service analytics tabs render no data in
the HTML and are out of scope.

Scope
The existing stub files for the analytics domain: app/models/analytics.py,
the matching file under app/schemas/, app/services/analytics_service.py,
and app/api/v1/analytics.py. No new files or folders. No Top Products
table (separate spec), no Ads/Engagement/Customer-Service analytics
endpoint - only the Sales tab's four cards and the Revenue by Day chart
are in scope.

Contract
After this step: one request returns, for the caller's tenant: revenue in
the trailing 7 days and its percentage change vs. the preceding 7 days,
the order count in the trailing 7 days, average order value (AOV) for the
trailing 7 days, refund rate for the trailing 7 days and its percentage-
point change vs. the preceding 7 days, and a day-by-day revenue series
covering the trailing 7 days.

Functional rules
- Revenue (7d) = sum of order totals for the caller's tenant in the
  trailing 7 days (UTC), with the percentage delta vs. the preceding
  7-day period, computed the same way SPEC-BE-006 computes its delta.
- Orders (7d) reuses SPEC-BE-006's existing order-count function directly
  - it is not recomputed independently, and must equal what that
  function returns for the same tenant at the same moment.
- AOV = revenue (7d) divided by orders (7d); a tenant with zero orders in
  that window returns AOV 0, not a division-by-zero error.
- Refund rate = refunded order count divided by total order count in the
  trailing 7 days, expressed as a percentage, with its percentage-point
  delta vs. the preceding 7-day period. Document the exact order status
  value(s) treated as "refunded" as a code comment, matching the existing
  order_status enum - do not invent a new value.
- Revenue-by-day = one revenue total per UTC calendar day for each of the
  trailing 7 days, ordered oldest to newest.
- Every query filters by tenant_id explicitly, per this codebase's
  existing service convention.

Edge cases
- A tenant with zero orders in the trailing 7 days and/or the preceding 7
  days returns 0 for every figure and a 0 (or documented) delta - never a
  division-by-zero error.
- An order belonging to another tenant never contributes to another
  tenant's figures.

Non-functional rules
No new files or folders - fill in the four existing stub files only. Follow
the existing service pattern: plain functions, explicit db and tenant_id
parameters, no classes. Type hints on every function. No print statements -
structlog only. No test framework exists yet, so verification is manual.

Acceptance criteria
- The endpoint returns revenue (7d) with delta, orders (7d), AOV, refund
  rate with delta, and a 7-value daily revenue series, for the caller's
  tenant only.
- Orders (7d) returned here is identical to what SPEC-BE-006's endpoint
  returns for the same tenant at the same moment.
- A tenant with zero orders in the relevant windows gets all-zero
  figures, no error.
- Data belonging to a different tenant never affects the result, verified
  with two tenants.
- No Top Products, Ads, Engagement, or Customer Service analytics
  endpoint exists as a result of this spec.

Assumptions
app/models/analytics.py, the matching schema file, analytics_service.py,
and api/v1/analytics.py already exist as stub files with correct
signatures (per CLAUDE.md's "structurally stubbed" list) - this spec
fills their bodies in, it does not create them. The orders and
order_items tables already exist, and SPEC-BE-006's order-count function
is importable and reusable from this service.

Target files (all existing - none added, none removed):
backend/app/models/analytics.py
backend/app/schemas/analytics.py
backend/app/services/analytics_service.py
backend/app/api/v1/analytics.py
