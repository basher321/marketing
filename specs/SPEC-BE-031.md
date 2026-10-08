Purpose
Implement the intent-parsing function, matching the first of the
architecture's three AI touchpoints: given a natural-language directive
typed into Command Chat, produce a strictly-typed, schema-validated
intent - or, if it doesn't validate, a clarifying question instead of a
guess. Plan generation from a validated intent (the second touchpoint)
is a separate, later spec; wiring this into POST /orchestrator/messages
is a further, later spec.

Scope
The existing stub files under the ai module: app/ai/llm_client.py,
app/ai/retrieval.py, app/ai/moderation.py, and
app/ai/prompts/intent_parser.py. This spec adds to llm_client.py,
retrieval.py, and moderation.py only where genuinely needed beyond what
SPEC-BE-027 and SPEC-BE-029 already implemented there - it does not
disturb their existing code paths. No new files or folders. No plan
generation, no persistence, no HTTP endpoint - only the callable intent-
parsing function is in scope.

Contract
After this step: a single function, given a tenant id and a natural-
language directive, returns either a validated, strictly-typed intent
object, or a clarifying-question result when the LLM's output does not
validate against the intent JSON Schema.

Functional rules
- The function calls the LLM (via app/ai/llm_client.py, reusing the
  existing provider-abstraction call path from SPEC-BE-027/029) with the
  directive text and asks for structured intent output.
- The LLM's raw output is validated against a documented JSON Schema for
  intent objects. Document the schema's location/definition as a code
  comment - the raw output is never trusted or returned unvalidated.
- If validation fails, the function returns a clarifying-question result
  - not the invalid intent, not a guessed or coerced one. Document the
  exact clarifying-question content/rule as a code comment.
- Retrieval of tenant KB/brand context for grounding uses
  app/ai/retrieval.py, restricted to that tenant's own data.

Edge cases
- If the LLM call fails or times out, the function raises a typed error
  rather than returning a fabricated intent.
- An empty or whitespace-only directive is rejected before any LLM call
  is made, with a clear error.
- The function never mixes one tenant's context into another tenant's
  intent parsing, verified with two tenants.

Non-functional rules
No new files or folders - fill in the four existing stub files only,
extending llm_client.py/retrieval.py/moderation.py rather than
duplicating SPEC-BE-027's or SPEC-BE-029's logic in them. Follow the
existing service pattern: plain functions, explicit parameters, no
hidden global state, type hints on every function. No print statements -
structlog only, with the LLM call logged as a span including token
counts, matching the existing observability convention. No test
framework exists yet - verify by exercising the function directly, not
through HTTP.

Acceptance criteria
- Calling the function with a well-formed directive returns a validated
  intent object matching the documented schema.
- Calling it with a directive that produces invalid LLM output returns
  the documented clarifying-question result, not a guessed intent.
- An empty directive is rejected before any LLM call.
- The function never mixes tenant context, verified with two tenants.
- No plan-generation, persistence, or HTTP endpoint exists as a result of
  this spec.

Assumptions
app/ai/llm_client.py, app/ai/retrieval.py, app/ai/moderation.py, and
app/ai/prompts/intent_parser.py already exist as stub files with correct
signatures (per CLAUDE.md's "structurally stubbed" list), and the first
three already carry SPEC-BE-027's and SPEC-BE-029's code - this spec adds
to their bodies without disturbing that existing code. An LLM provider is
already configured and reachable per SPEC-BE-003's settings.

Target files (all existing - none added, none removed):
backend/app/ai/llm_client.py
backend/app/ai/retrieval.py
backend/app/ai/moderation.py
backend/app/ai/prompts/intent_parser.py
