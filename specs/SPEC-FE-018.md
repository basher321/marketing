# SPEC-FE-018: Workflow Builder — Canvas & Test Run

## Purpose
Render a selected saved workflow's real trigger→condition→action structure on the canvas, and wire the "Test Run" button to the real dry-run endpoint (SPEC-BE-034), showing its real result.

## Scope
In scope: workflow selection from the Saved Workflows table (extending SPEC-FE-017), the canvas rendering that selection's real node structure, and the "Test Run" button + result display.

Explicitly NOT being built by this spec:
- Any natural-language translation of trigger_config, condition_dsl, or action inputs into prose like the mockup's illustrative copy ("SKU stock < 10", "Is best-seller?") — no such human-readable field is confirmed to exist in the real data, and condition_dsl parsing is explicitly a stubbed placeholder per SPEC-BE-034. Nodes render real raw data instead (see Functional Rule 3).
- Workflow creation/editing via the canvas — this is a read-only + test-run view, not the visual node editor described in the architecture doc
- "+ New Workflow" and "Version History" — still non-functional per SPEC-FE-017

## Contract
The real backend endpoints already implemented for a single workflow's detail (trigger_type, trigger_config, condition_dsl, actions) and for the dry-run test endpoint (SPEC-BE-034: POST /workflows/{id}/test). Do not assume field names or response shapes — confirm them from the real backend code per Functional Rule 1.

## Functional rules
1. Before writing any code, read the real backend's workflows routes/schemas (and CLAUDE.md) to determine: whether a single-workflow detail endpoint exists returning trigger_type/trigger_config/condition_dsl/actions (or whether the list endpoint from SPEC-FE-017 already includes enough detail), and the exact request/response shape of POST /workflows/{id}/test per SPEC-BE-034 (workflow_run fields, action_executions fields). If any of this is ambiguous, stop and report exactly what's unclear rather than guessing.
2. Extend SPEC-FE-017's saved-workflows table so clicking a row selects that workflow (visually indicated) and drives the canvas below. Default to the first workflow selected on load. Document this as a reasoned UI interpretation, same as the master-detail pattern established in SPEC-FE-013.
3. Render the canvas with one Trigger node, one Condition node (only if the selected workflow's condition_dsl is non-empty — omit the Condition node entirely if it is, rather than rendering an empty one), and one node per real action, connected with arrows in that order, matching the mockup's wf-node/wf-trigger/wf-condition/wf-action/wf-arrow visual structure. Node content:
   - Trigger node: title = the real raw trigger_type value (e.g. "inventory.low"); subtitle = the real trigger_config, rendered as compact raw JSON (or a specific human-readable description field only if Functional Rule 1 confirms one actually exists) — do not invent prose.
   - Condition node (if present): title = the literal word "Condition" (since no human-readable condition title is confirmed to exist); subtitle = the real condition_dsl string verbatim.
   - Action nodes: title = the real raw action "type" field (e.g. "notify_owner"); subtitle = the real action's input/config, rendered as compact raw JSON (or a human-readable description field only if one is confirmed to exist for actions, similar to what SPEC-FE-009 confirmed for plan actions — check whether workflow actions carry the same kind of description field).
4. "Test Run" button calls the real confirmed POST /workflows/{id}/test for the currently selected workflow. While in flight, disable the button and show a loading indicator.
5. On a real response, render a result panel beneath the canvas: the workflow_run's real status (and error, if failed), and one row per real action_execution (its real type, status, and output) — matching SPEC-BE-034's documented per-action fields exactly, not a reinterpretation of them.
6. On failure, show the real ApiError message in the result panel rather than a generic failure message.

## Edge cases
- No workflows exist yet: the canvas area shows a plain "No workflow selected" state rather than erroring.
- A workflow with zero actions: the canvas shows only the Trigger (and Condition, if present) node, with no dangling arrow to a missing action.
- Test Run called on a workflow with an unrecognized action type (per SPEC-BE-034's own failure path): the result panel shows the real "failed" status and real error message rather than treating it as a client-side error.

## Non-functional rules
- No fabricated natural-language node text anywhere — see Functional Rule 3.
- Must not change SPEC-FE-017's table rendering beyond adding row-click selection.
- Must not change SPEC-FE-002's other 9 routes or the sidebar/topbar.
- No new dependency beyond what's installed.

## Acceptance criteria
1. Selecting a different workflow updates the canvas to that workflow's real structure.
2. Every node's title/subtitle traces to real backend data (raw values or a genuinely confirmed description field) — no invented prose.
3. The Condition node only appears when a real condition_dsl value exists.
4. Test Run calls the real confirmed endpoint for the selected workflow and displays its real result (status, per-action results) accurately, including the failure case.
5. A workflow with zero actions renders the canvas correctly with no dangling arrow.
6. SPEC-FE-017's table (aside from the added selection) and SPEC-FE-002's other 9 routes/shell are unchanged.

## Assumptions
- The real single-workflow-detail and test-run contracts are authoritative per Functional Rule 1.
- No human-readable description exists for trigger_config/condition_dsl/action inputs unless specifically confirmed otherwise in the plan step.

## Target files
- app/(app)/workflows/page.tsx (extends SPEC-FE-017's version, adding selection state and the canvas)
- components/workflows/canvas.tsx (new)
- components/workflows/saved-workflows-table.tsx (extends SPEC-FE-017, adding row-click selection)
- lib/api/workflows.ts (extends SPEC-FE-017's version)
- lib/types/workflows.ts (extends SPEC-FE-017's version)
