# SPEC-BE-038: Marketing — Active Campaigns List + Content Calendar

Status: IMPLEMENTED (2026-09-29), under the user's "build every page so I can test the full software" instruction. Open decisions below were settled with the stated recommendation, with no separate plan review.

## Purpose
Back the Marketing page's two sections that SPEC-FE-012 left out because no endpoint existed: the "Active Campaigns" table (Campaign, Objective, Channels, Budget, ROAS, Status) and the "Content Calendar" (Mon–Sun, each day listing its scheduled posts, e.g. "FB Post", "IG Story").

## Scope
In scope: two read-only endpoints.
- `GET /api/v1/campaigns`: the tenant's current campaigns.
- `GET /api/v1/scheduled-posts/calendar`: the tenant's posts for the current week.

Not in scope: campaign create/edit/launch/pause, per-ad metrics, drag-and-drop scheduling, calendar navigation to other weeks.

## Contract
`GET /api/v1/campaigns` → 200 `[{ id, name, objective, channels, budget, currency, duration_days, roas, status }]`
- `budget`: major units from `budget_cents` (Decimal).
- `duration_days`: whole days from `starts_at` to `ends_at`; null if either is missing.
- `roas`: always `null`. No revenue or conversion-value column exists anywhere in the live schema (the same finding as SPEC-BE-009's avg ROAS placeholder), so it is never estimated.
- `status`: the raw live `campaign_status`.

`GET /api/v1/scheduled-posts/calendar` → 200 `{ week_start: date, timezone, days: [{ date, posts: [{ id, channel, format, status, scheduled_at }] }] }`
- Always exactly 7 days, Monday to Sunday.

## Functional rules
1. **Campaign list:** `status` in (`running`, `scheduled`, `paused`), meaning campaigns that are live or about to be. `draft`, `completed` and `failed` are not "active". Order: `starts_at` descending (NULLs last), then name. Filtered by tenant.
2. **Calendar week:** the Monday–Sunday week containing "now", in the **tenant's timezone** (`tenants.timezone`), computed in Postgres (`date_trunc('week', now() AT TIME ZONE tz)`). Each post is bucketed by its `scheduled_at` converted to that timezone.
3. **Posts shown:** `status` in (`pending`, `scheduled`, `publishing`, `published`); `failed` and `cancelled` are excluded. `format` comes from the post's content asset (`content_assets.format`). Order within a day: `scheduled_at`. Filtered by tenant on both `scheduled_posts` and `content_assets`.
4. **Timestamps:** returned in UTC; dates are the tenant-local calendar dates.

## Acceptance criteria
1. Only this tenant's `running`/`scheduled`/`paused` campaigns are listed, with budget in major units, duration in days, `roas` null.
2. The calendar always has 7 days starting on a Monday, in the tenant's timezone. A post appears on its tenant-local date, and excluded statuses and other tenants' posts never appear.
3. Both endpoints return 200 with empty lists/days for a tenant with no data.

## Target files
- backend/app/schemas/campaign.py, backend/app/services/campaign_service.py, backend/app/api/v1/campaigns.py
- backend/app/schemas/scheduled_post.py, backend/app/services/scheduler_service.py, backend/app/api/v1/scheduled_posts.py
