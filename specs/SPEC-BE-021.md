Purpose
Implement the Dashboard's Customer Service engine card's "Avg. response",
"Deflection rate", and "CSAT (7d)" metrics, for the caller's tenant.
"Open threads" is already covered by SPEC-BE-007 and is not duplicated
here.

Scope
The existing stub files for the conversations domain:
app/models/conversation.py, app/schemas/conversation.py,
app/services/conversation_service.py, and app/api/v1/conversations.py -
the same four files SPEC-BE-007 uses; this spec adds functions and a
route to that domain, not new files. No new files or folders. No CSAT-
collection endpoint, no per-agent response-time breakdown - only the
three tenant-wide figures are in scope.

Contract
After this step: a request returns, for the caller's tenant: average
first-response time over the trailing 7 days, the deflection rate over
the trailing 7 days, and the average CSAT score over the trailing 7 days.

Functional rules
- Avg. response = average elapsed time between each conversation's last
  customer message and the next outbound message, for conversations in
  the trailing 7 days (UTC). Reuse the waiting-time computation already
  established in SPEC-BE-007 rather than inventing a second timing
  calculation.
- Deflection rate = the percentage of the caller's tenant's conversations
  in the trailing 7 days whose status - per SPEC-BE-007's existing status
  derivation - is not "escalated". Document this exact rule as a code
  comment; never invent a different definition.
- CSAT (7d) = the average customer satisfaction score over the trailing 7
  days, sourced from wherever the existing conversation/message models
  already capture it, if anywhere. Document the exact source field as a
  code comment.
- Every query filters by tenant_id explicitly, per this codebase's
  existing service convention.

Edge cases
- A tenant with zero conversations in the trailing 7 days returns 0 (or a
  documented null) for all three figures, not a division-by-zero error.
- If no CSAT data exists anywhere yet in the schema or models, return a
  documented placeholder (e.g. null) with a code comment stating this is
  pending a CSAT-collection mechanism - never fabricate a plausible-
  looking score.
- A conversation belonging to another tenant never contributes to
  another tenant's figures.

Non-functional rules
No new files or folders - fill in the four existing stub files only. Follow
the existing service pattern: plain functions, explicit db and tenant_id
parameters, no classes. Type hints on every function. No print statements -
structlog only. No test framework exists yet, so verification is manual.

Acceptance criteria
- The endpoint returns avg. response, deflection rate, and CSAT (7d) for
  the caller's tenant only.
- A tenant with zero conversations in the trailing 7 days gets 0 (or the
  documented null) for all three, no error.
- If CSAT data does not exist, the documented placeholder is returned,
  never a fabricated score.
- A conversation belonging to a different tenant never affects the
  result, verified with two tenants.
- No CSAT-collection or per-agent-breakdown endpoint exists as a result
  of this spec.

Assumptions
app/models/conversation.py, the matching schema file,
conversation_service.py, and api/v1/conversations.py already exist as
stub files with correct signatures (per CLAUDE.md's "structurally
stubbed" list) and already carry SPEC-BE-007's code - this spec adds to
their bodies without disturbing that existing code.

Target files (all existing - none added, none removed):
backend/app/models/conversation.py
backend/app/schemas/conversation.py
backend/app/services/conversation_service.py
backend/app/api/v1/conversations.py
