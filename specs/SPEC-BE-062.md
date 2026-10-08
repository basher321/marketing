# SPEC-BE-062: Multi-platform Ad Manager — foundation

Status: IMPLEMENTED (2026-10-02), plan approved. The DDL is applied to the live DB. Verified on the live DB in a rolled-back transaction with real tokens: 35/35 checks, nothing persisted. Publish, rollback, approval and pause were exercised through a stand-in adapter, because the real platform adapters are SPEC-BE-063…068. Until one is built, its publish, lookup and media routes answer 501 ("isn't available yet"), and `GET /ads/platforms` reports `publishing: "not_built"`.

Implementation notes and deviations (needed for correctness, approved scope):
- The model enum tuples `CHANNEL_TYPES` (models/product.py) and `INTEGRATION_PROVIDERS` (models/integration.py) gained the new values. Without them the ORM can't read a row that uses them.
- `campaign_service.apply_approval_decision`, `pause` and `resume` route a platform campaign to this builder, so the Marketing page's Pause/Resume syncs the platform. `meta_builder_service` (`_campaign`, `_ad_set`, `_ad`) now returns 404 for another platform's campaign, so a TikTok draft can never be published to Meta.
- `integration_service` gained `ad_platform_connection` and `mark_ad_platform_expired`. `integrations/base_adapter.py` gained the adapter contract and `PlatformError`.
- The integration catalog entries, `verify.py` tests, dev fakes and the results job move to each platform's spec (063–068), where their fields are defined. The registry lives in `ads_builder_service.PLATFORMS`.
- A campaign-level pause also updates the published children, as `campaign_service` does for Meta.

Parent of SPEC-BE-063…068 (one per platform) and the backend for SPEC-FE-044/045. The Meta builder (SPEC-BE-054/055) is **not changed**. Meta keeps its own routes and appears in the registry below as one more platform.

## Amendment (2026-10-02): YouTube as its own platform (user request). IMPLEMENTED and verified through the SPEC-FE-045 E2E
YouTube gets its own Ad Manager card and builder pathway, published **through Google Ads**. YouTube has no separate ads API: YouTube ads are Google Ads Video / Demand Gen campaigns.
- Registry key `youtube`, label "YouTube". It uses the `google_ads` connection and the `google_ads.py` adapter (SPEC-BE-064), via the registry's `module` entry.
- Objectives: Video views, Awareness and reach, Website traffic, Leads, Sales.
- Campaign types: Demand Gen (in-stream, in-feed, Shorts) and Video.
- Ad formats: skippable in-stream, in-feed, Shorts, bumper.
- Text limits: headline 40, long headline 90, description 90, business name 25.
- Video: a YouTube video link or ID.
- **No DDL.** Campaigns are stored with the existing `google` channel plus `metadata.platform = youtube`.
- Campaign types are now generic: any platform listing them (Google, YouTube) requires one.
- Google's text limits are keyed by the editor's field names (`headlines`, `descriptions`, `long_headlines`). Each list item is checked.

## Purpose
"+ New campaign" leads to an Ad Manager page where the user picks a platform: Meta (Facebook/Instagram/Messenger), TikTok, Google Ads, LinkedIn, X, Snapchat or Pinterest. Each platform then gets its complete, platform-correct pathway: objective → campaign → ad groups → ads → review → publish, with real publishing for every platform. The user chose all seven platforms and full real publishing (2026-10-02).

## Platform registry
`GET /api/v1/ads/platforms` (any role) → `{platforms: [...]}`, one entry per platform:
`{key, label, channels[], hierarchy: {campaign, group, ad}, connected, account_name|null, connect_hint, objectives: [{key, label, description, available, reason|null}], creative: {formats[], text_limits{}, media{}}, publishing: "live"|"needs_connection"}`

| key | Label | channels (DB) | Group / ad names | Integration provider |
|---|---|---|---|---|
| meta | Meta (Facebook, Instagram, Messenger) | facebook, instagram, messenger | Ad set / Ad | meta_ads (existing) |
| tiktok | TikTok | tiktok | Ad group / Ad | tiktok_ads (existing enum value) |
| google | Google Ads (Search, YouTube, Display) | **google** (new) | Ad group / Ad | google_ads (existing enum value) |
| linkedin | LinkedIn | **linkedin** (new) | Campaign / Creative (group = LinkedIn "campaign", campaign = "campaign group") | **linkedin_ads** (new) |
| x | X (Twitter) | **x** (new) | Line item / Promoted post | **x_ads** (new) |
| snapchat | Snapchat | **snapchat** (new) | Ad squad / Ad | **snapchat_ads** (new) |
| pinterest | Pinterest | **pinterest** (new) | Ad group / Ad (Promoted Pin) | **pinterest_ads** (new) |

The objectives per platform come from each platform's spec (063–068). They're mapped onto the live `campaign_objective` enum (awareness, traffic, engagement, conversions, reach, leads, app_promotion, message_replies), and the platform's own objective name is stored in `campaigns.metadata.platform_objective`.

## Additive DDL (applied once, by hand, like SPEC-BE-055/058)
```sql
ALTER TYPE channel_type ADD VALUE IF NOT EXISTS 'google';
ALTER TYPE channel_type ADD VALUE IF NOT EXISTS 'linkedin';
ALTER TYPE channel_type ADD VALUE IF NOT EXISTS 'x';
ALTER TYPE channel_type ADD VALUE IF NOT EXISTS 'snapchat';
ALTER TYPE channel_type ADD VALUE IF NOT EXISTS 'pinterest';
ALTER TYPE integration_provider ADD VALUE IF NOT EXISTS 'linkedin_ads';
ALTER TYPE integration_provider ADD VALUE IF NOT EXISTS 'x_ads';
ALTER TYPE integration_provider ADD VALUE IF NOT EXISTS 'snapchat_ads';
ALTER TYPE integration_provider ADD VALUE IF NOT EXISTS 'pinterest_ads';
```
Values are only added, never removed or renamed. No table changes: the platform tree uses the existing `campaigns` / `ad_groups` / `ads` columns (`metadata`, `targeting`, `external_id`, `external_ad_id`).

## Storage (non-Meta platforms)
- `campaigns.metadata.platform = <key>`, plus `metadata.platform_campaign = {platform fields}`, `metadata.platform_ids = {campaign: <external id>}`, and `metadata.builder = true` (shared with the Meta builder, so the campaigns list links to the editor).
- `ad_groups.targeting` holds the platform-shaped targeting, `ad_groups.metadata.platform_fields` holds bidding, placements and schedule, and `ad_groups.external_id` holds the platform id.
- `ads.metadata.creative = {format, texts, media refs, destination, cta}`, with the platform id in `ads.external_ad_id`.
- Money stays in integer cents. Each adapter converts to the platform's unit: micros for Google, LinkedIn and Snapchat; the currency amount for TikTok and Pinterest.

## Generic builder routes (non-Meta; Meta keeps `/campaigns/builder`)
All writes are manager+ and audited (`ads_builder.*`).
- `POST /ads/{platform}/campaigns` `{name, objective}` → creates a draft with 1 group and 1 ad, and returns the tree.
- `GET|PATCH /ads/campaigns/{id}` — the tree, and campaign-level fields.
- `POST /ads/campaigns/{id}/groups`, `PATCH|DELETE /ads/groups/{id}`, `POST /ads/groups/{id}/duplicate`
- `POST /ads/groups/{id}/ads`, `PATCH|DELETE /ads/ads/{id}`, `POST /ads/ads/{id}/duplicate`
- `POST /ads/{platform}/media` (multipart) → uploads to the platform, returns `{media_id, kind, thumbnail_url?}`.
- `GET /ads/{platform}/lookup/{kind}?q=` → the platform's own catalog: locations, languages, interests, keywords, audiences, pixels, apps, identities, pages.
- `POST /ads/campaigns/{id}/validate` → `{ok, issues[{level, path, message, severity}]}`. This checks the platform rules from its spec, plus the platform's own validate-only call where one exists.
- `POST /ads/campaigns/{id}/publish` `{mode: active|paused}` → real publish.
- `POST /ads/campaigns/{id}/pause|resume`, and the same per group and per ad, synced to the platform first.
Limits: 1–10 groups per campaign and 1–10 ads per group, the same as the Meta builder (SPEC-BE-055).

## Adapter contract (`app/integrations/<platform>_ads.py`, one per platform)
Every adapter implements these. Each platform spec fills in its specifics.
- `objectives()`, `validate(tree) -> issues`, `lookup(kind, q)`, `upload_media(file)`
- `publish(tree, mode) -> ids`: creates campaign → groups → ads in order. The campaign is created paused, and set active only when everything exists (when `mode=active`). **All-or-nothing:** on any failure, everything created in this attempt is deleted or archived in reverse order, the DB is rolled back, and the route returns 502 with the platform's message (no secrets).
- `set_status(level, external_id, active)`
- `import_results(since)`: daily spend, impressions, clicks and conversions into `analytics_events` (`source=<platform>`, re-importing the last 3 days, as SPEC-BE-056 does for Meta). One 3-hour job covers all connected platforms, with a 5-minute on-demand throttle.
- HTTP goes through `httpx` with a swappable `client_factory`, so tests use `httpx.MockTransport`. `META_FAKE_TRANSPORT`'s dev fakes (`integrations/dev_fakes.py`) get fixtures for each platform and are still refused in production. The env var keeps its name.
- Tokens are Fernet-encrypted, never returned (only masked) and never logged. OAuth refresh happens where the platform's tokens expire (Google, LinkedIn, Snapchat, Pinterest, TikTok). The `httpx` logger stays at WARNING.

## Shared rules
1. **Approval:** publishing runs through the SPEC-BE-047 spend-cap rule (`campaign_service.approval_decision`), exactly as the Meta builder does. A non-owner's over-cap publish becomes a `campaign` approval item, and the owner's approval publishes it.
2. **Connection required:** publishing needs a connected, verified integration for the platform (409 otherwise, with a link hint to Integrations). Drafts can be built without a connection. Lookups then return 409 `needs_connection`, and the UI accepts free-text entries marked "pick from the list after connecting".
3. **Currency:** the ad account's currency must equal the tenant's currency, or validation fails with an error (amounts are never converted).
4. **Tenant isolation:** every query filters on `tenant_id`. Another tenant's ids return 404.
5. **Analytics:** the existing Analytics/Marketing CTR, ROAS and spend read `analytics_events` across all sources, so platform results appear there without frontend changes (still null when nothing was imported).

## Integrations (paste credentials, SPEC-BE-052 style; OAuth where the platform requires it)
Catalog entries and real `verify.py` connection tests for tiktok_ads, google_ads, linkedin_ads, x_ads, snapchat_ads and pinterest_ads. The required fields are listed in each platform spec. The Integrations page picks them up from `GET /integrations/catalog` with no frontend change.

## Acceptance criteria
1. The DDL is applied, and the enum values are listed in `pg_enum`.
2. `GET /ads/platforms` returns 7 platforms, with `connected` reflecting the tenant's integrations.
3. Live DB, rolled-back transaction, with each platform mocked through `MockTransport`: create → edit → validate → publish → pause → resume works for every platform. A failure injected at the ad step deletes the created campaign and group (the calls are asserted) and returns 502 with nothing persisted. A non-owner over cap gets an approval item, and the owner's approval publishes.
4. The Meta builder routes and their behavior are unchanged (regression: create, publish, pause).
5. Viewer → 403 on writes. Another tenant's campaign → 404.
6. ruff/mypy add no new errors. The app boots with no platform credentials.

**Real-platform verification needs your accounts.** Each platform requires approved API access before a real publish can be run:
- Google: a developer token with Basic access.
- TikTok: an approved Marketing API app.
- LinkedIn: the Advertising API product.
- X: Ads API approval.
- Snapchat: a Marketing API app.
- Pinterest: Ads "Standard" access.

Until those exist, each platform is verified with mocks plus a real connection test where possible. This is reported per platform.

## Target files (new files need approval; listed here for that)
- New: `backend/app/api/v1/ads_builder.py`, `backend/app/services/ads_builder_service.py`, `backend/app/schemas/ads_builder.py`, and `backend/app/integrations/{linkedin_ads,x_ads,snapchat_ads,pinterest_ads}.py`
- Changed: `backend/app/integrations/{tiktok_ads,google_ads}.py` (stubs → adapters), `integrations/verify.py`, `integrations/dev_fakes.py`, `api/router.py`, `workers/tasks/ad_tasks.py` (results job), `models/campaign.py` (only if a mapped column is needed)
