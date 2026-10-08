Purpose
Implement the saved workflows list, matching exactly what the Workflows
page's "Saved Workflows" table shows: Name, Trigger, Actions, Runs (7d),
and Status. The workflow canvas builder, Test Run, and Version History
are not implemented here.

Scope
The existing stub files for the workflows domain: app/models/workflow.py,
the matching file under app/schemas/, app/services/workflow_service.py,
and app/api/v1/workflows.py. No new files or folders. No create, update,
or delete of a workflow, no test-run, no version history, no visual
builder - none of that is rendered in the Saved Workflows table.

Contract
After this step: a request returns the caller's tenant's workflows, each
with name, trigger type, its action count, its run count over the
trailing 7 days, and its status.

Functional rules
- List endpoint returns workflows for the caller's tenant only, each
  with: name, trigger type, count of actions, count of runs in the
  trailing 7 days, and status.
- Actions count = the length of the workflow's own stored actions array -
  do not recompute or hardcode it elsewhere.
- Runs (7d) = the count of workflow_runs rows for that workflow with a
  start timestamp in the trailing 7 days (UTC). Document the exact
  timestamp field used as a code comment.
- Status is displayed as "Enabled" or "Paused", mapped from the
  workflow's existing status/enabled field. Document the exact mapping
  as a code comment - never invent a status value the existing model
  does not have.
- Every query filters by tenant_id explicitly, per this codebase's
  existing service convention.

Edge cases
- A workflow with zero actions returns an actions count of 0, not an
  error.
- A workflow with zero runs in the trailing 7 days returns 0, not an
  error.
- A workflow belonging to another tenant never appears in the list.

Non-functional rules
No new files or folders - fill in the four existing stub files only. Follow
the existing service pattern: plain functions, explicit db and tenant_id
parameters, no classes. Type hints on every function. No print statements -
structlog only. No test framework exists yet, so verification is manual.

Acceptance criteria
- The list endpoint returns only the caller's tenant's workflows, each
  with name, trigger, actions count, runs (7d), and status.
- The actions count matches the number of actions actually stored on the
  workflow.
- Runs (7d) matches the number of workflow_runs rows in the trailing 7
  days for that workflow.
- A workflow belonging to a different tenant never appears in the list,
  verified with two tenants.
- No create, update, delete, test-run, or version-history endpoint
  exists as a result of this spec.

Assumptions
app/models/workflow.py, the matching schema file, workflow_service.py,
and api/v1/workflows.py already exist as stub files with correct
signatures (per CLAUDE.md's "structurally stubbed" list) - this spec
fills their bodies in, it does not create them. The workflows and
workflow_runs tables already exist in the database.

Target files (all existing - none added, none removed):
backend/app/models/workflow.py
backend/app/schemas/workflow.py
backend/app/services/workflow_service.py
backend/app/api/v1/workflows.py
