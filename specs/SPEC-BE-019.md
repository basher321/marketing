Purpose
Implement the Dashboard's "Ad Spend" card, matching exactly: total ad
spend in the trailing 24 hours for the caller's tenant, paired with the
avg ROAS figure already produced by SPEC-BE-009.

Scope
The existing stub files for the campaigns domain: app/models/campaign.py,
app/schemas/campaign.py, app/services/campaign_service.py, and
app/api/v1/campaigns.py - the same four files SPEC-BE-009 uses; this spec
adds one more function and route to that domain, not a new file. No new
files or folders. No ad-level spend breakdown, no per-campaign spend
detail, no budget-editing endpoint - only the tenant-wide spend (24h)
paired with ROAS is in scope.

Contract
After this step: a request returns, for the caller's tenant, total ad
spend in the trailing 24 hours and the avg ROAS figure, with ROAS coming
from the same function SPEC-BE-009 already exposes - not recomputed
independently.

Functional rules
- Ad spend (24h) = sum of spend across the caller's tenant's active
  campaigns/ads for the trailing 24 hours (UTC). Document the exact
  spend field(s) used as a code comment.
- The ROAS value returned by this endpoint is produced by calling SPEC-
  BE-009's existing avg-ROAS function directly - it is not a separate
  computation and must equal what that function returns for the same
  tenant at the same moment.
- Every query filters by tenant_id explicitly, per this codebase's
  existing service convention.

Edge cases
- A tenant with zero ad spend in the trailing 24 hours returns 0, not an
  error.
- If no spend data exists anywhere yet in the schema or models, return 0
  with a code comment stating this is a placeholder pending ad-metrics
  ingestion - never fabricate a plausible-looking number.
- Spend belonging to another tenant never contributes to another
  tenant's figure.

Non-functional rules
No new files or folders - fill in the four existing stub files only. Follow
the existing service pattern: plain functions, explicit db and tenant_id
parameters, no classes. Type hints on every function. No print statements -
structlog only. No test framework exists yet, so verification is manual.

Acceptance criteria
- The endpoint returns ad spend (24h) and ROAS for the caller's tenant
  only.
- The ROAS value returned here is identical to what SPEC-BE-009's
  endpoint returns for the same tenant at the same moment.
- A tenant with zero ad spend in the trailing 24 hours gets 0, no error.
- Spend belonging to a different tenant never affects the result,
  verified with two tenants.
- No ad-level spend breakdown, per-campaign detail, or budget-editing
  endpoint exists as a result of this spec.

Assumptions
app/models/campaign.py, the matching schema file, campaign_service.py,
and api/v1/campaigns.py already exist as stub files with correct
signatures (per CLAUDE.md's "structurally stubbed" list) and already
carry SPEC-BE-009's code - this spec adds to their bodies without
disturbing that existing code.

Target files (all existing - none added, none removed):
backend/app/models/campaign.py
backend/app/schemas/campaign.py
backend/app/services/campaign_service.py
backend/app/api/v1/campaigns.py
