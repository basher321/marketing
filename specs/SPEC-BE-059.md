# SPEC-BE-059: Command Chat = global control layer (intent → plan → approval → execute → report)

Status: IMPLEMENTED, VERIFIED ON THE LIVE DB (2026-10-01). The plan was approved as recommended (all 9 decisions). Done: ruff/mypy at baseline, the app imports, `next build` passes, and the logic was checked in-process with `httpx.MockTransport` (no DB). The additive DDL was applied 2026-10-01. Live-DB verified 2026-10-01 after fixes: user/tenant ids are stringified before going into jsonb (chat send and approvals returned 500), plan steps now persist their approval_id, and /approvals/pending-counts no longer self-joins approval_queue (500). Open: a chat-made Meta draft has no image, so its publish fails until one is added in the builder; a retried step's skipped dependents return to pending_approval while their approval rows stay expired. Source: Developer Change Spec §4–§5 and the diagram's "COMMAND CHAT CONTROL" lane (intent + required fields → draft plan → user reviews/edits/approves → AI executes through APIs → AI reports status + metrics). Builds on SPEC-BE-023/031/032/033 (chat, intent, plan, plan storage) and SPEC-BE-020/024 (approvals). Uses SPEC-BE-055/056 (Meta), SPEC-BE-058 (shipping), SPEC-BE-060 (workflows). Frontend: SPEC-FE-041.

Implementation notes / deviations: (1) planning is one LLM call in the new `ai/command_actions.py`; `intent_parser.py`/`planner.py` are unchanged (`planner._spend_decision` is still used by campaigns). (2) **Spend steps always need an explicit owner click, even when the owner wrote the command**; only `change` steps auto-approve for the owner (safety). (3) The notify/task/webhook helpers live in `workflow_engine/actions.py`. (4) Added `POST /orchestrator/draft/discard` ("Start over"), plus `kind`/`plan_id`/`waiting_for`/`results` on `ChatMessage`, so plan cards render after a reload. (5) `product_service.update_products` was added for `update_product`. (6) Dev-only `LLM_PROVIDER=fixture` + `LLM_FIXTURE_FILE`.

## Purpose — what's missing today
- A plan is stored and turned into approval rows, but **nothing is ever executed** (`approval_service`: "no approved action is executed here").
- The action vocabulary is the 10 values of the `workflow_action_type` enum. There is no shipping, workflow, Meta builder, read/inspect or pause/resume action.
- Each message is parsed alone: a clarifying question can't be answered by the next message (no memory of the pending request).
- There is no status, no event trail and no result summary after approval.

This spec closes the loop, for every module: **user command → intent extraction → required-field check → plan/draft → approval (per policy) → execution through the backend services (which call the external APIs) → status/events → result summary.**

## Design
### 1. One action registry (replaces the enum-bound list)
`ai/prompts/planner.py`'s `ACTION_TYPES` / `PARAMETER_MODELS` become a registry of **command actions**. Each entry declares: `type`, strict Pydantic params, `module`, `risk` (`read` | `draft` | `change` | `spend`), `min_role`, `approval_subject_type`, and an `executor` (a function that calls an existing service function — never the DB or an external API directly). Plans live in `orchestrator_plans.actions` (jsonb), so they are not limited by the `workflow_action_type` enum; the 10 existing types stay as aliases.

| Module | Actions (type → service called) | Risk |
|---|---|---|
| E-Commerce | `inspect_products`, `inspect_orders`, `inspect_inventory` (read); `update_product` (status/title); `adjust_inventory` (inventory_service.adjust); `create_pricing_rule` / `adjust_pricing` (pricing_service) | read / change |
| Shipping | `inspect_shipping` (status + zones + validation); `create_shipping_zone`, `add_shipping_rate`, `update_shipping_rate`, `set_free_shipping_threshold`, `enable/disable_shipping_rate`, `sync_shipping` (shipping_service, SPEC-BE-058; store-sourced changes are pushed to the store) | read / change |
| Marketing | `generate_content` (content_service), `schedule_post`, `inspect_campaigns`, `inspect_campaign_results` (SPEC-BE-056) | draft / read |
| Meta campaigns | `create_meta_campaign_draft` (full SPEC-BE-055 tree: objective, campaign, ad set(s), ad(s)), `update_meta_campaign_draft`, `validate_meta_campaign`, `publish_meta_campaign` (active / paused / scheduled), `pause_meta` / `resume_meta` (campaign, ad set or ad), `update_meta_budget` | draft / spend |
| Workflows | `inspect_workflows`, `create_workflow` (always saved **disabled**), `update_workflow` (new version, SPEC-BE-049), `enable_workflow` / `disable_workflow` (SPEC-BE-060 builds the NL → JSON part) | draft / change |
| General | `notify_owner`, `create_task`, `send_message`, `call_webhook` (existing) | change |

### 2. Approval / safety policy (reuses the existing approval queue — no new approval system)
Defaults, documented as a code comment and overridable per tenant in `tenants.settings.approval_policy` (no UI in v1, open decision 3):
- `read` → executes immediately, never queued; any role.
- `draft` → executes immediately (creates drafts only: nothing goes live, no money, no customer sees it); manager+.
- `change` → `pending` approval; any manager+ may approve, **not the requester alone unless they are owner** (owner's own command counts as approval, like SPEC-BE-047).
- `spend` (publish/resume/budget increase on Meta, `launch_ad`) → `pending`; **only the owner** approves (SPEC-BE-047/054 rule unchanged). The SPEC-BE-032 daily-cap rule still flags over-cap amounts in the summary.
- Pausing a Meta object (reduces spend) is `change`, so a manager can approve it quickly.
- Role gate at plan time: an action whose `min_role` is above the requester's role is dropped with reason `forbidden_for_role` and named in the reply ("Agents can't change shipping rates").
- The AI never calls an executor for a pending item; execution starts only from an approval decision (or immediately for read/draft/owner-self-approved). This is enforced in the executor entry point, not in the prompt.

### 3. Required-field check + multi-turn clarification
- Each action's params model is the required-field contract. When the LLM's draft fails validation, the reply asks **only** for the missing/invalid fields of that action (fixed question templates per field, as SPEC-BE-031 — never echoing raw LLM text), e.g. "What daily budget should the Sales campaign use?".
- The pending draft (validated parts + missing list) is stored on the assistant message (`orchestrator_messages.parsed_intent` = `{"pending_draft": {...}, "missing": [...]}`). The next user message in the thread is parsed **together with** that pending draft, so "500 BDT a day" completes it. A new unrelated command discards it ("Starting a new request").
- Tenant data is resolved before planning: SKUs, product names → products; "best sellers" → `top_by_units`; campaign names → campaign IDs; zone names → zone IDs; workflow names → IDs. Unknown references → a clarifying question, never a guess (SPEC-BE-031 rule kept).
- Defaults the AI may fill without asking (and must show in the plan): currency = tenant currency; Meta identity = the connected Page / IG account; pixel = the connected pixel; placements = Advantage+; start = now. It must ask for: budget, objective (when not implied), destination URL when the products have none, audience countries.

### 4. Multi-module plans with dependencies
- A plan holds an ordered list of actions with optional `depends_on: [index]` and `$ref` params (`"$1.campaign_id"` = output field of action 1). Example — "Create a Sales campaign for these products, set budget X, and turn on a low-stock workflow" →
  1. `create_meta_campaign_draft` (draft, runs now) →
  2. `publish_meta_campaign` (spend, owner approval, depends on 1) →
  3. `create_workflow` (draft, disabled, runs now) →
  4. `enable_workflow` (change, approval, depends on 3).
- If an action fails, its dependents become `skipped` with the reason; independent actions still run.
- One approval per plan item (as today), plus "approve all" (SPEC-BE-024's group decision), which approves only the items the approver's role may approve.

### 5. Execution, status, events
- Executor entry point `orchestrator_service.execute_ready_actions(db, tenant_id, plan_id, actor_user_id)` runs every action whose approval is `approved` (or auto) and whose dependencies succeeded, in order.
- Runs **in the background** on the existing in-process APScheduler (`add_job(..., trigger="date")`, run now), so a Meta publish doesn't block the approve request. Triggered from: send (for read/draft/auto items) and `approval_service.decide_one/decide_group` (after commit).
- Each action in `orchestrator_plans.actions[i]` gets `status` (`pending_approval` → `approved` → `running` → `succeeded` | `failed` | `skipped` | `rejected`), `started_at`, `finished_at`, `result` (IDs + a short summary), `error` (classified message, e.g. SPEC-BE-055 rule 9). Plan status: live `plan_status` enum — `executed` when every non-rejected action succeeded, `failed` when any failed, otherwise as today.
- Idempotency: an action that is already `running`/`succeeded` is never re-run (row lock on the plan).
- **Result summary:** when the plan finishes, one `assistant` message with the same `correlation_id` summarizes outcomes, IDs and links (Ads Manager link, workflow link, shipping zone), and for read actions the data itself (short table text). Inspect results are summarized from real service data, never by the LLM inventing numbers (the LLM may only phrase numbers it was given).
- `GET /orchestrator/plans/{id}` → plan with per-action status/result/error (for polling). `GET /orchestrator/messages` (existing) includes the summary messages. `POST /orchestrator/plans/{id}/actions/{index}/retry` (manager+, failed actions only, re-checks approval).
- Edit before approval: `PATCH /orchestrator/plans/{id}/actions/{index}` (manager+) with new params → re-validated against the same params model; a changed `change`/`spend` action resets its approval to `pending` (diagram: "User reviews / edits / approves").
- Audit: `orchestrator.plan_created` (existing), `orchestrator.action_started|succeeded|failed|skipped`, plus each underlying service's own audit rows (they already audit), all sharing the plan's `correlation_id` in metadata.
- Errors never leak secrets or raw provider bodies; LLM failures keep SPEC-BE-033's fallback replies.

### 6. Bug fixes found while reading (in scope)
- `launch_ad` plan items are queued with `subject_type='campaign'` and `subject_id = plan id`; `campaign_service.apply_approval_decision` then looks for a campaign with the plan's id and silently does nothing. Plan items will use `subject_type='plan'`/`'action'` (live enum) for plan items, and the engine counters (SPEC-BE-020) will count plan items by the action's module from `payload.module`.

## Open decisions (recommendation first)
1. **Background execution.** *Recommend:* APScheduler one-off jobs (already in-process, no new infra) + polling. *Alternative:* run inline in the approve request (simpler, but a multi-action Meta publish can take 30–60 s).
2. **Draft actions without approval.** *Recommend:* yes (drafts can't spend or reach customers). *Alternative:* every action, even drafts, waits for approval.
3. **Configurable policy.** *Recommend:* code defaults + optional `tenants.settings.approval_policy` override (no UI in v1). *Alternative:* a Settings UI now (adds a frontend spec).
4. **Meta read-only MCP (SPEC-BE-057).** *Recommend:* not in this spec; inspect actions use our own imported data (SPEC-BE-056).

## Acceptance criteria (live Postgres, rolled-back transaction; the LLM is a deterministic stub returning fixture JSON through `llm_client`; Meta/store APIs via `httpx.MockTransport`; background jobs run synchronously in the test)
1. **Command A/B:** "Create a Sales campaign for SKU-1 and SKU-2 with a 500 BDT daily budget for 7 days in Bangladesh, and turn on a low-stock workflow" → one plan with the 4 dependent actions above; actions 1 and 3 execute immediately (draft campaign tree + disabled workflow exist); 2 and 4 are pending; the reply lists all four with their approval needs.
2. **Missing info (Workflow-C, Command-C):** the same command without a budget → clarifying question for the budget only; the next message "500 a day" completes the same draft and produces the plan.
3. **Approval:** a manager approving action 2 → 403 (owner only); the owner approves → Meta publish runs (MockTransport sees the SPEC-BE-055 call sequence); action 4 approved by a manager → workflow enabled; plan `executed`; summary message posted with IDs.
4. **Failure:** Meta returns an error on the ad → action 2 `failed` with the classified message, dependents `skipped`, other actions unaffected, plan `failed`, audit `orchestrator.action_failed`; retry after a fixed fixture → succeeds.
5. **Shipping-C:** "Show my shipping setup" → `inspect_shipping` runs immediately and the reply contains the real zones; "Add free shipping over 2000 BDT in the Dhaka zone" → `set_free_shipping_threshold` pending → approved → rate updated (and pushed to the store for a store-sourced zone).
6. **Role gate:** an agent asking to change shipping → action dropped with `forbidden_for_role`, named in the reply.
7. **Edit before approval:** PATCH a pending action's budget → re-validated; invalid → 422.
8. **No execution without approval:** calling the executor on a pending item does nothing (asserted directly).
9. The `launch_ad` subject bug is fixed (approving a plan's launch item executes it; no stray campaign lookup).
10. Tenant isolation on plans/actions; ruff/mypy no new errors; no secret in any message, result or log.

## Target files
`services/orchestrator_service.py` (pipeline, executor, summary), `ai/prompts/planner.py` (registry, params models, policy), `ai/prompts/intent_parser.py` (multi-module intents, pending-draft context), `services/approval_service.py` (trigger execution after a decision; subject mapping), `api/v1/orchestrator.py`, `schemas/orchestrator.py`, `models/orchestrator.py`, `services/scheduler_service.py` (one-off job helper).
**New file (needs approval):** `ai/command_actions.py` — the action registry + executors (keeps `planner.py` from growing past ~1,000 lines). Alternative: keep it inside `planner.py`.
