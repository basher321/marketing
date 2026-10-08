Purpose
Implement the Customer Service page's AI Reply Draft panel actions -
Edit, Send Reply, and Handoff - for one selected conversation, matching
exactly what the HTML shows. Generating the draft itself (the LLM call,
its confidence score, and its grounding sources) is a separate, later
spec; this spec only operates on a draft that already exists.

Scope
The existing stub files for the conversations domain:
app/models/conversation.py, app/schemas/conversation.py,
app/services/conversation_service.py, and app/api/v1/conversations.py -
the same four files SPEC-BE-007 and SPEC-BE-021 use; this spec adds
functions and routes to that domain, not new files. No new files or
folders. No draft generation, no LLM call, no moderation pass, no
confidence/grounding computation - only editing the draft's text,
sending it, and escalating (handoff) are in scope.

Contract
After this step: a request returns the caller's tenant's current pending
draft reply for one conversation, if one exists; an edit request updates
that draft's text; a send request sends the (possibly edited) draft as
the actual outbound reply; a handoff request escalates the conversation
to a human instead of sending the draft.

Functional rules
- Get-draft returns the caller's tenant's current pending draft reply
  for one conversation, with its text, if one exists; if none exists,
  returns a documented empty/null response, not an error.
- Edit updates the pending draft's text for the caller's tenant's
  conversation - it does not send anything.
- Send takes the current draft text (as edited, if edited) and creates
  the actual outbound message on the conversation, marking the source
  draft as sent/consumed. Reuse SPEC-BE-007's existing status derivation
  so the conversation's status updates accordingly (moves out of "draft
  ready") - do not invent a second status mechanism.
- Handoff escalates the conversation to a human without sending the
  draft. Reuse SPEC-BE-007's existing escalation state so the
  conversation's status becomes "escalated" per that spec's derivation
  rule, not a new status value.
- Every query and mutation filters by tenant_id explicitly, per this
  codebase's existing service convention.
- Every send and every handoff writes one entry via the existing
  write_audit_log() function in core/audit.py.

Edge cases
- Editing, sending, or handing off a conversation with no pending draft
  is rejected with a clear error, nothing is written.
- Acting on a conversation belonging to another tenant returns 404, not
  the other tenant's data and not a permission error that would confirm
  the row exists.
- Sending an edited draft whose text is empty is rejected, nothing is
  sent.

Non-functional rules
No new files or folders - fill in the four existing stub files only. Follow
the existing service pattern: plain functions, explicit db and tenant_id
parameters, no classes. Type hints on every function. No print statements -
structlog only. No test framework exists yet, so verification is manual.

Acceptance criteria
- Get-draft returns the current pending draft for the caller's tenant's
  conversation, or the documented empty response if none exists.
- Edit updates the draft's text without sending anything.
- Send creates the outbound message from the (possibly edited) draft
  text, and the conversation's status - per SPEC-BE-007's derivation -
  reflects it as sent, not still draft-ready.
- Handoff escalates the conversation and the conversation's status - per
  SPEC-BE-007's derivation - reflects escalated.
- Every send and every handoff produces exactly one audit_log row.
- Acting on a conversation with no pending draft, or belonging to a
  different tenant, is rejected or 404 as specified, verified with two
  tenants.
- No draft-generation, LLM, or moderation endpoint exists as a result of
  this spec.

Assumptions
app/models/conversation.py, the matching schema file,
conversation_service.py, and api/v1/conversations.py already exist as
stub files with correct signatures (per CLAUDE.md's "structurally
stubbed" list) and already carry SPEC-BE-007's and SPEC-BE-021's code -
this spec adds to their bodies without disturbing that existing code. A
pending draft is assumed to already exist in the data model (created by
a separate, later generation spec) - this spec is tested against
existing or seeded draft rows, not ones it creates itself.

Target files (all existing - none added, none removed):
backend/app/models/conversation.py
backend/app/schemas/conversation.py
backend/app/services/conversation_service.py
backend/app/api/v1/conversations.py
