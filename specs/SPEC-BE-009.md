Purpose
Implement campaign summary metrics, matching exactly what the Marketing
page's "Active Campaigns" and "Avg. ROAS" cards show, and the same two
numbers on the Dashboard's Marketing engine card. "Scheduled Posts" and
"CTR (7d)" belong to a different domain and are explicitly out of scope
for this spec.

Scope
The existing stub files for the campaigns domain: app/models/campaign.py,
the matching file under app/schemas/, app/services/campaign_service.py,
and app/api/v1/campaigns.py. No new files or folders. No campaign list or
detail endpoint, no create, launch, or pause action, no ad-group or ad-
level detail - the Active Campaigns table (Campaign/Objective/Channels/
Budget/ROAS/Status) is a separate, later spec.

Contract
After this step: one request returns, for the caller's tenant, the count
of active campaigns and the average ROAS across those campaigns - the same
two numbers backing both the Marketing page's top cards and the
Dashboard's Marketing engine card.

Functional rules
- Active campaign count = campaigns for the caller's tenant whose status
  falls in the "active/running" set. Document the exact status value(s)
  used as a code comment, matching the existing campaign_status enum - do
  not invent new values.
- Avg ROAS = the average of the ROAS figure across those same active
  campaigns, computed from whatever ROAS/spend/revenue fields already
  exist on campaign or its related records. Document the exact
  computation as a code comment.
- Both numbers are produced by one function and reused by both call sites
  (Marketing page, Dashboard engine card) - never computed twice with
  different logic.
- Every query filters by tenant_id explicitly, per this codebase's
  existing service convention.

Edge cases
- A tenant with zero active campaigns returns count 0 and avg ROAS as 0
  (or null - pick one and document it), not a division-by-zero error.
- If no ROAS-relevant data exists anywhere yet in the schema/models,
  return 0 with a code comment stating this is a placeholder pending ad-
  metrics ingestion - never fabricate a plausible-looking number.
- A campaign belonging to another tenant never contributes to another
  tenant's count or average.

Non-functional rules
No new files or folders - fill in the four existing stub files only. Follow
the existing service pattern: plain functions, explicit db and tenant_id
parameters, no classes. Type hints on every function. No print statements -
structlog only. No test framework exists yet, so verification is manual.

Acceptance criteria
- The endpoint returns the active campaign count and avg ROAS for the
  caller's tenant only.
- The Marketing-page-backing call and the Dashboard-engine-card-backing
  call return the identical two numbers, from the same underlying
  computation.
- A tenant with zero active campaigns gets count 0 and avg ROAS 0 (or the
  documented null), no error.
- A campaign belonging to a different tenant never affects the count or
  average, verified with two tenants.
- No list, detail, create, launch, or pause endpoint exists as a result of
  this spec.

Assumptions
app/models/campaign.py, the matching schema file, campaign_service.py, and
api/v1/campaigns.py already exist as stub files with correct signatures
(per CLAUDE.md's "structurally stubbed" list) - this spec fills their
bodies in, it does not create them. The campaigns table and its status
enum already exist in the database.

Target files (all existing - none added, none removed):
backend/app/models/campaign.py
backend/app/schemas/campaign.py
backend/app/services/campaign_service.py
backend/app/api/v1/campaigns.py
