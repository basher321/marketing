# SPEC-FE-034: Workflow Builder — New, Edit, Enable, Test Run, Version History

Status: IMPLEMENTED (2026-09-30), plan approved by the user; verified E2E in headless Edge on dev-shop (test workflow chain, its runs and audit rows removed afterwards). Depends on SPEC-BE-049. Amends SPEC-FE-017/018.

Finding: Test Run already worked (200, succeeded); the problem was that its result appeared below the fold as raw JSON without naming the workflow. It now appears directly under the toolbar in plain words ("Passed — All 2 step(s) would run", with each step's action label).

## Purpose
Make the Workflow Builder work end to end.

## Functional rules
1. **Selection:** the first saved workflow is selected on load. Test Run was disabled until a row was clicked, which made it look broken. The selected row is highlighted, and the canvas title shows "{name} · v{version}".
2. **Test Run:** unchanged behavior (dry run, no external calls). It is always enabled when a workflow is selected. The result panel shows each step's status.
3. **+ New Workflow** and **Edit** open the same editor panel:
   - Name and description.
   - A trigger dropdown, with its config fields from the catalog.
   - A condition field with the catalog's help text and examples.
   - An ordered action list: add, remove, move up/down, type dropdown, params fields from the catalog.
   - "Save" (creating a new version on edit) and "Cancel". Backend 422 messages show inline.
4. **Enable/Disable** toggle per workflow in the table and the canvas.
5. **Version History:**
   - A panel listing the versions (vN, date, author, trigger, number of actions, and "current").
   - "View" shows that version's steps on the canvas (read-only).
   - "Restore" asks for confirmation, then creates a new version.
6. A 403 shows "Only managers and above can edit workflows."

## Acceptance criteria (verified E2E)
Create a workflow, edit it (v2), view v1, restore v1 (v3), toggle it, and test-run it. Each step is checked in the DB. Test rows are removed afterwards.

## Target files
- app/(app)/workflows/page.tsx
- components/workflows/canvas.tsx, components/workflows/saved-workflows-table.tsx, components/workflows/workflow-editor.tsx (new, includes the versions panel)
- lib/api/workflows.ts, lib/types/workflows.ts
