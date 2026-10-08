Purpose
Implement the plan-generation function, matching the second of the
architecture's three AI touchpoints: given a validated intent (from
SPEC-BE-031) and the tenant's current Knowledge Base state, produce a
plan - a list of proposed actions, each with its type, parameters, a
cost estimate, and whether it requires approval. Wiring this and
SPEC-BE-031's intent parsing into POST /orchestrator/messages, and
persisting the resulting plan/approval-queue rows, is a separate, later
spec.

Scope
The existing stub files under the ai module: app/ai/llm_client.py,
app/ai/retrieval.py, app/ai/moderation.py, and app/ai/prompts/planner.py.
This spec adds to llm_client.py, retrieval.py, and moderation.py only
where genuinely needed beyond what SPEC-BE-027, SPEC-BE-029, and
SPEC-BE-031 already implemented there - it does not disturb their
existing code paths. No new files or folders. No intent parsing (that is
SPEC-BE-031, called as-is if needed), no persistence, no HTTP endpoint,
no actual execution of any action - only the callable plan-generation
function is in scope.

Contract
After this step: a single function, given a tenant id and a validated
intent object matching SPEC-BE-031's schema, returns a list of proposed
actions, each with: action type, parameters, a cost estimate, and
whether it requires approval - restricted to action types this
codebase's existing action-type list already defines.

Functional rules
- The function retrieves whatever tenant KB/policy state (SPEC-BE-012's
  brand settings, existing pricing/inventory/etc.) is relevant to the
  intent via app/ai/retrieval.py, restricted to that tenant's own data.
- The function calls the LLM (via app/ai/llm_client.py, reusing the
  existing provider-abstraction call path) to decompose the intent into
  a plan.
- Each proposed action's type must be one of this codebase's existing,
  documented action types (e.g. generate_content, schedule_post,
  launch_ad, adjust_budget, send_message, create_task, notify_owner,
  call_webhook, per CLAUDE.md) - the function never invents a new action
  type.
- Each action's cost estimate and requires-approval flag are derived
  from documented, existing policy rules (e.g. a spend threshold).
  Document the exact rule as a code comment - never fabricate a cost or
  approval requirement without basis.
- Every retrieval call filters by tenant_id explicitly, per this
  codebase's existing service convention.

Edge cases
- If the LLM call fails or times out, the function raises a typed error
  rather than returning a fabricated plan.
- If the LLM proposes an action whose type isn't in the documented list,
  that action is dropped from the plan - never silently kept, never
  coerced into a valid type. Document this rule as a code comment.
- The function never mixes one tenant's KB/policy state into another
  tenant's plan, verified with two tenants.
- An intent that maps to zero concrete actions returns an empty plan, not
  an error.

Non-functional rules
No new files or folders - fill in the four existing stub files only,
extending llm_client.py/retrieval.py/moderation.py rather than
duplicating SPEC-BE-027's, SPEC-BE-029's, or SPEC-BE-031's logic in them.
Follow the existing service pattern: plain functions, explicit
parameters, no hidden global state, type hints on every function. No
print statements - structlog only, with the LLM call logged as a span
including token counts, matching the existing observability convention.
No test framework exists yet - verify by exercising the function
directly, not through HTTP.

Acceptance criteria
- Calling the function with a validated intent and tenant context
  returns a plan of proposed actions, each with a documented action type,
  parameters, cost estimate, and requires-approval flag.
- An action type outside the documented list is dropped, never
  fabricated into a valid one.
- The function never mixes tenant context, verified with two tenants.
- An intent mapping to zero actions returns an empty plan, no error.
- No intent-parsing duplication, persistence, or HTTP endpoint exists as
  a result of this spec.

Assumptions
app/ai/llm_client.py, app/ai/retrieval.py, app/ai/moderation.py, and
app/ai/prompts/planner.py already exist as stub files with correct
signatures (per CLAUDE.md's "structurally stubbed" list), and the first
three already carry SPEC-BE-027's, SPEC-BE-029's, and SPEC-BE-031's code
- this spec adds to their bodies without disturbing that existing code.
The documented action-type list and the cost/approval policy rules
already exist per CLAUDE.md.

Target files (all existing - none added, none removed):
backend/app/ai/llm_client.py
backend/app/ai/retrieval.py
backend/app/ai/moderation.py
backend/app/ai/prompts/planner.py
