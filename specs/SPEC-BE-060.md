# SPEC-BE-060: Workflows from Command Chat (NL → workflow JSON) + live trigger execution

Status: IMPLEMENTED, VERIFIED ON THE LIVE DB (2026-10-01). The plan was approved as recommended (all 9 decisions). Done: ruff/mypy at baseline, the app imports, `next build` passes, and the logic was checked in-process with `httpx.MockTransport` (no DB). The additive DDL was applied 2026-10-01. Live-DB verified 2026-10-01 (rolled-back run; all acceptance checks pass; the chat part needed SPEC-BE-059's fixes). Source: Developer Change Spec §3 and Workflow acceptance tests A–C. Builds on SPEC-BE-014/034/049 (list, detail, dry-run, create/version/enable) and SPEC-BE-059 (chat action registry, approvals, execution). Frontend: SPEC-FE-041 (chat preview card) — the visual Workflow Builder (SPEC-FE-018 and later) is **unchanged** (acceptance A).

Implementation notes: the engine writes runs through workflow_service's Core tables; the `WorkflowRun`/`ActionExecution` models were left as-is (unused by the engine). `order_placed` is wired in the dispatcher, but this backend has no order-creation path yet, so it fires only once a store order sync exists. The cron job checks every minute.

## Purpose
1. **Command Chat as a second editor** for the same workflows: create, edit, enable/disable, inspect — producing exactly the same stored structure the visual builder saves (`trigger_type`, `trigger_config`, `condition_dsl`, `actions[{type, params}]`), validated by the **same** `workflow_service._validated()` rules, so a chat-made workflow opens in the builder and vice versa.
2. **Ask for missing information** and **validate** before saving; require approval when enabling a workflow whose actions are consequential.
3. **Make enabled workflows actually run** — today nothing dispatches a live event (only the SPEC-BE-034 dry-run exists, and `workflow_engine/engine.py` uses `Workflow.conditions` / `is_active`, which don't exist on the live table). Without this, "turn on a low-stock workflow" would turn on nothing (open decision 1).

## Part A — NL → workflow (used by SPEC-BE-059's `create_workflow` / `update_workflow` actions)
- The LLM gets the live catalog (`workflow_service.catalog()`: triggers with their fields, actions with their fields, the condition grammar and examples) and the tenant's context names (products, campaigns, zones) and must return a `WorkflowSave`-shaped draft.
- Validation pipeline: Pydantic `WorkflowSave` → `_validated()` (trigger enum, trigger fields, `parse_condition`, action catalog fields) → **context-field check**: every field used in `condition_dsl` must be one the trigger provides (table below). Any failure → a fixed clarifying question naming the missing/invalid part (e.g. "What stock level counts as low?", "How should I decide a best seller: units sold in the last 30 days at or above what number?"). Raw LLM text is never echoed (SPEC-BE-031 rule).
- `create_workflow` saves **disabled** (risk `draft`, runs immediately). `update_workflow` saves a new version (SPEC-BE-049; superseded → 409 surfaced as a chat reply). `enable_workflow` risk: `change` when every action is `notify_owner`/`create_task`, `spend` when any action is `launch_ad`/`adjust_budget`, `change` otherwise (`adjust_pricing`, `update_product`, `send_message`, `call_webhook`, `generate_content`, `schedule_post`).
- `inspect_workflows` returns the list (SPEC-BE-014) or one workflow's readable summary: "When **inventory is low (≤ 5)** and **product.units_sold_30d ≥ 20** → notify the owner, create a task 'Draft restock PO …'", plus runs in the last 7 days and last run status.
- The chat reply includes a link to open the workflow in the visual builder.

### Worked example (from the change spec)
"Create a workflow: when stock is below 5 and product is a best seller, notify me and draft a restock PO." →
```json
{"name": "Low stock on best sellers → restock", "trigger_type": "inventory_low",
 "trigger_config": {"threshold": 4},
 "condition_dsl": "product.units_sold_30d >= 20",
 "actions": [
   {"type": "notify_owner", "params": {"message": "{{product.title}} ({{product.sku}}) is down to {{inventory.available}} units."}},
   {"type": "create_task", "params": {"title": "Draft restock PO for {{product.sku}}", "assignee_role": "manager"}}],
 "enabled": false}
```
- "below 5" → `threshold: 4` because the trigger is "at or below"; the plan shows this conversion.
- "best seller" has no fixed meaning → the AI asks for the number (acceptance C) unless the tenant already answered it earlier in the thread.
- "Draft a restock PO" → `create_task` (there is no purchase-order module; the plan says so). Open decision 3.

## Part B — live execution (minimal, real)
- **Engine fix:** `engine.run_workflow` reads the live columns (`condition_dsl` via `parse_condition`, `enabled`, `actions[].params`), writes `workflow_runs` with the live columns (`tenant_id`, `workflow_version`, `triggered_by='system'`, `input`, `output`, `status` `running`→`succeeded|failed`, `started_at`, `finished_at`, `error_message`, `correlation_id`), and `action_executions` per step; increments `workflows.run_count`, sets `last_run_at`. It reuses the dry-run's condition evaluator so dry-run and live agree.
- **Templating:** `{{field.path}}` in text params is filled from the trigger context (missing → empty, never an error).
- **Triggers wired in v1** (the ones the change spec needs; others keep the dry-run only, listed in the catalog as "manual test only"):
  | Trigger | Fired from | Context fields |
  |---|---|---|
  | `inventory_low` | `inventory_service.adjust` (and SPEC-BE-058/store syncs that change stock), when `available` crosses from above to at/below `threshold` | `product.{id, sku, title, units_sold_30d, revenue_30d_cents}`, `inventory.{available, committed, location}` |
  | `order_placed` | order creation path (`order_service`, and store order sync when it exists) | `order.{total, channel, status, items_count}`, `customer.{tags}` |
  | `ad_threshold_crossed` | the SPEC-BE-056 insights import, per campaign after each import | `campaign.{id, name, roas, ctr, cpc, daily_spend}` |
  | `schedule_cron` | APScheduler (`workers/tasks/workflow_tasks.py`, inert today) | `now` |
  | `manual_owner_command` | `POST /workflows/{id}/run` (manager+) and the chat action `run_workflow` | `input` |
- `product.units_sold_30d` / `revenue_30d_cents` = sum over `order_items` of orders placed in the last 30 days, status not cancelled/refunded (documented as a code comment).
- **Action executors in v1:** `notify_owner` → a `notifications` row (live table) for each owner; `create_task` → a `notifications` row with `type='task'`, `severity='info'`, assignee role in `metadata` (open decision 3); `call_webhook` → SSRF-guarded https POST with the context; `generate_content` → SPEC-BE-046 draft (needs approval to publish, as today); `adjust_pricing`, `update_product`, `launch_ad`, `adjust_budget`, `send_message`, `schedule_post` → create a **pending approval item** (SPEC-BE-059 policy) instead of acting silently; the run output says "queued for approval".
- **Safety:** at most 50 runs per workflow per hour (excess → run `cancelled` with reason); a workflow can't trigger itself recursively (depth 1); an action error marks the run `failed` but other actions still run; every run is audited (`workflow.run_succeeded|failed`).
- Runs happen in-process after the triggering transaction commits (APScheduler date job), never inside the user's request transaction.

## Open decisions (recommendation first)
1. **Live execution in this spec.** *Recommend:* yes, Part B as scoped (5 triggers, safe executors). *Alternative:* chat edits workflows but they still never run (only the dry-run) — acceptance "turn on a low-stock workflow" would be cosmetic.
2. **Enable needs approval?** *Recommend:* per the risk rule above (an owner's own command counts as approval). *Alternative:* enabling any workflow is a `change` needing approval.
3. **"Restock PO".** *Recommend:* `create_task` (notification-backed) in v1; a real purchase-order module is a separate spec. *Alternative:* add a `draft_purchase_order` action now with a new `purchase_orders` table (needs DDL + UI).
4. **Best-seller definition.** *Recommend:* always ask (or use a tenant default saved after the first answer in `tenants.settings.best_seller_min_units_30d`). *Alternative:* fixed default (top 10% by units).

## Acceptance criteria (live Postgres, rolled-back transaction; deterministic LLM stub; background jobs run synchronously in the test)
1. **A:** the existing builder routes (`GET/POST/PUT /workflows`, enable, versions, restore, dry-run test) still pass their SPEC-BE-049/034 checks unchanged.
2. **B:** the worked example via chat → after the best-seller question is answered, a disabled workflow is saved with exactly the JSON above; `GET /workflows/{id}` returns it (opens in the builder); "change the threshold to 10" → new version 2; "turn it on" → `enable_workflow` approval → approved → enabled.
3. **C:** missing threshold → question; an unknown condition field (`product.color`) → question naming it; an invalid condition (`stock lots`) → question; nothing saved until valid.
4. **Live run:** with the workflow enabled, an inventory adjust from 6 → 3 on a product with 25 units sold in 30 days → one `workflow_runs` row `succeeded`, two `action_executions`, one owner notification + one task notification; 3 → 2 doesn't fire again (crossing rule); a non-best-seller doesn't pass the condition (run `succeeded` with output `condition_not_met`, or no run — decided in the plan, documented).
5. `launch_ad` inside a workflow → a pending approval item, 0 Meta calls.
6. Rate limit and recursion guards hold; tenant isolation; ruff/mypy no new errors (the pre-existing `Workflow.conditions` mypy error disappears).

## Target files
`workflow_engine/engine.py`, `workflow_engine/actions.py`, `workflow_engine/conditions.py`, `workflow_engine/dispatcher.py`, `workflow_engine/triggers.py`, `services/workflow_service.py` (context fields, readable summary, manual run), `services/inventory_service.py` (fire `inventory_low`), `services/order_service.py` (fire `order_placed`), `workers/tasks/workflow_tasks.py`, `workers/schedules.py`, `models/workflow.py` (align `WorkflowRun`/`ActionExecution` to live columns), `api/v1/workflows.py`, `schemas/workflow.py`, plus SPEC-BE-059's chat files. No new files.
