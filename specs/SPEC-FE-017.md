# SPEC-FE-017: Workflow Builder — Saved Workflows Table

## Purpose
Wire the Workflow Builder page's "Saved Workflows" table to real, already-implemented backend data (SPEC-BE-014).

## Scope
In scope: exactly the Saved Workflows table (Name, Trigger, Actions, Runs (7d), Status columns).

Explicitly NOT being built by this spec:
- The workflow canvas (trigger→condition→action node visualization) and the "Test Run" button — a later spec (SPEC-FE-018), since rendering a human-readable canvas from raw trigger_config/condition_dsl/actions JSON needs its own contract confirmation
- "+ New Workflow" and "Version History" — no backend endpoint exists for workflow creation or versioning; these render present but non-functional, matching the established pattern for undefined interactions in this series

## Contract
The real backend endpoint already implemented for the saved-workflows list (SPEC-BE-014). Do not assume field names, route paths, or response shape — confirm them from the real backend code per Functional Rule 1.

## Functional rules
1. Before writing any code, read the real backend's workflows routes/schemas (and CLAUDE.md) to determine: the exact list endpoint path and response shape (name, trigger_type, actions count or actions array to derive a count from, the 7-day run count, and the enabled boolean). If any of this is ambiguous, stop and report exactly what's unclear rather than guessing.
2. Render one table row per real workflow: Name as the real stored name; Trigger as the real raw trigger_type value (e.g. "inventory.low") — render it exactly as returned, do not translate it into prose; Actions as the real count of actions (from a returned count field, or the length of a returned actions array — confirm which the real response provides); Runs (7d) as the real returned 7-day run count; Status as a badge — badge-success "Enabled" if the real enabled field is true, badge-warn "Paused" if false.
3. "+ New Workflow" and "Version History" render present with their exact mockup labels but are non-functional — add a code comment noting no backend endpoint exists for either yet.
4. Table loading/empty/error states: a skeleton or lightweight loading indicator while fetching; a plain "No workflows yet" row if the real list is empty; an inline error message if the fetch fails.

## Edge cases
- A workflow with zero actions: render "0" in the Actions column, not blank.
- A workflow with zero runs in the last 7 days: render "0", not blank or an error.

## Non-functional rules
- No mock/hardcoded workflow rows anywhere.
- Do not build the canvas or Test Run functionality in this spec.
- Must not change SPEC-FE-002's other 9 routes or the sidebar/topbar.
- No new dependency beyond what's installed.

## Acceptance criteria
1. Every rendered workflow row's fields trace to real backend data confirmed in the plan step.
2. The Trigger column shows the real raw trigger_type value unmodified.
3. The Status badge correctly reflects the real enabled boolean.
4. Loading/empty/error states render distinctly and correctly.
5. "+ New Workflow"/"Version History" are present and visibly non-functional, with the documenting comment.
6. SPEC-FE-002's other 9 routes and the sidebar/topbar are unchanged.

## Assumptions
- The real saved-workflows list contract is authoritative per Functional Rule 1.
- The canvas and Test Run wiring are deferred to SPEC-FE-018.

## Target files
- app/(app)/workflows/page.tsx (extends SPEC-FE-002's stub)
- components/workflows/saved-workflows-table.tsx (new)
- lib/api/workflows.ts (new)
- lib/types/workflows.ts (new)
