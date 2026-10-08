Purpose
Implement the Integrations connection-status list, matching what the
Integrations page's cards show for the caller's tenant: each supported
provider's connection status (connected / needs reconnect / not
connected) and, when connected, its last-synced time. Provider-specific
descriptive copy shown in some cards (e.g. "2,431 products synced", "Add
search & display campaigns") is presentational frontend text, not sourced
from this endpoint.

Scope
The existing stub files for the integrations domain:
app/models/integration.py, the matching file under app/schemas/,
app/services/integration_service.py, and app/api/v1/integrations.py. No
new files or folders. No OAuth connect/reconnect flow, no credential
storage or rotation, no manual sync-trigger endpoint - only the status
list is in scope.

Contract
After this step: a request returns, for the caller's tenant, every
supported provider with its connection status and, when connected, its
last-synced timestamp.

Functional rules
- The set of supported providers is a fixed, documented list in code,
  matching the platforms shown in the HTML - it is not derived from user
  data.
- For each provider, status is: "connected" if the tenant has an
  integration record for it with no expired credential; "needs_reconnect"
  if a record exists but its credential has expired; "not_connected" if
  no record exists for that tenant. Document this three-way rule as a
  code comment.
- last_synced_at is returned only for connected providers, sourced from
  that integration record's own last-sync field - omitted or null for
  needs_reconnect and not_connected providers.
- Every query filters by tenant_id explicitly, per this codebase's
  existing service convention.

Edge cases
- A tenant with no integrations connected at all returns every supported
  provider marked not_connected, not an error or an empty list.
- A provider whose credential-expiry field is null is treated as
  connected (never expiring), not needs_reconnect - document this as a
  code comment.
- An integration record belonging to another tenant never affects another
  tenant's status list.

Non-functional rules
No new files or folders - fill in the four existing stub files only. Follow
the existing service pattern: plain functions, explicit db and tenant_id
parameters, no classes. Type hints on every function. No print statements -
structlog only. No test framework exists yet, so verification is manual.

Acceptance criteria
- The endpoint returns every supported provider with its status, for the
  caller's tenant only.
- A connected provider includes its last-synced timestamp; a not-
  connected or needs-reconnect provider never fabricates one.
- A tenant with zero connected integrations gets every provider marked
  not_connected, no error.
- An integration belonging to a different tenant never affects another
  tenant's list, verified with two tenants.
- No connect, reconnect, disconnect, or sync-trigger endpoint exists as a
  result of this spec.

Assumptions
app/models/integration.py, the matching schema file,
integration_service.py, and api/v1/integrations.py already exist as stub
files with correct signatures (per CLAUDE.md's "structurally stubbed"
list) - this spec fills their bodies in, it does not create them. The
integrations table already exists in the database.

Target files (all existing - none added, none removed):
backend/app/models/integration.py
backend/app/schemas/integration.py
backend/app/services/integration_service.py
backend/app/api/v1/integrations.py
