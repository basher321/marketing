# SPEC-BE-050: Analytics — Ads, Engagement, Customer Service reports

Status: IMPLEMENTED (2026-10-01; started in the 2026-09-30 session, finished after an interruption); verified on live Postgres (rolled-back txn, 35/35 checks: totals, tenant-timezone day buckets around local midnight, zero-fill, 7d/30d/90d, nulls on an empty tenant, 422 on a bad range, 401 without a token, tenant isolation).

## Implementation notes (deviations / clarifications)
- **Window** = the last N local calendar days in `tenants.timezone`, today included.
- **Ads:** `totals.spend` and `spend_by_day` include spend from every campaign in the window, including completed ones. The `campaigns` table lists only running/scheduled/paused campaigns. Its `spend` is window spend, while `pacing_pct` and `budget_used_pct` use lifetime spend. `active_campaigns` = status `running`.
- **Engagement:** published counts posts by `published_at` in the window, and failed counts by `updated_at`. Scheduled and pending are the current pipeline, with any date. In `posts_by_channel`, `scheduled` includes pending posts. `posts_by_day` covers the window plus the next 7 days, so upcoming posts are visible. Channels with no posts are omitted.
- **Customer service:** conversations count when they were created in the window. `escalated` = `metadata.handed_off_at` is set (the live `conversation_status` enum has no escalated value). First response and AI/agent replies count only **sent** outbound messages (`sent_at`), so a pending AI draft (`sent_at` NULL) never counts as a reply. `system` messages are excluded.

## Purpose
Back the three empty Analytics tabs (SPEC-FE-035) with real numbers from the live DB, like the standard reports in ad and helpdesk tools. **Rule: a metric with no source data is returned as null and shown as "—" with a reason. It is never estimated** (the same rule as SPEC-BE-009/011's ROAS and CTR).

All endpoints take `?range=7d|30d|90d` (default 30d) and bucket by day in the **tenant timezone**, with every missing day filled with 0.

## Contract
`GET /api/v1/analytics/ads` →
```
{ currency, range, totals: { spend, active_campaigns, budget_total, budget_used_pct: float|null,
    impressions: null, clicks: null, ctr: null, roas: null,
    missing_reason: "No impression/click/revenue data — connect an ads account (Integrations)." },
  spend_by_day: [{date, spend}],
  campaigns: [{id, name, status, channels, budget, spend, pacing_pct|null, starts_at, ends_at}] }
```
- Spend comes from `analytics_events` (`metric = spend_cents`, entity campaign/ad → campaign), the same source as SPEC-BE-019.
- `pacing_pct` = spend ÷ (budget × elapsed-share of the schedule).

`GET /api/v1/analytics/engagement` →
```
{ range, posts: { published, scheduled, pending, failed },
  posts_by_channel: [{channel, published, scheduled}], posts_by_day: [{date, published, scheduled}],
  content: { draft, pending_approval, approved, published },
  likes: null, comments: null, shares: null, reach: null,
  missing_reason: "Post engagement isn't imported yet — connect Facebook/Instagram/TikTok." }
```
Sources: `scheduled_posts` (status, channel, scheduled_at/published_at) and `content_assets` (status).

`GET /api/v1/analytics/customer-service` →
```
{ range, conversations: { total, open, pending, resolved, escalated },
  by_channel: [{channel, total, resolved}], by_day: [{date, new, resolved}],
  first_response_minutes_avg: float|null, resolution_hours_avg: float|null,
  csat_avg: float|null, csat_responses: int,
  replies: { ai: int, agent: int, ai_share_pct: float|null },
  deflection_pct: float|null }
```
- **First response:** first outbound message after the first inbound message, per conversation. `first_response_at` is empty in live data, so it is derived from `messages`.
- **Resolution:** `resolved_at − created_at`.
- **CSAT:** average of `csat_score`.
- **Deflection:** resolved conversations with no agent-sent message ÷ resolved conversations.

## Functional rules
1. Tenant-scoped, read-only, any authenticated role. Each endpoint uses a small number of aggregate queries, with no N+1.
2. Every formula above is documented as a code comment.

## Acceptance criteria
Seeded rows in a rolled-back transaction produce exactly the expected totals, daily series (tenant-timezone buckets, zero-filled), averages and nulls.

## Target files
- backend/app/schemas/analytics.py, services/analytics_service.py, api/v1/analytics.py
