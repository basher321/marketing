Purpose
Implement the endpoint that turns a sent chat message into a real plan,
wiring SPEC-BE-031's intent-parsing and SPEC-BE-032's plan-generation
functions into the orchestrator domain so sending a message (SPEC-BE-023)
produces a stored plan whose actions appear in the approval queue
(SPEC-BE-020/024/025), matching the Command Chat's plan-card flow.

Scope
The existing stub files for the orchestrator domain:
app/models/orchestrator.py, app/schemas/orchestrator.py,
app/services/orchestrator_service.py, and app/api/v1/orchestrator.py -
the same four files SPEC-BE-023 uses. No new files or folders. No change
to intent-parsing (SPEC-BE-031) or plan-generation (SPEC-BE-032)
themselves - both are called as-is. No actual execution of any approved
action - that is a separate, later spec (the workflow execution engine) -
only producing and storing the plan and its approval-queue entries is in
scope.

Contract
After this step: sending a message (per SPEC-BE-023) also triggers
intent parsing and plan generation for the caller's tenant, and stores
the resulting plan as approval_queue rows (one per proposed action,
correctly counted and listed by SPEC-BE-020 and SPEC-BE-025); if intent
parsing returns a clarifying question instead, that question is returned
as the AI's reply message instead of a plan.

Functional rules
- After storing the user's message (per SPEC-BE-023, unchanged), the send
  flow calls SPEC-BE-031's intent-parsing function, then - if a valid
  intent was returned - SPEC-BE-032's plan-generation function, for the
  caller's tenant.
- If intent parsing returns a clarifying question, that question is
  stored as the AI's reply message (extending SPEC-BE-023's message
  history) and no plan/approval-queue rows are created.
- If a plan is generated, each of its proposed actions is inserted as
  one approval_queue row for the caller's tenant, with subject_type set
  per SPEC-BE-032's documented action-type-to-engine mapping - reusing
  SPEC-BE-020's existing mapping, not a new one - and a pending
  decision. An action the plan already marks "auto-approved" per an
  existing, documented policy rule is inserted already-decided
  (approved) rather than pending; document this rule as a code comment.
- A brief AI reply summarizing the plan is stored as the AI's reply
  message.
- Every mutation filters by tenant_id explicitly, per this codebase's
  existing service convention.

Edge cases
- If SPEC-BE-031 or SPEC-BE-032 raises a typed error, the send flow
  still keeps the user's stored message (per SPEC-BE-023) but stores a
  clear error/fallback AI reply instead of a plan, and creates no
  approval_queue rows.
- A plan with zero proposed actions produces no approval_queue rows and
  a reply saying so, not an error.
- Approval_queue rows created here never leak into another tenant's
  counts or lists, verified with two tenants against SPEC-BE-020 and
  SPEC-BE-025.

Non-functional rules
No new files or folders - fill in the four existing stub files only. Follow
the existing service pattern: plain functions, explicit db and tenant_id
parameters, no classes. Type hints on every function. No print statements -
structlog only, following SPEC-BE-031's/SPEC-BE-032's existing
observability convention for the LLM calls, not re-logged differently
here. No test framework exists yet, so verification is manual.

Acceptance criteria
- Sending a message that parses to a valid intent produces the plan's
  proposed actions as approval_queue rows, correctly counted by
  SPEC-BE-020 and listed by SPEC-BE-025.
- Sending a message that fails intent validation stores the clarifying
  question as the AI's reply, with no approval_queue rows created.
- An action marked auto-approved per the documented policy is inserted
  already-decided, not pending.
- If SPEC-BE-031 or SPEC-BE-032 fails, the user's message is still
  stored, a fallback AI reply is stored, and no approval_queue rows are
  created.
- Approval_queue rows created here never affect another tenant, verified
  with two tenants.
- No action-execution endpoint exists as a result of this spec.

Assumptions
app/models/orchestrator.py, the matching schema file,
orchestrator_service.py, and api/v1/orchestrator.py already exist as
stub files with correct signatures (per CLAUDE.md's "structurally
stubbed" list) and already carry SPEC-BE-023's code - this spec adds to
their bodies without disturbing that existing code. SPEC-BE-031's and
SPEC-BE-032's functions are implemented and importable. SPEC-BE-020's
engine mapping and SPEC-BE-024's/SPEC-BE-025's approval mechanics already
exist.

Target files (all existing - none added, none removed):
backend/app/models/orchestrator.py
backend/app/schemas/orchestrator.py
backend/app/services/orchestrator_service.py
backend/app/api/v1/orchestrator.py
