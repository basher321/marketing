Purpose
Implement the Pending Approvals list, matching exactly what the Command
Chat's "Pending Approvals (N)" panel shows: each pending item's human-
readable title, its originating engine, and how long ago it was
requested, for the caller's tenant, plus the total count in the panel
heading.

Scope
The existing stub files for the approvals domain: app/models/approval.py,
app/schemas/approval.py, app/services/approval_service.py, and
app/api/v1/approvals.py - the same four files SPEC-BE-020 and
SPEC-BE-024 use; this spec adds a list function and route to that
domain, not new files. No new files or folders. No approve/reject action
(already covered by SPEC-BE-024), no plan/action generation - only the
list view is in scope.

Contract
After this step: a request returns, for the caller's tenant, every
pending approval-queue item with a human-readable title, its originating
engine, and the elapsed time since it was requested, ordered most
recently requested first, plus a total count matching the number of
items returned.

Functional rules
- List endpoint returns pending approval_queue items for the caller's
  tenant only, ordered by requested_at descending.
- Each item's human-readable title is generated from a small, documented
  set of title templates keyed by subject_type - never fabricate a
  specific detail (a product name, an amount, a person's name) that
  isn't present in the underlying item's own stored data.
- Each item's engine label reuses SPEC-BE-020's existing subject_type-
  to-engine mapping directly - it is not redefined or duplicated here.
- Elapsed time is computed from requested_at to now, not hardcoded.
- Every query filters by tenant_id explicitly, per this codebase's
  existing service convention.

Edge cases
- A tenant with zero pending approvals returns an empty list and a count
  of 0, not an error.
- A subject_type with no matching title template is either excluded or
  shown with a documented generic title - document which, as a code
  comment.
- An approval-queue item belonging to another tenant never appears in
  another tenant's list.

Non-functional rules
No new files or folders - fill in the four existing stub files only. Follow
the existing service pattern: plain functions, explicit db and tenant_id
parameters, no classes. Type hints on every function. No print statements -
structlog only. No test framework exists yet, so verification is manual.

Acceptance criteria
- The list endpoint returns only the caller's tenant's pending items,
  most recently requested first, each with title, engine, and elapsed
  time; the count matches the number of rows returned.
- The engine label matches SPEC-BE-020's existing mapping exactly, not a
  second, different mapping.
- No fabricated detail appears in any generated title.
- A tenant with zero pending approvals gets an empty list and count 0, no
  error.
- An approval-queue item belonging to a different tenant never appears
  in another tenant's list, verified with two tenants.
- No approve, reject, or plan-generation endpoint exists as a result of
  this spec.

Assumptions
app/models/approval.py, the matching schema file, approval_service.py,
and api/v1/approvals.py already exist as stub files with correct
signatures (per CLAUDE.md's "structurally stubbed" list) and already
carry SPEC-BE-020's and SPEC-BE-024's code - this spec adds to their
bodies without disturbing that existing code.

Target files (all existing - none added, none removed):
backend/app/models/approval.py
backend/app/schemas/approval.py
backend/app/services/approval_service.py
backend/app/api/v1/approvals.py
