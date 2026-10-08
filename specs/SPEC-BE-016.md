Purpose
Implement the Analytics page's Top Products table, matching exactly:
Product, Units Sold, Revenue, and Trend, ranked for the caller's tenant.

Scope
The existing stub files for the analytics domain: app/models/analytics.py,
the matching file under app/schemas/, app/services/analytics_service.py,
and app/api/v1/analytics.py - the same four files SPEC-BE-015 uses; this
spec adds one more function and route to that domain, not a new file. No
new files or folders. No product-detail drill-down, no per-channel
breakdown - only the ranked table is in scope.

Contract
After this step: one request returns, for the caller's tenant, the top
products by revenue in the trailing 7 days, each with product name, units
sold, revenue, and the percentage change in that product's revenue vs.
the preceding 7-day period.

Functional rules
- Ranks products by revenue (sum of order_items line revenue) in the
  trailing 7 days (UTC) for the caller's tenant, descending.
- For each ranked product: units sold = sum of order_items quantity in
  the trailing 7 days; revenue = sum of order_items line revenue in the
  trailing 7 days; trend = percentage change in that product's revenue
  vs. the preceding 7-day period.
- The number of rows returned is a documented, fixed limit (e.g. top 10) -
  document the exact value as a code comment; never return every
  product unranked.
- Only order items from completed/paid orders count toward units sold and
  revenue. Document the exact order status value(s) used as a code
  comment, matching the existing order_status enum - refunded or
  cancelled order items are excluded.
- Every query filters by tenant_id explicitly, per this codebase's
  existing service convention.

Edge cases
- A tenant with no qualifying order activity in the trailing 7 days
  returns an empty list, not an error.
- A product with revenue in the trailing 7 days but none in the preceding
  7-day period gets a documented trend value (not a division-by-zero
  error) - document the exact rule as a code comment.
- Order items belonging to another tenant never contribute to another
  tenant's ranking.

Non-functional rules
No new files or folders - fill in the four existing stub files only. Follow
the existing service pattern: plain functions, explicit db and tenant_id
parameters, no classes. Type hints on every function. No print statements -
structlog only. No test framework exists yet, so verification is manual.

Acceptance criteria
- The endpoint returns the caller's tenant's top products by revenue in
  the trailing 7 days, each with product name, units sold, revenue, and
  trend.
- The row limit and the zero-prior-period trend rule are both documented
  as code comments.
- A tenant with no qualifying order activity in the trailing 7 days gets
  an empty list, no error.
- Order items belonging to a different tenant never affect the ranking,
  verified with two tenants.
- No product-detail or per-channel-breakdown endpoint exists as a result
  of this spec.

Assumptions
app/models/analytics.py, the matching schema file, analytics_service.py,
and api/v1/analytics.py already exist as stub files with correct
signatures (per CLAUDE.md's "structurally stubbed" list) and already
carry SPEC-BE-015's Sales-summary code - this spec adds to their bodies,
it does not create or replace them. The orders, order_items, and products
tables already exist.

Target files (all existing - none added, none removed):
backend/app/models/analytics.py
backend/app/schemas/analytics.py
backend/app/services/analytics_service.py
backend/app/api/v1/analytics.py
