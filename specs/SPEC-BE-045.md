# SPEC-BE-045: Campaign Wizard — Audiences (saved targeting)

Status: IMPLEMENTED (2026-09-30), plan approved by the user; verified on live Postgres (rolled-back txn).

## Purpose
Back the wizard's **Audience** step. Ad managers let you pick a saved audience or define a new one (location, age, gender, interests, language). The live `audiences` table exists, but there's no model, schema, service or route for it.

## Scope
In scope: list and create saved audiences.

Not in scope: size estimates, lookalike or custom (customer-list) audiences, edit, and delete. `estimated_size` is always returned as null because there is no ad-platform data to estimate from, so it is never guessed.

## Contract
`GET /api/v1/audiences` → 200 `{ count, items: [AudienceRead] }`, sorted by name.

`POST /api/v1/audiences` (manager+) → 201 `AudienceRead`
```
{ name (1-255), description?,
  targeting: {
    countries: [ISO alpha-2, >= 1],   regions: [str],        # e.g. ["Dhaka"]
    age_min: 13-65 (default 18),      age_max: age_min-65 (default 65),
    genders: ["male","female"] subset (empty = all),
    interests: [str] (<= 50),         languages: [str] (<= 10, e.g. "bn","en") } }
AudienceRead = { id, name, description, targeting, estimated_size: null, created_at }
```

## Functional rules
1. `targeting` is stored as-is (normalized) in `audiences.targeting` jsonb. Country codes are upper-cased and de-duplicated, blank entries are dropped, and `channel` is left NULL (one audience can serve every channel).
2. Tenant-scoped. `created_by` = the acting user. The name must be unique per tenant (checked in the service), otherwise 409.
3. Creating an audience writes an audit row (`audience.create`).

## Acceptance criteria
1. List returns only this tenant's audiences.
2. Create persists normalized targeting. Viewer gets 403. Invalid ages, countries or a missing name give 422. A duplicate name gives 409.

## Target files (new domain, so 4 new files, plus one registration line)
- backend/app/models/audience.py (new)
- backend/app/schemas/audience.py (new)
- backend/app/services/audience_service.py (new)
- backend/app/api/v1/audiences.py (new)
- backend/app/api/router.py (register the router)
