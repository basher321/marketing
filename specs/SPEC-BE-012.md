Purpose
Implement brand settings, matching exactly what the Knowledge Base page's
Brand Settings card shows and saves: brand name, tone (formal ↔ playful),
style (concise ↔ detailed), primary language, and forbidden terms. Logo,
color palette, and disclaimers are not rendered by any control in the
HTML and are explicitly out of scope.

Scope
The existing stub files for the brand domain: app/models/brand.py, the
matching file under app/schemas/, app/services/brand_service.py, and
app/api/v1/brand.py. No new files or folders. No logo upload, no palette
editor, no disclaimers editor, no versioning/history of past settings -
none of that is shown in the HTML.

Contract
After this step: a request returns the caller's tenant's brand name,
tone value, style value, primary language, and forbidden terms; a save
request updates all of those fields for the caller's tenant in one call,
and a following read reflects the change immediately.

Functional rules
- GET returns brand name, tone (0-100), style (0-100), primary language,
  and forbidden terms, for the caller's tenant only.
- Save (PUT or PATCH, matching the existing service convention) updates
  all five fields at once from a single request body, matching the
  HTML's single "Save Brand Settings" button - not a set of independent
  per-field updates.
- If no brand settings row exists yet for a tenant, save creates it
  (upsert) rather than requiring a separate create step; GET before any
  save returns documented default values, not a 404.
- Forbidden terms are exchanged as a list of strings at the API boundary.
  If the underlying storage is a single delimited string rather than an
  array column, document the exact split/join rule as a code comment.
- Every query and mutation filters by tenant_id explicitly, per this
  codebase's existing service convention.
- Every save writes one entry via the existing write_audit_log() function
  in core/audit.py - do not invent a new audit mechanism.

Edge cases
- Saving with an empty forbidden-terms list clears it, not leaves the
  previous value in place.
- A tone or style value outside 0-100 is rejected with a validation
  error, not silently clamped.
- A tenant's brand settings are never returned to, or overwritten by, a
  different tenant.

Non-functional rules
No new files or folders - fill in the four existing stub files only. Follow
the existing service pattern: plain functions, explicit db and tenant_id
parameters, no classes. Type hints on every function. No print statements -
structlog only. No test framework exists yet, so verification is manual.

Acceptance criteria
- GET returns brand name, tone, style, primary language, and forbidden
  terms for the caller's tenant only.
- A save call updates all five fields for the caller's tenant in one
  request, and a following GET reflects the change.
- A tenant with no saved brand settings yet gets documented defaults from
  GET, not an error.
- A tone or style value outside 0-100 is rejected.
- A save produces one new audit_log row.
- A different tenant's brand settings are never returned or modified,
  verified with two tenants.
- No logo, palette, or disclaimers endpoint exists as a result of this
  spec.

Assumptions
app/models/brand.py, the matching schema file, brand_service.py, and
api/v1/brand.py already exist as stub files with correct signatures (per
CLAUDE.md's "structurally stubbed" list) - this spec fills their bodies
in, it does not create them. core/audit.write_audit_log() already exists
and works as documented in CLAUDE.md.

Target files (all existing - none added, none removed):
backend/app/models/brand.py
backend/app/schemas/brand.py
backend/app/services/brand_service.py
backend/app/api/v1/brand.py
