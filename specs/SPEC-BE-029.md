Purpose
Implement the campaign ad-creative generation function, matching what
the Campaign Wizard's "AI-Generated Creative Variants" step needs:
multiple text creative variants (a headline and a short description
each), grounded in the tenant's brand voice and the campaign's target
products/objective. Wiring this into an HTTP endpoint that creates or
updates a campaign's content_assets (so the wizard can list, select, and
edit variants) is a separate, later spec - this spec only implements the
generation function itself. Image/visual asset generation is out of
scope - only the text creative is generated, matching what the HTML's
variant cards show as real generated content (headline + description);
the colored placeholder blocks in each variant card are decorative and
not generated.

Scope
The existing stub files under the ai module: app/ai/llm_client.py,
app/ai/retrieval.py, app/ai/moderation.py, and
app/ai/prompts/content_generator.py. This spec adds to llm_client.py,
retrieval.py, and moderation.py only where genuinely needed beyond what
SPEC-BE-027 already implemented there - it does not disturb SPEC-BE-027's
existing reply-drafting code path. No new files or folders. No image
generation, no persistence, no HTTP endpoint - only the callable
creative-variant generation function is in scope.

Contract
After this step: a single function, given a tenant id, a target
objective/products/brief, and the tenant's brand voice, returns a
documented fixed number of distinct text creative variants (each a
headline and a short description), having passed a moderation check.

Functional rules
- The generation function retrieves the relevant product/campaign
  context needed for grounding (e.g. the named SKUs, the campaign
  objective) - restricted to that tenant's own data, never another
  tenant's.
- The generation function applies the tenant's brand voice settings
  (from SPEC-BE-012's brand domain) as system context when calling the
  LLM via app/ai/llm_client.py, reusing SPEC-BE-027's existing provider-
  abstraction call path rather than building a second one.
- Returns a documented fixed number of variants (e.g. 3, matching the
  HTML) - document the exact count as a code comment.
- Each variant is passed through app/ai/moderation.py's existing
  moderation check before being returned. Document, as a code comment,
  whether a variant that fails moderation is dropped from the result or
  replaced with a regenerated one - pick one rule and apply it
  consistently.

Edge cases
- If the LLM call fails or times out, the function raises a typed error
  rather than returning fabricated variants.
- If moderation rejects every generated variant, the function raises a
  typed error rather than silently returning zero variants as if that
  were success.
- The function never mixes one tenant's brand/product data into another
  tenant's generated variants, verified with two tenants.

Non-functional rules
No new files or folders - fill in the four existing stub files only,
extending llm_client.py/retrieval.py/moderation.py rather than
duplicating SPEC-BE-027's logic in them. Follow the existing service
pattern: plain functions, explicit parameters, no hidden global state,
type hints on every function. No print statements - structlog only, with
the LLM call logged as a span including token counts, matching
SPEC-BE-027's existing observability convention. No test framework
exists yet - verify by exercising the function directly, not through
HTTP.

Acceptance criteria
- Calling the function for a tenant with valid brand/product context
  returns the documented fixed number of variants, each with a headline
  and description consistent with that tenant's brand voice.
- A variant that fails moderation is handled per the documented rule,
  never returned as-is.
- If every variant fails moderation, a typed error is raised, not a
  silent empty/zero result.
- The function never mixes one tenant's data into another tenant's
  variants, verified with two tenants.
- No image generation, persistence, or HTTP endpoint exists as a result
  of this spec.

Assumptions
app/ai/llm_client.py, app/ai/retrieval.py, app/ai/moderation.py, and
app/ai/prompts/content_generator.py already exist as stub files with
correct signatures (per CLAUDE.md's "structurally stubbed" list) and the
first three already carry SPEC-BE-027's code - this spec adds to their
bodies without disturbing that existing code. An LLM provider is already
configured and reachable per SPEC-BE-003's settings.

Target files (all existing - none added, none removed):
backend/app/ai/llm_client.py
backend/app/ai/retrieval.py
backend/app/ai/moderation.py
backend/app/ai/prompts/content_generator.py
