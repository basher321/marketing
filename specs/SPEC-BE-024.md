Purpose
Implement approving and rejecting approval-queue items, matching the
Command Chat plan card's "Approve All" and "Reject All" actions (and, by
extension, deciding one action at a time). Generating a plan's proposed
actions - intent parsing, planning - is a separate, later spec; this spec
only decides on approval-queue items that already exist.

Scope
The existing stub files for the approvals domain: app/models/approval.py,
app/schemas/approval.py, app/services/approval_service.py, and
app/api/v1/approvals.py - the same four files SPEC-BE-020 uses; this
spec adds functions and routes to that domain, not new files. No new
files or folders. No plan/action generation, no execution of an approved
action (actually running the workflow/action it represents) - only
recording the approve/reject decision is in scope.

Contract
After this step: a request approves or rejects one approval-queue item
for the caller's tenant, recording who decided and when; a request
approves (or rejects) every still-pending item belonging to one group
(e.g. a plan id) in a single call, matching the "Approve All"/"Reject
All" buttons.

Functional rules
- Approve-one and reject-one each update exactly one approval_queue row's
  decision, decided_by, and decided_at for the caller's tenant - the row
  must currently be pending; deciding an already-decided item is
  rejected with a clear error, not silently overwritten.
- Approve-all/reject-all applies the same decision to every still-pending
  approval_queue item sharing one subject_id for the caller's tenant, in
  one call - already-decided items in that group are left untouched, not
  re-decided.
- An optional reason is accepted on reject, matching the approval_queue's
  existing reason column.
- Every query and mutation filters by tenant_id explicitly, per this
  codebase's existing service convention.
- Every decision writes one entry via the existing write_audit_log()
  function in core/audit.py.

Edge cases
- Deciding an item that does not belong to the caller's tenant returns
  404, not the other tenant's row and not a permission error that would
  confirm the row exists.
- Deciding an already-decided item is rejected with a clear error;
  nothing changes.
- Approve-all/reject-all on a group with zero pending items succeeds with
  zero items changed, not an error.

Non-functional rules
No new files or folders - fill in the four existing stub files only. Follow
the existing service pattern: plain functions, explicit db and tenant_id
parameters, no classes. Type hints on every function. No print statements -
structlog only. No test framework exists yet, so verification is manual.

Acceptance criteria
- Approve-one and reject-one update exactly one pending item's decision,
  decided_by, and decided_at, for the caller's tenant only.
- Approve-all/reject-all decides every still-pending item in one group,
  leaving already-decided items untouched.
- Deciding an already-decided item is rejected, nothing changes.
- Deciding an item belonging to a different tenant returns 404, verified
  with two tenants.
- Every decision produces exactly one new audit_log row.
- No plan/action-generation or action-execution endpoint exists as a
  result of this spec.

Assumptions
app/models/approval.py, the matching schema file, approval_service.py,
and api/v1/approvals.py already exist as stub files with correct
signatures (per CLAUDE.md's "structurally stubbed" list) and already
carry SPEC-BE-020's code - this spec adds to their bodies without
disturbing that existing code. Approval-queue rows are assumed to already
exist (created by a separate, later plan-generation spec) - this spec is
tested against existing or seeded rows, not ones it creates itself.

Target files (all existing - none added, none removed):
backend/app/models/approval.py
backend/app/schemas/approval.py
backend/app/services/approval_service.py
backend/app/api/v1/approvals.py
