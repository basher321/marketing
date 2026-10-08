Purpose
Implement the scheduled-posts count, matching exactly what the Marketing
page's "Scheduled Posts" card shows and the same number on the Dashboard's
Marketing engine card. The Content Calendar grid, and any scheduled-post
list or detail view, are separate, later specs.

Scope
The existing stub files for the scheduled-posts domain:
app/models/scheduled_post.py, the matching file under app/schemas/,
app/services/scheduled_post_service.py, and app/api/v1/scheduled_posts.py.
No new files or folders. No list endpoint, no create, reschedule, or
cancel action, no calendar view - only the count is in scope.

Contract
After this step: one request returns, for the caller's tenant, the count
of pending (not-yet-published) scheduled posts - the same number backing
both the Marketing page's "Scheduled Posts" card and the Dashboard's
Marketing engine card.

Functional rules
- Count = scheduled_posts rows for the caller's tenant whose status is
  pending/scheduled. Document the exact status value(s) used as a code
  comment, matching the existing status field - do not invent new values.
- Computed once by one function and reused by both call sites (Marketing
  page, Dashboard engine card) - never computed twice with different
  logic.
- Every query filters by tenant_id explicitly. If scheduled_posts has no
  direct tenant_id column and tenancy must be inferred through a related
  table (e.g. via its content asset or campaign), document that join as a
  code comment.

Edge cases
- A tenant with zero pending scheduled posts returns 0, not an error.
- A scheduled post belonging to another tenant never contributes to
  another tenant's count.

Non-functional rules
No new files or folders - fill in the four existing stub files only. Follow
the existing service pattern: plain functions, explicit db and tenant_id
parameters, no classes. Type hints on every function. No print statements -
structlog only. No test framework exists yet, so verification is manual.

Acceptance criteria
- The endpoint returns the pending scheduled-post count for the caller's
  tenant only.
- The Marketing-page-backing call and the Dashboard-engine-card-backing
  call return the identical number, from the same underlying computation.
- A tenant with zero pending scheduled posts gets 0, no error.
- A scheduled post belonging to a different tenant never affects the
  count, verified with two tenants.
- No list, create, reschedule, or cancel endpoint exists as a result of
  this spec.

Assumptions
app/models/scheduled_post.py, the matching schema file,
scheduled_post_service.py, and api/v1/scheduled_posts.py already exist as
stub files with correct signatures (per CLAUDE.md's "structurally
stubbed" list) - this spec fills their bodies in, it does not create
them. The scheduled_posts table already exists in the database.

Target files (all existing - none added, none removed):
backend/app/models/scheduled_post.py
backend/app/schemas/scheduled_post.py
backend/app/services/scheduled_post_service.py
backend/app/api/v1/scheduled_posts.py
