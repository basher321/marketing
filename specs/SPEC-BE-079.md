# SPEC-BE-079: Paid Marketing lists — Ad Sets and Ads across campaigns

Status: IMPLEMENTED (code, 2026-10-03). The user said "write spec and then go for all and execute", so there was no separate plan approval. `ruff`/`mypy` add no errors; routes, auth (401) and UUID path validation are checked without a DB. **Pending:** acceptance 1–4 on the live DB (Postgres isn't installed or running on this machine). Deviation: ad items also carry `currency`, which is needed to format spend. The user's final UI asks for Paid Marketing › Campaigns / Ad Sets / Ads / Drafts / Analytics. Frontend: SPEC-FE-051.

## Purpose
Today ad sets and ads are only visible inside one campaign's builder tree (`GET /campaigns/{id}/builder`, `GET /ads/campaigns/{id}`). Ads Manager also lists every ad set and every ad across campaigns, with status, budget, schedule and results, and lets you pause/resume from the list. This spec adds those two read endpoints plus one pause/resume endpoint per level that dispatches to the right builder, so the frontend never needs to know which builder made a row.

## Sources (no new table, no DDL)
| Builder | Campaign marker | Ad set fields | Ad fields |
|---|---|---|---|
| Meta builder (SPEC-BE-055) | `campaigns.metadata.builder` present, `metadata.platform` null or `meta` | `ad_groups.budget_cents`, `metadata.budget_type/starts_at/ends_at/optimization_goal/effective_status/last_error` | `ads.metadata.headline/primary_text/call_to_action/destination.url/media[0].thumbnail_url/effective_status/review_feedback` |
| Multi-platform builder (SPEC-BE-062) | `metadata.platform` in the six others | `ad_groups.metadata.platform_fields.budget_cents/budget_mode/starts_at/ends_at` | `ads.metadata.creative.headline` (or `card_headline`), text = `primary_text`/`text`/`intro_text`/`description`, `cta`, `destination_url` |
| Legacy wizard (SPEC-BE-047) | no `builder`, no `platform` | `ad_groups.budget_cents` | `ads.metadata` variant text |

`platform` in responses: `meta`, the six builder keys, or `wizard`.

## Endpoints (viewer+ for reads, manager+ for pause/resume)
### `GET /paid/ad-sets`
Query: `platform`, `status` (a `campaign_status` value), `campaign_id`, `q` (name contains, case-insensitive, max 100), `range` = `7d|30d|90d` (default `30d`, for the results columns), `page` (≥1), `page_size` (1–200, default 50).

Response `{count, items}`; each item:
`{id, name, campaign_id, campaign_name, platform, status, effective_status, last_error, budget, budget_type ("daily"|"lifetime"|"campaign"|null), currency, starts_at, ends_at, performance_goal, ads_count, spend, impressions, clicks, ctr, results_level ("ad"|"campaign"|null)}`

### `GET /paid/ads`
Same query parameters plus `ad_set_id`. Each item:
`{id, name, ad_set_id, ad_set_name, campaign_id, campaign_name, platform, status, effective_status, review_feedback, last_error, headline, text (first 160 chars), call_to_action, destination_url, thumbnail_url, external_id, currency, spend, impressions, clicks, ctr, results_level}`

### `POST /paid/ad-sets/{id}/pause|resume`, `POST /paid/ads/{id}/pause|resume`
Look up the row (tenant-scoped; another tenant's row → 404), find its campaign's builder, and call the existing `meta_builder_service.set_status` (levels `ad_set`/`ad`) or `ads_builder_service.set_status` (levels `group`/`ad`). Their rules, errors (409 not published / wrong status, 502 platform error) and audit entries apply unchanged. A wizard row → 409 "This ad set was made with the old wizard; pause its campaign instead." Response `{id, name, level, status}`.

## Rules
- **Ordering:** newest campaign first, then the row's `created_at`.
- **Tenant isolation:** every query filters `tenant_id` on campaigns, ad_groups and ads.
- **Results** (spend in major units, impressions, clicks, CTR %) come from `analytics_events` in the range window:
  - Meta writes **per-ad** rows (`entity_type='ad'`, SPEC-BE-056): an ad's results are its own rows; an ad set's results are the sum over its ads. `results_level = "ad"`.
  - The other six platforms write **per-campaign** rows only (SPEC-BE-062): their ad sets and ads get `null` results and `results_level = "campaign"` (the UI says "reported per campaign").
  - No rows at all → `null` (never 0, never an estimate). CTR = `link_clicks / impressions × 100`, 2 decimals, null without impressions.
- Money is `Decimal(cents) / 100`, with the campaign's currency.
- Datetimes are returned in UTC.

## Acceptance criteria (live DB, rolled back; `META_FAKE_TRANSPORT=true`)
1. A tenant with one Meta builder campaign (2 ad sets, 3 ads), one TikTok builder campaign (1 group, 1 ad) and one wizard campaign: `GET /paid/ad-sets` returns 4 items and `GET /paid/ads` 5, with the right `platform`, campaign names and ad counts. Another tenant sees none of them.
2. Filters: `platform=tiktok` → only the TikTok rows; `status=paused`; `campaign_id`; `q`; paging (`count` stays the total).
3. Seeded Meta `analytics_events` for two ads → those ads show spend/impressions/clicks/CTR; their ad set shows the sums; the TikTok rows show null with `results_level="campaign"`.
4. Pause/resume through `/paid/…` on a published Meta ad set (dev fakes) → status `paused`, then `running`, with the audit rows that the Meta builder writes. An unpublished row → 409. A wizard row → 409. Another tenant's id → 404. A viewer → 403.
5. `ruff check` and `mypy` add no new errors.

## Target files
- New: `app/api/v1/paid.py`, `app/services/paid_service.py`, `app/schemas/paid.py`
- Changed: `app/api/router.py` (register)

## Out of scope
Editing ad sets/ads from the list (the builders do that), bulk actions, column customization, per-ad results for platforms that only report per campaign.
