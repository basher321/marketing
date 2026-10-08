Purpose
Implement the AI reply-draft generation function, matching what the
Customer Service page's AI Reply Draft panel needs: a drafted reply
grounded in the tenant's Knowledge Base and brand voice, with a
confidence score and the sources it was grounded in. Wiring this into an
HTTP endpoint that creates or updates a conversation's pending draft (so
SPEC-BE-026's get-draft can serve it) is a separate, later spec - this
spec only implements the generation function itself.

Scope
The existing stub files under the ai module: app/ai/llm_client.py,
app/ai/retrieval.py, app/ai/moderation.py, and
app/ai/prompts/reply_drafter.py. No new files or folders. No HTTP
endpoint, no persistence of the generated draft into the conversations
domain, no streaming or async-job mechanism - only the callable
generation function is in scope.

Contract
After this step: a single function, given a tenant id, a conversation's
message history, and the tenant's brand/KB context, returns a drafted
reply body, a confidence score, and the list of grounding sources it
used, having passed a moderation check.

Functional rules
- The generation function retrieves grounding context from the tenant's
  kb_documents (and any other existing per-tenant policy/FAQ data
  already modeled) via app/ai/retrieval.py, restricted to that tenant's
  own data - never another tenant's.
- The generation function applies the tenant's brand voice settings (from
  SPEC-BE-012's brand domain) as system context when calling the LLM via
  app/ai/llm_client.py. Document exactly how brand settings are read and
  applied, as a code comment.
- The drafted reply is passed through app/ai/moderation.py's existing
  moderation check before being returned. Document the exact fallback
  behavior for a reply that fails moderation (e.g. a rejection with
  reason, or a safe fallback message) as a code comment.
- The function returns the drafted body, a confidence score, and the
  specific grounding sources actually used - never a source that wasn't
  actually retrieved and used.
- The LLM provider is called through the existing provider-abstraction
  pattern already established in llm_client.py - do not hardcode a
  single provider's SDK call outside that abstraction.

Edge cases
- If retrieval finds no relevant grounding context for a tenant, the
  function still returns a reply (a generic, brand-voice-consistent
  fallback) with an empty grounding-sources list and a correspondingly
  lower confidence score. Document this fallback rule as a code comment -
  never fabricate grounding sources that weren't retrieved.
- If the LLM call fails or times out, the function raises a typed error
  matching this codebase's existing error types, rather than returning a
  fabricated draft.
- If moderation rejects the draft, the function does not silently return
  the rejected text - document the exact behavior as a code comment.

Non-functional rules
No new files or folders - fill in the four existing stub files only. Follow
the existing service pattern: plain functions, explicit parameters, no
hidden global state, type hints on every function. No print statements -
structlog only, with the LLM call logged as a span including token
counts, matching this codebase's existing observability convention if
one exists. No test framework exists yet - verify by exercising the
function directly, not through HTTP.

Acceptance criteria
- Calling the function for a tenant with relevant KB/policy data returns
  a drafted reply, a confidence score, and a non-empty, accurate list of
  grounding sources.
- Calling it for a tenant with no relevant grounding data returns the
  documented fallback reply with an empty grounding-sources list and a
  lower confidence score - not an error, not fabricated sources.
- A reply that fails moderation is handled per the documented rule,
  never returned as-is.
- The function never mixes one tenant's KB/brand data into another
  tenant's generation, verified with two tenants.
- No HTTP endpoint or draft-persistence logic exists as a result of this
  spec.

Assumptions
app/ai/llm_client.py, app/ai/retrieval.py, app/ai/moderation.py, and
app/ai/prompts/reply_drafter.py already exist as stub files with correct
signatures (per CLAUDE.md's "structurally stubbed" list) - this spec
fills their bodies in, it does not create them. An LLM provider is
already configured and reachable per SPEC-BE-003's settings.

Target files (all existing - none added, none removed):
backend/app/ai/llm_client.py
backend/app/ai/retrieval.py
backend/app/ai/moderation.py
backend/app/ai/prompts/reply_drafter.py
