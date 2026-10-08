Purpose
Implement Command Chat message history and sending, matching exactly
what the Command Chat page shows: a chronological list of user and AI
messages, and the ability to send a new user message. Intent parsing,
plan generation, and the approval workflow (the plan card and its
approve/reject buttons) are separate, later specs - this spec only
persists and lists messages.

Scope
The existing stub files for the orchestrator domain:
app/models/orchestrator.py, the matching file under app/schemas/,
app/services/orchestrator_service.py, and app/api/v1/orchestrator.py. No
new files or folders. No NLU/intent parsing, no plan generation, no
approve/reject action - only message storage and listing are in scope.

Contract
After this step: a request returns the caller's tenant's chat message
history in chronological order; a send request stores a new user message
for the caller's tenant and it appears in the next history call.

Functional rules
- List endpoint returns the caller's tenant's orchestrator messages in
  chronological order (oldest first), each with sender (user/ai), body,
  and sent timestamp.
- Send endpoint stores a new user message for the caller's tenant from
  the request body. It does not generate or store any AI response - that
  requires intent parsing and planning, which is out of scope here.
  Document this explicitly as a code comment on the send function.
- Every query and mutation filters by tenant_id explicitly, per this
  codebase's existing service convention.

Edge cases
- A tenant with no prior messages returns an empty list, not an error.
- Sending an empty message body is rejected with a validation error,
  nothing is written.
- A message belonging to another tenant never appears in another
  tenant's history.

Non-functional rules
No new files or folders - fill in the four existing stub files only. Follow
the existing service pattern: plain functions, explicit db and tenant_id
parameters, no classes. Type hints on every function. No print statements -
structlog only. No test framework exists yet, so verification is manual.

Acceptance criteria
- The list endpoint returns only the caller's tenant's messages, in
  chronological order, each with sender, body, and timestamp.
- The send endpoint stores a new user message for the caller's tenant,
  and it appears in the next list call.
- No AI response is generated or stored by the send endpoint.
- Sending an empty message body is rejected, nothing is written.
- A message belonging to a different tenant never appears in another
  tenant's history, verified with two tenants.
- No intent-parsing, plan-generation, or approve/reject endpoint exists
  as a result of this spec.

Assumptions
app/models/orchestrator.py, the matching schema file,
orchestrator_service.py, and api/v1/orchestrator.py already exist as
stub files with correct signatures (per CLAUDE.md's "structurally
stubbed" list) - this spec fills their bodies in, it does not create
them. The orchestrator messages table already exists in the database.

Target files (all existing - none added, none removed):
backend/app/models/orchestrator.py
backend/app/schemas/orchestrator.py
backend/app/services/orchestrator_service.py
backend/app/api/v1/orchestrator.py
