Purpose
Implement the endpoint that generates and persists an AI reply draft for
a conversation, wiring SPEC-BE-027's generation function into the
conversations domain so SPEC-BE-026's get-draft, edit, send, and handoff
actions operate on real, generated drafts instead of seeded test data.

Scope
The existing stub files for the conversations domain:
app/models/conversation.py, app/schemas/conversation.py,
app/services/conversation_service.py, and app/api/v1/conversations.py -
the same four files SPEC-BE-007, SPEC-BE-021, and SPEC-BE-026 use. No new
files or folders. No change to the generation function itself (that is
SPEC-BE-027's code, called as-is), no change to the edit/send/handoff
actions (SPEC-BE-026) - only the trigger-and-persist step is in scope.

Contract
After this step: a request triggers AI reply-draft generation for one
conversation, calling SPEC-BE-027's generation function with that
conversation's message history and the tenant's brand/KB context, and
persists the result as the conversation's pending draft - with its
confidence score and grounding sources - so that SPEC-BE-026's get-draft,
edit, send, and handoff endpoints operate on it.

Functional rules
- The generate-draft endpoint calls SPEC-BE-027's existing generation
  function directly - it does not reimplement any retrieval, LLM, or
  moderation logic itself.
- The generated draft (body, confidence score, grounding sources) is
  persisted as the conversation's pending draft. There is at most one
  pending draft per conversation at a time - document, as a code
  comment, whether generating again replaces the existing pending draft
  or is rejected while one is already pending; pick one behavior and
  apply it consistently.
- Generating a draft for a conversation whose message history has no
  customer messages yet is rejected with a clear error - it does not
  generate a reply to nothing.
- Every query and mutation filters by tenant_id explicitly, per this
  codebase's existing service convention.

Edge cases
- If SPEC-BE-027's function raises its typed error (e.g. an LLM
  failure), this endpoint surfaces a clear error and persists nothing -
  it never stores a partial or fabricated draft.
- Generating a draft for a conversation belonging to another tenant
  returns 404.
- A generated draft's confidence score and grounding sources are
  persisted exactly as SPEC-BE-027 returned them - never altered or
  re-derived here.

Non-functional rules
No new files or folders - fill in the four existing stub files only. Follow
the existing service pattern: plain functions, explicit db and tenant_id
parameters, no classes. Type hints on every function. No print statements -
structlog only; the generate-draft call is logged as a span with token
counts per SPEC-BE-027's existing observability convention, not
re-logged differently here. No test framework exists yet, so
verification is manual.

Acceptance criteria
- Calling generate-draft for a conversation with customer messages
  produces a pending draft retrievable via SPEC-BE-026's get-draft, with
  the same body, confidence, and sources SPEC-BE-027's function
  produced.
- Calling generate-draft again for the same conversation follows the
  documented replace-or-reject rule consistently, never creating two
  pending drafts.
- Generating for a conversation with no customer messages is rejected,
  nothing persisted.
- If generation fails, nothing is persisted and a clear error is
  returned.
- Generating for a conversation belonging to a different tenant returns
  404, verified with two tenants.
- SPEC-BE-026's edit/send/handoff actions and SPEC-BE-007's list and
  status derivation still work correctly against a draft created this
  way.

Assumptions
app/models/conversation.py, the matching schema file,
conversation_service.py, and api/v1/conversations.py already exist as
stub files with correct signatures (per CLAUDE.md's "structurally
stubbed" list) and already carry SPEC-BE-007's, SPEC-BE-021's, and
SPEC-BE-026's code - this spec adds to their bodies without disturbing
that existing code. SPEC-BE-027's generation function is implemented and
importable.

Target files (all existing - none added, none removed):
backend/app/models/conversation.py
backend/app/schemas/conversation.py
backend/app/services/conversation_service.py
backend/app/api/v1/conversations.py
