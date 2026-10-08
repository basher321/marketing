# SPEC-BE-056: Meta results import → real status and metrics in Analytics

Status: IMPLEMENTED, VERIFIED ON THE LIVE DB (2026-10-01). The plan was approved as recommended (all 9 decisions). Done: ruff/mypy at baseline, the app imports, `next build` passes, and the logic was checked in-process with `httpx.MockTransport` (no DB). The additive DDL was applied 2026-10-01. Live-DB verified 2026-10-01 (rolled-back run; all acceptance checks pass). Deviation kept: the tenant-wide ads report's conversions = purchases + leads + installs; per-campaign results use the objective's metric. Source: Developer Change Spec §2 ("Analytics must read real campaign results from the connected account") and acceptance test Meta-D. SPEC-BE-054 reserved this number for exactly this. Depends on SPEC-BE-054/055. Frontend: SPEC-FE-042.

Implementation notes: `AdSpend24h.avg_roas` also became nullable. Each run fires the `ad_threshold_crossed` workflow trigger with 7-day KPIs.

## Purpose
Today no spend, impressions, clicks or conversions reach the app: `GET /ads/ctr-7d` is a documented `0.0` placeholder, and the SPEC-BE-050 ads report returns null CTR and ROAS. This spec imports **real** daily results from the connected Meta ad account and feeds them into the existing reports. It still never estimates: a metric Meta didn't return stays null.

## Source and storage
- **Source:** Meta Insights API, `GET {campaign_id}/insights` with `level=ad`, `time_increment=1`, `time_range={since, until}`, `fields=spend,impressions,reach,clicks,inline_link_clicks,actions,action_values,frequency`, `action_attribution_windows` left at the account default. One call per published campaign (paged with `after` cursors).
- **Storage:** the live `analytics_events` table, which the SPEC-BE-019/050 reports already read. One row per (ad, day, metric):
  - `source = 'meta'`, `event_type = 'meta_insights'`, `entity_type = 'ad'`, `entity_id` = our `ads.id`.
  - `event_time` = that day 00:00 in the **ad account's** timezone (Meta's day boundary), stored as UTC.
  - `dimensions` = `{campaign_id, ad_group_id, meta_ad_id, date, currency}`.
  - Metrics (names are the contract): `spend_cents` (Meta spend × 100 via Decimal; offset-1 currencies × 100 too, so it stays in our cents), `impressions`, `reach`, `clicks` (all clicks), `link_clicks`, `purchases`, `purchase_value_cents`, `leads`, `app_installs`, `post_engagement`, `video_thruplays`.
  - Action-derived metrics read only these `action_type`s: `offsite_conversion.fb_pixel_purchase` / `purchase` (purchases + value), `lead` / `onsite_conversion.lead_grouped` (leads), `mobile_app_install` (app_installs), `post_engagement`, `video_thruplay_watched_actions`. Documented as a code comment.
- **Idempotent:** each import deletes the `source='meta'` rows for that campaign's ads in the imported date window, then inserts, in one transaction. Meta revises recent days, so every run re-imports the **last 3 days** plus any missing days.
- **Running totals:** `campaigns.spent_cents` = the sum of imported `spend_cents` for the campaign (so the existing budget/cap displays are real).
- **Status sync:** the same job reads `effective_status` and `configured_status` for the campaign, ad sets and ads (SPEC-BE-055 rule 10) and maps them onto our `campaign_status`:
  ACTIVE → running; PAUSED / CAMPAIGN_PAUSED / ADSET_PAUSED → paused; PENDING_REVIEW / IN_PROCESS / PREAPPROVED → keeps `scheduled`/`running` with `metadata.effective_status` showing the review state; DISAPPROVED / WITH_ISSUES → keeps status, sets `metadata.last_error`; DELETED / ARCHIVED → completed; past `end_time` with no delivery → completed. A change made in Ads Manager therefore shows up in the app.

## Triggers
1. **Scheduled:** the existing APScheduler job in `workers/tasks/ad_tasks.py` (today an inert stub) runs every 3 hours (`SCHEDULER_*` unchanged) for every tenant with a `connected` `meta_ads` integration and published campaigns that were running in the last 30 days.
2. **On demand:** `POST /api/v1/campaigns/{id}/sync` (manager+) and `POST /api/v1/analytics/meta/sync` (manager+, all campaigns) → `{synced_campaigns, rows_written, last_sync_at, errors}`. Throttled to once per 5 minutes per tenant (409 with the wait).
3. The import never runs inside a user's publish request.

## Reports (existing endpoints, real values replace nulls)
- `GET /ads/ctr-7d` → `link_clicks ÷ impressions × 100` over the last 7 days of `source='meta'` rows; **null when there are no impressions** (the response schema changes `ctr_7d_pct: float` → `float | null`; open decision 2). The `0.0` placeholder comment is replaced by this rule.
- `GET /analytics/ads?range=` (SPEC-BE-050): CTR and ROAS per day and in totals. ROAS = `purchase_value_cents ÷ spend_cents`, null when spend is 0 or no purchase values were reported. Adds `impressions`, `reach`, `clicks`, `conversions` (the campaign objective's result metric: purchases / leads / installs / link_clicks / post_engagement).
- `GET /campaigns/metrics` (SPEC-BE-009) ROAS → the same rule over the last 30 days instead of always null.
- New `GET /campaigns/{id}/results?range=7d|30d|90d|lifetime` → per-day series + per-ad-set and per-ad totals, plus `last_sync_at`, `effective_status`, and `source: "meta"`.
- Spend that came from an approved but unpublished campaign doesn't exist, so nothing is invented for internal-only channels.

## Sync status
`integrations.last_sync_at` and `integrations.last_error` (live columns) for the `meta_ads` row, plus `integrations.metadata.insights_sync = {last_success_at, last_window, campaigns, rows, errors: [{campaign_id, message, at}]}` (last 20 errors). Audit `meta.insights_synced` (one per run, counts only) and `meta.insights_failed`.

## Errors
- Code 190 → integration `expired` (SPEC-BE-054 rule 5); the run stops for that tenant.
- Rate limit (4, 17, 32, 613, 80000–80014) → stop this tenant's run, keep what was written, retry next schedule.
- A deleted campaign on Meta (code 100 / "does not exist") → campaign marked `completed` with `metadata.meta.deleted_on_meta = true`.

## Open decisions (recommendation first)
1. **Storage.** *Recommend:* `analytics_events` (the reports already read it; replace-window keeps it idempotent). *Alternative:* `analytics_daily_rollups` (it has a unique index, but every report would need a second source).
2. **CTR placeholder schema change** (`float` → nullable). *Recommend:* yes, so "no data" isn't shown as 0%. The frontend card shows "—".
3. **Schedule frequency.** *Recommend:* every 3 hours + on-demand. Meta itself updates insights roughly every 15 min, but per-account rate limits are tight.

## Acceptance criteria (live Postgres, rolled-back transaction, Meta answered by `httpx.MockTransport`)
1. A fixture insights response for 2 ads × 3 days → exactly the documented rows (metric names, cents, account-timezone day), `campaigns.spent_cents` updated.
2. Re-running the same import → same row count (idempotent); a revised spend for day 3 replaces the old value.
3. `GET /analytics/ads?range=7d` returns real CTR/ROAS computed from those rows; `GET /ads/ctr-7d` returns the 7-day CTR; with no impressions both are null.
4. **Meta-D status:** an ad `DISAPPROVED` and a campaign paused in Ads Manager → our statuses and `effective_status`/`last_error` updated.
5. Code 190 → integration `expired`; rate limit → partial data kept, error recorded in `insights_sync.errors`.
6. On-demand sync throttle → 409 within 5 minutes.
7. Tenant isolation; scheduler job registered and runs once against the fixture; ruff/mypy no new errors.

## Target files
`integrations/meta_ads.py` (insights + status reads), `workers/tasks/ad_tasks.py` (job body), `workers/schedules.py` (interval), `services/campaign_service.py` (sync, results), `services/analytics_service.py` (CTR/ROAS/conversions from meta rows), `services/ad_service.py` (CTR 7d), `schemas/campaign.py`, `schemas/analytics.py`, `api/v1/campaigns.py`, `api/v1/analytics.py`, `models/analytics.py` (`AnalyticsEvent` aligned to the live columns: `event_time`, `metric`, `value`, `source`, `dimensions` — today it is misaligned).
