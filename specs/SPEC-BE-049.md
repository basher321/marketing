# SPEC-BE-049: Workflows — create, edit (versioned), enable/disable, version history, restore

Status: IMPLEMENTED (2026-09-30), plan approved by the user; verified on live Postgres (rolled-back txn).

Implementation notes (deviations from rule 1):
- Allowed action types are the 8 the existing dry-run Test Run simulates (generate_content, schedule_post, launch_ad, adjust_budget, send_message, create_task, notify_owner, call_webhook). The legacy workflow_engine ACTION_REGISTRY only holds "log"/"notify" and isn't what runs. update_product and adjust_pricing stay unsupported, as in SPEC-BE-034.
- `condition_dsl` had no grammar, and the engine's evaluator takes dicts, not text. This spec defines `<field> <op> <value>` clauses joined by AND (ops == != > >= < <= contains), validated on save in workflow_service. The dry-run still treats conditions as passed (SPEC-BE-034, unchanged).
- The catalog (trigger config fields and action params) lives in workflow_service, so workflow_engine/actions.py is untouched. Actions are stored flat, `{type, ...params}`, like the seeded workflows.

## Purpose
Back the Workflow Builder's "+ New Workflow", edit and "Version History" (SPEC-FE-034), as in standard automation tools (Zapier, HubSpot Workflows, Klaviyo Flows): build a trigger → condition → actions flow, keep every saved version, and restore an old one. Test Run (dry run, SPEC-BE-034) already works and is unchanged.

## Versioning model (the live schema's own design)
`workflows` has `version` and `previous_version_id`.
- **Saving an edit inserts a new row** with version + 1 and `previous_version_id` = the old row's id. It copies `enabled`, and the old row is disabled.
- The old row stays, so its `workflow_runs` keep pointing at the exact version that ran.
- A row that some other row names as `previous_version_id` is **superseded**. Lists show only the current (non-superseded) row of each chain.

## Contract
- `GET /api/v1/workflows`: unchanged shape, now current rows only.
- `POST /api/v1/workflows` (manager+) → 201 WorkflowDetail. Body: `{ name, description?, trigger_type, trigger_config{}, condition_dsl?, actions:[{type, params{}}] (1-10), enabled? (default false) }`
- `PUT /api/v1/workflows/{id}` (manager+) → 200 WorkflowDetail of the **new version**. Same body. Only the current version can be edited; a superseded version returns 409.
- `PATCH /api/v1/workflows/{id}/enabled` `{enabled}` (manager+) → 200. Toggles the current row without creating a new version.
- `GET /api/v1/workflows/{id}/versions` → `[{id, version, created_at, created_by_name, name, trigger_type, action_count, enabled, is_current}]`, newest first, following the chain.
- `POST /api/v1/workflows/{id}/versions/{version_id}/restore` (manager+) → 201 WorkflowDetail. Creates a new version that copies the chosen old version's definition.

## Functional rules
1. `trigger_type` must be one of the live `workflow_trigger_type` values. Each action `type` must be one of the live `workflow_action_type` values **and** registered in `workflow_engine/actions.py`, otherwise 422. `condition_dsl` must parse with the engine's own `conditions` parser, otherwise 422 with the parser's message.
2. The editor's trigger and action parameter forms are driven by a backend-served catalog: `GET /api/v1/workflows/catalog` returns `{triggers:[{type,label,config_fields}], actions:[{type,label,param_fields}], condition_help}`. The catalog comes from the engine registry, so the UI never invents a field.
3. Everything is tenant-scoped. `created_by` = the actor. Each write is audited (`workflow.create`, `workflow.update`, `workflow.enable`/`disable`, `workflow.restore`).
4. Runs(7d) in the list counts runs of every version in the chain.

## Acceptance criteria
1. Create, then edit twice → 3 rows in the chain, and the list shows only v3. Versions returns v3, v2, v1.
2. Restore v1 → v4 with v1's definition. Old runs still point at their own version.
3. An invalid trigger, action or condition returns 422 and writes nothing. Editing a superseded version returns 409. Viewer gets 403. Another tenant gets 404.
4. Test Run on the new version works as before.

## Target files
- backend/app/models/workflow.py, schemas/workflow.py, services/workflow_service.py, api/v1/workflows.py
- backend/app/workflow_engine/actions.py (read-only use of the registry; a `describe()` for the catalog if needed)
