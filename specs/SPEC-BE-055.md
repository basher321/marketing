# SPEC-BE-055: Meta Ads Manager-style campaign builder (Campaign → Ad Set → Ad)

Status: IMPLEMENTED, VERIFIED ON THE LIVE DB (2026-10-01). The plan was approved as recommended (all 9 decisions). Done: ruff/mypy at baseline, the app imports, `next build` passes, and the logic was checked in-process with `httpx.MockTransport` (no DB). The additive DDL was applied 2026-10-01. Live-DB verified 2026-10-01 (rolled-back run; all acceptance checks pass). Deviations kept: a PNG renamed .mp4 is accepted as an image (magic bytes decide); "Publish paused" sends ad sets/ads ACTIVE under a PAUSED campaign. Source: the "AI Orchestrator — Developer Change Spec" §2 and the review flow diagram ("NEW: META ADS CAMPAIGN BUILDER"). Builds on SPEC-BE-054 (connect + publish), which stays the transport layer. This spec absorbs the "ad images" item that SPEC-BE-054 reserved as SPEC-BE-055. Results import is SPEC-BE-056. The frontend is SPEC-FE-039.

Implementation notes: the builder routes live in the new `api/v1/meta.py` (no prefix), not in campaigns.py/ads.py. Meta `validate_only` runs on the campaign object only; ad sets and ads are validated at publish (all-or-nothing rollback). Logic is in the new `services/meta_builder_service.py` and `schemas/meta.py`. `CampaignDetail`/`CampaignListItem` gained `builder`; the list also gained `spent` and `effective_status`.

## Purpose
Today's wizard (SPEC-BE-044/047/054) is a simplified flow: one objective out of five, one audience, one creative variant, one lifetime budget, and one ad set with one ad, with no image. This spec replaces it with the same A-to-Z structure as Meta Ads Manager:

1. **Objective**: Awareness, Traffic, Engagement, Leads, App Promotion, Sales (Meta's six outcome objectives).
2. **Campaign**: name, objective, special ad categories, buying type, campaign budget (Advantage+ campaign budget) or ad-set budgets, bid strategy, spend cap.
3. **Ad sets** (1..N per campaign): budget (daily or lifetime), schedule, conversion location, performance goal, audience (locations, age, gender, languages, detailed targeting, custom/lookalike audiences, Advantage+ audience), placements (Advantage+ or manual), pixel/dataset + conversion event.
4. **Ads** (1..N per ad set): identity (Facebook Page, Instagram account), format (single image, single video, carousel), media, primary text, headline, description, CTA, destination (website URL, app store, instant form), URL parameters (UTM tracking).
5. **Review**: local validation, Meta validation (`execution_options=validate_only` where Meta allows it), a real Meta preview (`generatepreviews`).
6. **Actions**: Save draft, Publish now, Schedule (future start), Pause / Resume (campaign, ad set or ad level).

**Meta is the execution layer.** Nothing is "created" in the frontend. Every Meta object is created by the backend through `integrations/meta_ads.py`, and its ID and status are saved in our DB.

## Honest limits (to be shown in the UI, not hidden)
- **"Draft" is ours.** Meta's Marketing API has no draft object (Ads Manager drafts are UI-only). Save draft = stored in our DB only. The builder also offers "Publish paused": all objects are created on Meta with status PAUSED, so they appear in Ads Manager but don't spend.
- **Buying type:** the API supports AUCTION for all advertisers. RESERVATION (Reach & Frequency) needs Meta allow-listing, so it is shown disabled with that reason.
- **App Promotion** needs an app registered to the ad account (`act_{id}/advertisable_applications`). With none, the objective is shown disabled with the reason.
- **Leads with an Instant Form** needs Page lead forms (`{page_id}/leadgen_forms`) and the `pages_manage_ads` + `leads_retrieval` permissions on the Meta app. Without them, Leads works only with a website destination + pixel Lead event.
- **Special ad categories** (housing, employment, financial products and services, issues/elections/politics) restrict targeting per Meta's rules. The builder enforces those restrictions (no age/gender/zip-code targeting, no lookalikes). Issues/elections/politics also needs the Page to be authorized by Meta; we only pass the category and show Meta's error if it isn't.

## Data model (live DB changes — need approval, see open decision 1)
Additive, run once in a transaction, documented here as the source of truth (there is no Alembic):

```sql
ALTER TYPE campaign_objective ADD VALUE IF NOT EXISTS 'leads';
ALTER TYPE campaign_objective ADD VALUE IF NOT EXISTS 'app_promotion';
ALTER TABLE ad_groups ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb;
```

Objective mapping (the existing enum values stay; "Sales" in the UI = our `conversions`):

| UI | `campaigns.objective` | Meta objective |
|---|---|---|
| Awareness | awareness (or reach) | OUTCOME_AWARENESS |
| Traffic | traffic | OUTCOME_TRAFFIC |
| Engagement | engagement | OUTCOME_ENGAGEMENT |
| Leads | leads (new) | OUTCOME_LEADS |
| App Promotion | app_promotion (new) | OUTCOME_APP_PROMOTION |
| Sales | conversions | OUTCOME_SALES |

`message_replies` stays rejected for Meta (SPEC-BE-054 decision 3).

Where each level lives:
- **Campaign:** `campaigns` columns (name, objective, channels, budget_cents, currency, starts_at, ends_at, status) + `campaigns.metadata.builder` = `{special_ad_categories, special_ad_category_country, buying_type, budget_mode: "campaign"|"ad_set", budget_type: "daily"|"lifetime", bid_strategy, bid_amount_cents, spend_cap_cents}`. `campaigns.metadata.meta` keeps the Meta IDs (SPEC-BE-054).
- **Ad set:** one `ad_groups` row each. `targeting` jsonb = the audience (resolved Meta IDs + display names), `budget_cents`, `bid_strategy`, `status`, `external_id` = Meta ad set ID. New `ad_groups.metadata` = `{budget_type, starts_at, ends_at, conversion_location, optimization_goal, billing_event, promoted_object, placements: {mode: "advantage"|"manual", platforms, positions, devices}, advantage_audience, attribution_spec, meta_status, effective_status, last_error}`.
- **Ad:** one `ads` row each. `external_ad_id` = Meta ad ID, `external_url` = Ads Manager link, `ads.metadata` = `{identity: {page_id, instagram_user_id}, format, media: [{type, image_hash|video_id, thumbnail_url, name}], primary_text, headline, description, call_to_action, destination: {type: "website"|"app"|"instant_form", url, app_store_url, lead_form_id}, url_tags, creative_id, effective_status, last_error}`.
- An ad set or ad in a draft has `status = 'draft'` and no external ID.

## Contract (all under `/api/v1`, manager+ for writes, all tenant-scoped; another tenant's ID → 404)
Meta asset lookups (for the builder's pickers; all need a connected Meta integration, else 409):
- `GET /meta/objectives` → the six objectives, each `{key, label, meta_objective, available, reason}` (App Promotion / Leads availability per the limits above), plus allowed `optimization_goals` and `conversion_locations` per objective (the table below).
- `GET /meta/targeting/search?type=adgeolocation|adinterest|adlocale|adTargetingCategory&q=` → `[{id, name, type, audience_size?}]` (proxy to Meta's targeting search).
- `GET /meta/custom-audiences` → the ad account's custom and lookalike audiences `[{id, name, subtype, approximate_count}]`.
- `GET /meta/apps` (advertisable applications), `GET /meta/lead-forms` (forms on the selected Page), `GET /meta/pixels` (pixels/datasets on the ad account).
- `POST /meta/reach-estimate` body `{targeting, optimization_goal}` → Meta's `delivery_estimate` (estimated daily reach range). Best-effort: a Meta error returns `{available: false, reason}`, never a fake number.
- `POST /meta/media` (multipart, image ≤ 30 MB JPG/PNG, video ≤ 1 GB MP4/MOV, checked by magic bytes) → uploads to `act_{id}/adimages` or `act_{id}/advideos` and returns `{type, image_hash|video_id, thumbnail_url, status}`. Video `status` is polled through `GET /meta/media/videos/{video_id}` until `ready`.

Builder (replaces the SPEC-BE-044 wizard routes; old ones keep working until SPEC-FE-039 ships, see decision 4):
- `POST /campaigns/builder` → create a draft campaign with its campaign-level fields. Returns the full builder tree.
- `GET /campaigns/{id}/builder` → `{campaign, ad_sets: [{..., ads: [...]}], missing: [{level, id, field, message}], meta: {...}|null}`.
- `PATCH /campaigns/{id}/builder` (campaign fields), `POST /campaigns/{id}/ad-sets`, `PATCH /ad-sets/{id}`, `POST /ad-sets/{id}/duplicate`, `DELETE /ad-sets/{id}` (draft only), `POST /ad-sets/{id}/ads`, `PATCH /ads/{id}`, `POST /ads/{id}/duplicate`, `DELETE /ads/{id}` (draft only).
- `POST /campaigns/{id}/validate` → runs local rules, then Meta `validate_only` on the campaign. Returns `{ok, errors: [{level, id, field, message, source: "local"|"meta"}]}`.
- `POST /ads/{id}/preview?format=DESKTOP_FEED_STANDARD|MOBILE_FEED_STANDARD|INSTAGRAM_STANDARD|INSTAGRAM_STORY|FACEBOOK_STORY_MOBILE|INSTAGRAM_REELS` → Meta `act_{id}/generatepreviews` with the ad's creative spec → `{format, iframe_html}` (Meta's own preview; never rendered by us).
- `POST /campaigns/{id}/publish` body `{mode: "active"|"paused"}`. Runs the existing SPEC-BE-047 approval rule first. With a future `starts_at` on any ad set, the result status is `scheduled` ("Schedule" in the UI = publish with a future start).
- `POST /campaigns/{id}/pause|resume` (existing), plus new `POST /ad-sets/{id}/pause|resume`, `POST /ads/{id}/pause|resume`. Meta first, then our row (SPEC-BE-054 rule 4).
- `PATCH` on a **published** object (open decision 3): only budget, end time, bid amount, and ad text/CTA changes are allowed. Each is sent to Meta first; a Meta failure → 502 and our row is unchanged.

## Rules (each to be documented as a code comment)
1. **Objective → allowed settings** (Meta outcome-objective rules, checked 2026-10-01; v25 is configured):

   | Objective | Conversion locations | Performance goals (optimization_goal) |
   |---|---|---|
   | Awareness | — | REACH, IMPRESSIONS, AD_RECALL_LIFT, THRUPLAY |
   | Traffic | website, app, messenger, whatsapp* | LINK_CLICKS, LANDING_PAGE_VIEWS, REACH, IMPRESSIONS |
   | Engagement | on_ad (post), video, page | POST_ENGAGEMENT, THRUPLAY, PAGE_LIKES |
   | Leads | website, instant_form | OFFSITE_CONVERSIONS (pixel Lead), LEAD_GENERATION, QUALITY_LEAD |
   | App Promotion | app | APP_INSTALLS, LINK_CLICKS, OFFSITE_CONVERSIONS (app events) |
   | Sales | website, app | OFFSITE_CONVERSIONS, VALUE, LINK_CLICKS, LANDING_PAGE_VIEWS |

   *messenger/whatsapp destinations are out of scope (SPEC-BE-054 decision 3); they are listed as unavailable with that reason. The table is the one place to update when Meta changes; any other pairing → 422 before any Meta call.
2. **Budget:** campaign budget (Advantage+ campaign budget: `daily_budget` or `lifetime_budget` on the campaign, with `bid_strategy`) **or** ad-set budgets, never both. Lifetime needs an end time. Amounts use `to_meta_amount` (offset-1 currencies). Daily budget × days is what the SPEC-BE-047/032 spend-cap approval rule checks (lifetime → `budget ÷ days`, unchanged).
3. **Bid strategy:** LOWEST_COST_WITHOUT_CAP (default), LOWEST_COST_WITH_BID_CAP, COST_CAP (needs `bid_amount`), LOWEST_COST_WITH_MIN_ROAS (Sales + VALUE only, needs `roas_average_floor`).
4. **Audience:** locations (countries, regions, cities with radius, zip codes) / age 18–65 / gender / languages / detailed targeting (interests, behaviors, demographics) / custom + lookalike include/exclude / Advantage+ audience on or off. Everything is stored with Meta IDs, picked from Meta's own search, so SPEC-BE-054's name-resolution step is only needed for audiences saved before this spec. Saved audiences (`/audiences`, SPEC-BE-045) can be loaded into an ad set as a starting point.
5. **Placements:** Advantage+ placements (omit `publisher_platforms`) or manual: `publisher_platforms` ⊆ {facebook, instagram, messenger, audience_network}, plus `facebook_positions`, `instagram_positions`, `messenger_positions`, `audience_network_positions`, `device_platforms`. The campaign's `channels` column is derived from the selected platforms (facebook / instagram / messenger) so existing lists and analytics keep working.
6. **Creative:**
   - Single image → `object_story_spec.link_data` with `image_hash`; single video → `video_data` with `video_id` + thumbnail; carousel (2–10 cards) → `link_data.child_attachments`.
   - Fields: `message` (primary text), `name` (headline), `description`, `call_to_action {type, value: {link | app_link | lead_gen_form_id}}`, `url_tags` (UTM).
   - Identity: `page_id` required; `instagram_user_id` when Instagram placement is used (422 without one, as SPEC-BE-054).
   - AI-generated text from SPEC-BE-046 creatives can be imported into an ad (`content_asset_id`).
7. **Tracking:** pixel/dataset + `custom_event_type` in `promoted_object` (Sales: PURCHASE default; Leads website: LEAD). `url_tags` default `utm_source=facebook&utm_medium=paid&utm_campaign={{campaign.name}}` (Meta dynamic params), editable.
8. **Publish order** (SPEC-BE-054 rule 2 extended): campaign → each ad set → each ad's creative → ad, all PAUSED; then the requested status. Any failure → delete everything created (campaign delete cascades on Meta), DB rollback, 502 with Meta's message and the failing object path (`ad_sets[1].ads[0]`), audit `campaign.publish_failed`.
9. **Errors are classified for the UI:** `validation` (Meta subcode on a field → mapped back to `{level, id, field}`), `permission` (codes 10, 200–299, 294 → "Your Meta connection lacks permission X"), `auth` (190 → integration `expired`, 409), `missing_asset` (no Page/pixel/app/form/media → 422 naming it), `unsupported` (field not allowed for objective/category → 422), `rate_limit` (codes 4, 17, 32, 613 → 503 "Meta is rate-limiting this account; try again in a few minutes"), `meta_unavailable` (5xx/timeout → 502).
10. **Status read-back:** after publish and on every builder GET of a published campaign (cached 60 s), Meta `effective_status` for campaign/ad sets/ads is read and stored (`metadata.effective_status`), so "In review", "Disapproved", "With issues" are real Meta states. Disapproval reasons (`ad_review_feedback`) are shown on the ad.
11. **Audit:** `campaign.builder_created/updated`, `ad_set.created/updated/deleted`, `ad.created/updated/deleted`, `meta.media_uploaded`, `campaign.validated`, `campaign.published`, `campaign.publish_failed`, `campaign|ad_set|ad.meta_paused/resumed`, `campaign.meta_updated`.

## Edge cases
- Objective changed after ad sets exist → incompatible goals/locations are flagged in `missing`, not silently changed.
- Switching budget mode campaign ↔ ad set moves the amount, never duplicates it.
- Media uploaded, then the Meta connection is replaced by another ad account → hashes don't exist there → `missing_asset` on validate.
- Video still processing at publish → 422 "Video is still processing on Meta".
- Ad set or ad delete on a published object → not allowed (409); pause it instead.
- Concurrent publish clicks → the existing draft-status lock (`with_for_update`) keeps one.

## Open decisions (recommendation first)
1. **Schema change.** *Recommend:* run the 3 additive DDL statements above (no data rewrite; reversible except enum values, which are harmless). *Alternative:* no DDL — keep Leads/App Promotion in `campaigns.metadata.builder.meta_objective` with the enum set to `traffic`/`conversions`, and ad-set extras inside `ad_groups.targeting`. That works but makes reports and filters lie about the objective.
2. **Multiple ad sets / ads.** *Recommend:* 1..N each (up to 10 ad sets × 10 ads in v1), like Ads Manager. *Alternative:* keep one of each (much simpler UI).
3. **Editing live campaigns.** *Recommend:* allow budget, end time, bid amount, status and ad text/CTA only (each pushed to Meta first). Targeting/placement edits on live ad sets → "duplicate the ad set". *Alternative:* full edit (Meta re-enters review on most edits).
4. **Old wizard routes** (SPEC-BE-044 PATCH/launch). *Recommend:* keep them working (Command Chat's current `launch_ad` uses them) and mark deprecated; SPEC-BE-059 moves chat onto the builder.
5. **Video in v1.** *Recommend:* yes (single video + upload status polling). *Alternative:* images + carousel only.

## Acceptance criteria (live Postgres, rolled-back transaction, real register/login tokens, every Meta call answered by `httpx.MockTransport`)
1. **A — objective → Campaign → Ad Set → Ad:** create with each of the six objectives; allowed goals/locations returned per the table; an invalid pairing → 422 with 0 Meta calls.
2. **B — configurable fields:** daily vs lifetime, campaign vs ad-set budget, schedule, audience (location/age/gender/language/interest/custom audience/Advantage+), manual placements, image/video/carousel creative, CTA, destination, pixel + event, UTM tags are stored and appear in the exact Meta request bodies on publish.
3. **C — draft/publish/schedule/pause:** draft = 0 Meta calls; Publish paused → all objects PAUSED; Publish active → activate call; future start → status `scheduled` with `start_time` sent; pause/resume at each level sends the matching status call and a Meta failure leaves our status unchanged.
4. **Validation:** `validate` returns local + Meta (`validate_only`) errors mapped to `{level, id, field}`.
5. **Preview:** `generatepreviews` called with the creative spec; iframe HTML returned unchanged.
6. **Errors:** each class in rule 9 produces the documented status and message (fixture per Meta error code).
7. **Rollback:** failure on the 2nd ad of the 2nd ad set → every created object deleted on Meta, no rows changed, audit `campaign.publish_failed`.
8. **IDs + status saved:** `campaigns.metadata.meta`, `ad_groups.external_id`, `ads.external_ad_id`, effective statuses stored.
9. **Approval:** a manager's over-cap publish → approval item and 0 Meta calls; the owner's approval publishes the whole tree.
10. **Media:** magic-byte check; a PNG renamed `.mp4` → 422; upload result stored on the ad.
11. Tenant isolation on every route; ruff/mypy add no new errors; no token in any response or log.
12. Optional live check against a Meta sandbox ad account once the Meta app exists.

## Target files
Existing: `integrations/meta_ads.py` (client methods: validate_only, previews, media, search, custom audiences, apps, lead forms, delivery estimate, status read-back; objective/goal table), `services/campaign_service.py` (publish tree, rollback, pause/resume per level), `services/ad_service.py` (ad set / ad CRUD; today a near-empty module for `/ads/ctr-7d`), `models/campaign.py` (`AdGroup.metadata`, new objective values), `schemas/campaign.py`, `api/v1/campaigns.py`, `api/v1/ads.py`, `api/router.py`.
**New files (need approval):** `api/v1/meta.py` + `services/meta_builder_service.py` (asset lookups, media, preview, validate) and `schemas/meta.py`. Alternative: put the lookups into `api/v1/integrations.py` / `integration_service.py`, which are already large.
