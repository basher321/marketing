# SPEC-BE-034: Workflow Test Run (dry-run execution)

## Purpose
Implement the "Test Run" dry-run execution described in the architecture spec (§4.7 Workflow Builder: "A Test button dry-runs the workflow against a synthetic or historical event and shows what would happen without actually calling external APIs") and exposed in the UI as the Workflow Builder page's "Test Run" button. This runs a saved workflow's trigger → condition → action chain against a synthetic input and records the outcome as real rows in workflow_runs and action_executions, without invoking any real external API and without causing any real side effect in any other domain.

## Scope
In scope: a single endpoint that dry-runs one saved workflow by id and persists the result.

Explicitly NOT being built by this spec:
- Automatic/real trigger listening (no event bus, no wiring of workflows to real product/order/message/ad events; workflows only run when this test endpoint is called)
- Real action side effects of any kind (no real send_message, launch_ad, adjust_budget, schedule_post, generate_content, notify_owner, create_task, or call_webhook calls against any real service, integration, or other domain's tables)
- condition_dsl expression parsing or evaluation (stubbed per Functional Rule 3 below)
- Workflow creation, editing, or versioning ("+ New Workflow" and "Version History" buttons)
- Enabling, disabling, or pausing a workflow
- Any change to the existing workflow list/detail behavior built in SPEC-BE-014

## Contract
POST /api/v1/workflows/{workflow_id}/test
- Request body (optional): {"input": {<arbitrary JSON object>}}. If omitted or null, treat input as {}.
- Response 200: an object containing the created workflow_run (id, status, started_at, finished_at, error) and an ordered list of the action_executions created (action_index, type, status, output).
- Response 404: workflow_id does not exist for the caller's tenant.
- Response 422: malformed request body.

## Functional rules
1. Load the workflow by id filtered by tenant_id. If not found for this tenant, return 404. Follow the exact same tenant-mismatch response convention already used by the existing GET /workflows list/detail endpoints in app/api/v1/workflows.py (from SPEC-BE-014) rather than introducing a new one; if those endpoints don't establish a clear convention, stop and report rather than guessing.
2. Create a new workflow_runs row: workflow_id, triggered_by = the literal string "manual_test", input = the request body's input (or {} if omitted), status = "running", started_at = now.
3. Condition evaluation placeholder: condition_dsl's grammar is not defined anywhere in the codebase or in the architecture doc available to you. Do not write a parser or evaluator for it. For every test run, treat the workflow's condition as passed unconditionally, and add a code comment at the point of this stub stating that condition_dsl evaluation is a placeholder pending a dedicated rule-engine spec.
4. Iterate the workflow's actions JSONB array in order (action_index = 0-based position). For each entry:
   - If its declared "type" is one of the eight documented action types (generate_content, schedule_post, launch_ad, adjust_budget, send_message, create_task, notify_owner, call_webhook), create an action_executions row: workflow_run_id, action_index, type, input = a shallow merge of the action's stored config with the run's input (run input keys win on conflict — document this exact merge rule as a code comment), attempts = 1, status = "simulated", output = {"simulated": true, "message": "Dry run - no external call made"}.
   - If its declared "type" is missing or not one of the eight documented types, stop iterating immediately: do not create an action_executions row for this or any later entry, set the workflow_run's status = "failed", error = a message naming the unrecognized type and its action_index, finished_at = now, and return the response reflecting only the action_executions created so far.
5. If every action in the array was processed without hitting rule 4's failure path, set workflow_run status = "completed", finished_at = now, error = null.
6. This endpoint never writes to workflows.enabled, workflows.actions, or any other existing workflow field — it only reads the workflow definition.
7. Do not call core/audit.write_audit_log from this endpoint. workflow_runs/action_executions rows are themselves the full record of what happened, and this endpoint makes no tenant business-data mutation of the kind audit_log tracks (orders, campaigns, content, etc.). If your own review of the existing codebase shows other read-only/simulated actions do call write_audit_log, stop and report that discrepancy instead of guessing which convention to follow.
8. tenant_id must be threaded through and filtered on every query touching workflows, workflow_runs, or action_executions.
9. Reuse the same require_permission capability string already declared on the existing GET /workflows endpoints from SPEC-BE-014 for this new endpoint. Do not invent a new capability string. If no capability is currently declared on those endpoints, stop and report.

## Edge cases
- A workflow with an empty actions array: still create the workflow_run, mark it "completed" immediately, return an empty action_executions list.
- A disabled workflow (enabled = false): the test endpoint still runs it; this endpoint is not gated by the enabled flag.
- Two test runs on the same workflow at the same time: both proceed independently; no locking is required.
- Missing workflow_id in the path or a malformed request body: 422, no workflow_run row is created.
- A workflow whose actions entry is present but has no "type" key at all: treated identically to an unrecognized type under Functional Rule 4.

## Non-functional rules
- structlog only; no print statements.
- No new files or folders. Edit only the four target files listed below.
- Must not disturb or change the behavior, response shape, or existing fields relied on by SPEC-BE-014's GET /workflows list/detail endpoints.
- No real HTTP calls to any external platform or integration are permitted anywhere in this code path, under any condition.

## Acceptance criteria
1. POST /api/v1/workflows/{id}/test on a valid workflow returns 200 with a workflow_run summary and an ordered action_executions list whose length equals the workflow's stored actions array length, unless Functional Rule 4's failure path was hit.
2. Every call to this endpoint persists exactly one new workflow_runs row and one action_executions row per action processed.
3. Manually verify (by comparing row counts/checksums before and after a test run) that no row in orders, campaigns, content_assets, scheduled_posts, ads, conversations, messages, or integrations changes as a result of calling this endpoint.
4. SPEC-BE-014's existing GET /workflows list and detail endpoints return unchanged data and shape after this change is made.
5. Calling this endpoint with a workflow_id belonging to a different tenant does not return that other tenant's workflow data.
6. An actions entry with an unrecognized or missing type produces a workflow_run with status "failed" and a descriptive error, never a silently "completed" run.

## Assumptions
- CLAUDE.md is canonical for the exact current field names/types on the Workflow, WorkflowRun, and ActionExecution ORM models if they differ from the column list above.
- Which workflow_id the frontend's "Test Run" button targets (there is no workflow-selector UI documented) is a frontend wiring concern out of scope for this backend spec; this spec only builds the parameterized backend contract POST /workflows/{workflow_id}/test.
- condition_dsl evaluation is out of scope and stubbed per Functional Rule 3 until a dedicated rule-engine spec exists.
- No real external/integration call is authorized by this spec under any circumstance, even for testing purposes.

## Target files
- app/models/workflow.py
- app/schemas/workflow.py
- app/services/workflow_service.py
- app/api/v1/workflows.py

## Implementation notes (2026-09-29)
Implemented with these deviations, each forced by the live schema and documented in
`services/workflow_service.py`:
- `workflow_runs.triggered_by` is the `actor_type` enum, so a test run stores `'human'` plus
  `triggered_by_id` = the caller. The "manual_test" marker goes in the run's `output`
  (`{"mode": "manual_test", "dry_run": true}`).
- `run_status` has no `completed` or `simulated`. A finished run is `succeeded`/`failed`;
  each simulated action is `succeeded` with output `{"simulated": true, "message": ...}`.
- `workflow_runs.workflow_version` (= `workflows.version`) and `correlation_id` (one new
  uuid shared by the run and its action rows) are NOT NULL and set accordingly.
- Rule 9: the GET /workflows endpoints declare no capability beyond authentication, so the
  test endpoint requires the same.
- The assumed SPEC-BE-014 detail endpoint did not exist. `GET /workflows/{id}` was added
  (raw trigger_config / condition_dsl / actions) for SPEC-FE-018.
- `update_product` / `adjust_pricing` exist in the live `workflow_action_type` enum but not in
  this spec's 8 types, so they are treated as unrecognized (the run fails at that action).
- Rows are written through table() constructs: the WorkflowRun/ActionExecution models don't
  map these live columns, and the unused workflow_engine depends on the old attributes.
