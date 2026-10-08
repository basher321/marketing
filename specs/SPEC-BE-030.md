Purpose
Implement the endpoint that generates and persists ad-creative variants
for a campaign, wiring SPEC-BE-029's generation function into the content
domain so the Campaign Wizard's "AI-Generated Creative Variants" step
can list, select, and edit real generated variants instead of hardcoded
demo content.

Scope
The existing stub files for the content domain: app/models/content.py,
the matching file under app/schemas/, app/services/content_service.py,
and app/api/v1/content.py. No new files or folders. No change to the
generation function itself (SPEC-BE-029, called as-is), no image
generation, no campaign launch or scheduling logic - only generating,
persisting, listing, and selecting a variant are in scope.

Contract
After this step: a request triggers ad-creative generation for a
campaign brief, calling SPEC-BE-029's generation function, and persists
the resulting variants as one content_assets record for the caller's
tenant; a request lists the persisted variants for that record; a
request marks one variant as selected.

Functional rules
- Generate endpoint calls SPEC-BE-029's existing generation function
  directly - it does not reimplement any retrieval, LLM, or moderation
  logic itself.
- The generated variants are persisted as one content_assets row
  (matching the existing variants JSONB array and selected_variant_index
  columns) for the caller's tenant.
- Get endpoint returns the persisted variants for one content_assets
  record, for the caller's tenant only.
- Select endpoint sets selected_variant_index to one of the persisted
  variants' indices for the caller's tenant's record. Selecting an out-
  of-range index is rejected with a validation error.
- Every query and mutation filters by tenant_id explicitly, per this
  codebase's existing service convention.
- Every generate and every select action writes one entry via the
  existing write_audit_log() function in core/audit.py.

Edge cases
- If SPEC-BE-029's function raises its typed error, this endpoint
  surfaces a clear error and persists nothing.
- Acting on a content_assets record belonging to another tenant returns
  404.
- Selecting a variant index before any variants exist for that record is
  rejected.

Non-functional rules
No new files or folders - fill in the four existing stub files only. Follow
the existing service pattern: plain functions, explicit db and tenant_id
parameters, no classes. Type hints on every function. No print statements -
structlog only, following SPEC-BE-029's existing observability
convention for the generate call. No test framework exists yet, so
verification is manual.

Acceptance criteria
- Generate produces a content_assets row with the variants SPEC-BE-029's
  function returned, for the caller's tenant.
- Get returns those persisted variants for the caller's tenant only.
- Select updates selected_variant_index to a valid index; an out-of-
  range index is rejected.
- If generation fails, nothing is persisted.
- Acting on a record belonging to a different tenant returns 404,
  verified with two tenants.
- Every generate and select action produces exactly one audit_log row.
- No image-generation or campaign-launch endpoint exists as a result of
  this spec.

Assumptions
app/models/content.py, the matching schema file, content_service.py, and
api/v1/content.py already exist as stub files with correct signatures
(per CLAUDE.md's "structurally stubbed" list) - this spec fills their
bodies in, it does not create them. The content_assets table already
exists in the database. SPEC-BE-029's generation function is implemented
and importable.

Target files (all existing - none added, none removed):
backend/app/models/content.py
backend/app/schemas/content.py
backend/app/services/content_service.py
backend/app/api/v1/content.py
