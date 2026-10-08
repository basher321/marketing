Purpose
Implement the 7-day click-through-rate (CTR) metric, matching exactly what
the Marketing page's "CTR (7d)" card shows, for the caller's tenant. No
other metric, table, or ad-management action is in scope.

Scope
The existing stub files for the ads domain: app/models/ad.py, the matching
file under app/schemas/, app/services/ad_service.py, and
app/api/v1/ads.py. No new files or folders. No ad list or detail endpoint,
no ad-group management, no create, pause, or optimize action - only the
tenant-wide CTR (7d) number is in scope.

Contract
After this step: one request returns, for the caller's tenant, the click-
through rate (clicks divided by impressions) aggregated across all of
that tenant's ads over the trailing 7 days - the single number backing the
Marketing page's "CTR (7d)" card.

Functional rules
- CTR (7d) = total clicks divided by total impressions across the
  caller's tenant's ads, for records timestamped within the trailing 7
  days (UTC), expressed as a percentage.
- Compute from whatever impression/click fields already exist on the ad
  or its related metrics records. Document the exact source field(s) and
  the computation as a code comment.
- Every query filters by tenant_id explicitly, through the ad's
  relationship to the tenant's campaigns/ad_groups - document that join
  path as a code comment.

Edge cases
- A tenant with zero impressions in the trailing 7 days returns CTR 0, not
  a division-by-zero error.
- If no ad impression/click data exists anywhere yet in the schema or
  models, return 0 with a code comment stating this is a placeholder
  pending ad-metrics ingestion - never fabricate a plausible-looking
  number.
- An ad belonging to another tenant never contributes to another
  tenant's CTR.

Non-functional rules
No new files or folders - fill in the four existing stub files only. Follow
the existing service pattern: plain functions, explicit db and tenant_id
parameters, no classes. Type hints on every function. No print statements -
structlog only. No test framework exists yet, so verification is manual.

Acceptance criteria
- The endpoint returns CTR (7d) for the caller's tenant only.
- A tenant with zero impressions in the trailing 7 days gets CTR 0, no
  error.
- An ad belonging to a different tenant never affects the result,
  verified with two tenants.
- No list, detail, create, pause, or optimize endpoint exists as a result
  of this spec.

Assumptions
app/models/ad.py, the matching schema file, ad_service.py, and
api/v1/ads.py already exist as stub files with correct signatures (per
CLAUDE.md's "structurally stubbed" list) - this spec fills their bodies
in, it does not create them. The ads and ad_groups tables already exist
in the database, whether or not impression/click data has been populated
yet.

Target files (all existing - none added, none removed):
backend/app/models/ad.py
backend/app/schemas/ad.py
backend/app/services/ad_service.py
backend/app/api/v1/ads.py
