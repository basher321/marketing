# SPEC-BE-044: Campaign Wizard — Campaign Drafts (create / read / update)

Status: IMPLEMENTED (2026-09-30), plan approved by the user; verified on live Postgres (rolled-back txn).

## Purpose
Back the Campaign Wizard (SPEC-FE-030) so a campaign can be built step by step and saved as a **draft**, following the standard ad-manager flow (Meta Ads Manager, TikTok Ads, Google Ads): Objective → Audience → Creative → Budget & Schedule → Channels → Review & Launch. Today the backend has only read endpoints for campaigns (SPEC-BE-009/038), so "Continue to Budget →" has nothing to save to. Launching is SPEC-BE-047.

## Scope
In scope:
- Realign the `Campaign` model with the live `campaigns` table.
- Create a draft, read one campaign, update a draft, and list drafts.

Not in scope: launch/pause/resume (SPEC-BE-047), audiences (SPEC-BE-045), creative (SPEC-BE-046), and deleting drafts.

## Live table (authoritative)
`campaigns`: name, description, objective `campaign_objective` (awareness, traffic, engagement, conversions, message_replies, reach), channels `channel_type[]`, budget_cents, daily_cap_cents (both NOT NULL), spent_cents, currency, starts_at, ends_at, status `campaign_status`, auto_pause_rules, owner_approved_at/by, launched_at, paused_at, completed_at, metadata jsonb, created_by.

## Contract
`POST /api/v1/campaigns` (manager+) → 201 `CampaignDetail`
Body: `{ name (1-255), objective, description? }`
The draft is created with `status = draft`, `budget_cents = 0`, `daily_cap_cents = 0`, `channels = []`, `currency = tenant currency`, and `created_by = actor`.

`GET /api/v1/campaigns/drafts` → 200 `[CampaignDetail]`: this tenant's drafts, most recently updated first.

`GET /api/v1/campaigns/{id}` → 200 `CampaignDetail` (any status). Another tenant's campaign returns 404.

`PATCH /api/v1/campaigns/{id}` (manager+) → 200 `CampaignDetail`. **Drafts only**; any other status returns 409. Every field is optional:
`{ name, objective, description, audience_id, creative_asset_id, total_budget (major units, > 0), starts_at, ends_at, channels[] }`
```
CampaignDetail = { id, name, objective, description, status, channels, currency,
  total_budget: float, daily_budget: float, duration_days: int | null,
  starts_at, ends_at, audience_id, creative_asset_id,
  approval: { required: bool, reason: str } | null,   # preview of SPEC-BE-047's rule
  pending_approval_id: str | null,
  missing: [str],        # steps still incomplete, e.g. ["audience", "budget"]
  created_at, updated_at, launched_at }
```

## Functional rules
1. **Wizard state:** `audience_id` and `creative_asset_id` are stored in `campaigns.metadata` as `wizard.audience_id` and `wizard.creative_asset_id`. The live table has no columns for them, and the real `ad_groups`/`ads` rows are only created at launch (SPEC-BE-047). Both ids must belong to the tenant, or the request gets a 422. A creative must be a `content_assets` row whose `selected_variant_index` is set. Setting a creative also sets that asset's `campaign_id`.
2. **Budget:** the user enters a total budget and a schedule (the Meta "lifetime budget" pattern).
   - `duration_days` = the number of calendar days from `starts_at` to `ends_at`, counting both, in the tenant timezone.
   - `daily_cap_cents` = `round(budget_cents / duration_days)`, using Decimal with ROUND_HALF_UP.
   - Money is in the tenant currency. Validation: `starts_at` must not be in the past (1-minute tolerance), `ends_at` must be after `starts_at`, and the duration must be at most 365 days. Any other input gets a 422.
3. **Channels:** a subset of the live `channel_type` values, with at least 1 required before launch.
4. **`missing`** lists, in order: `audience`, `creative`, `budget` (budget or schedule not set), and `channels`. It is empty once a draft can be launched.
5. **`approval`:** a preview of the SPEC-BE-047 launch rule, so the Review step can say "Needs owner approval: daily spend ৳2,857 > cap ৳50" before the user clicks Launch. It is null until the budget is set.
6. Timestamps come back in UTC. Every query is filtered by tenant. Create and update each write an audit row (`campaign.create`, `campaign.update`).
7. The existing `GET /campaigns`, `/metrics` and `/ad-spend-24h` are unchanged. `/drafts` is declared before `/{id}`.

## Acceptance criteria
1. Create persists a draft that matches the input and the defaults above. A viewer gets 403.
2. PATCH updates only the fields sent. Budget and schedule give the correct `daily_cap_cents` and `duration_days`. Invalid dates, budget, or a foreign audience or creative give 422, and nothing is written.
3. PATCH on a non-draft returns 409. Another tenant's id returns 404.
4. `missing` and `approval` are correct for partial and complete drafts.
5. Existing campaign endpoints return the same results as before.

## Target files
- backend/app/models/campaign.py (Campaign realigned: status enum, metadata, created_by, launch/approval timestamps)
- backend/app/schemas/campaign.py
- backend/app/services/campaign_service.py
- backend/app/api/v1/campaigns.py
