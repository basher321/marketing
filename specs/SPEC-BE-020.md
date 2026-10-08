Purpose
Implement per-engine pending-approval counts, matching exactly what the
Dashboard's E-Commerce and Marketing engine cards show in their "Pending
approvals" row. The Customer Service engine card does not show this row
and is out of scope. The Command Chat's "Pending Approvals" panel (the
list itself, with its approve/reject actions) is a separate, later spec.

Scope
The existing stub files for the approvals domain: app/models/approval.py,
the matching file under app/schemas/, app/services/approval_service.py,
and app/api/v1/approvals.py. No new files or folders. No approve or
reject action endpoint, no approval detail or list-with-metadata endpoint
- only the two engine-scoped counts are in scope.

Contract
After this step: a request returns, for the caller's tenant, the count of
pending approval-queue items scoped to the e-commerce engine and the
count scoped to the marketing engine.

Functional rules
- Pending count per engine = approval_queue rows for the caller's tenant
  with no decision yet, grouped by the item's subject_type. Document
  exactly how subject_type values map to "e-commerce" vs "marketing" as
  a code comment, matching the existing approval_queue subject_type
  values - do not invent new categories.
- Every query filters by tenant_id explicitly, per this codebase's
  existing service convention.

Edge cases
- A tenant with zero pending approvals for an engine returns 0 for that
  engine, not an error.
- An approval-queue item whose subject_type does not map cleanly to
  e-commerce or marketing is excluded from both counts, not guessed into
  one - document this as a code comment.
- An approval-queue item belonging to another tenant never contributes
  to another tenant's count.

Non-functional rules
No new files or folders - fill in the four existing stub files only. Follow
the existing service pattern: plain functions, explicit db and tenant_id
parameters, no classes. Type hints on every function. No print statements -
structlog only. No test framework exists yet, so verification is manual.

Acceptance criteria
- The endpoint returns the pending count for e-commerce and for
  marketing, for the caller's tenant only.
- A tenant with zero pending approvals for an engine gets 0 for that
  engine, no error.
- An approval-queue item belonging to a different tenant never affects
  the count, verified with two tenants.
- No approve, reject, or detail endpoint exists as a result of this
  spec.

Assumptions
app/models/approval.py, the matching schema file, approval_service.py,
and api/v1/approvals.py already exist as stub files with correct
signatures (per CLAUDE.md's "structurally stubbed" list) - this spec
fills their bodies in, it does not create them. The approval_queue table
already exists in the database with its existing subject_type values.

Target files (all existing - none added, none removed):
backend/app/models/approval.py
backend/app/schemas/approval.py
backend/app/services/approval_service.py
backend/app/api/v1/approvals.py
