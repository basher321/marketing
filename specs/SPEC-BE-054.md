# SPEC-BE-054: Meta — "Connect with Facebook" + publish campaigns to Meta Ads

Status: IMPLEMENTED (2026-10-01). The plan was approved with changes A–D; open decisions 1–5 were resolved as recommended. Verified on live Postgres (rolled-back txn, real register/login tokens, every Meta call answered by `httpx.MockTransport`): 55/55 checks covering acceptance criteria 1–10, decision 4, and tenant isolation. ruff and mypy are at the baseline (1 and 7 pre-existing errors). Criterion 11 (live Meta sandbox run) is still open: it needs the Meta developer app. This is the first Priority-1 spec from the 2026-10-01 capability check. It follows the integration strategy: direct API is the core, and Meta's MCP is a separate, later, read-only spec. A companion frontend spec (SPEC-FE-039) is needed.

## Purpose
Today, "Launch" only records a campaign inside the app; nothing reaches Facebook or Instagram (all adapters are stubs, and the live DB has 0 ads with an `external_ad_id`). This spec makes a launched campaign **actually run on Meta**:
1. A company connects its Meta business with one click (OAuth). It never pastes tokens.
2. Launch creates the real campaign, ad set, ad creative and ad in the company's ad account.
3. Pause and Resume in the app also pause and resume it on Meta.

## Prerequisites (outside the code; the owner must do these)
- A Meta developer app (type Business) with **Facebook Login for Business** and a **configuration** set up:
  - Token type: business integration system user.
  - Assets: ad accounts, Pages, Instagram accounts, pixels.
  - Permissions: `ads_management`, `ads_read`, `business_management`, `pages_show_list`, `pages_read_engagement`, `instagram_basic`.
- **Development mode works only for people with a role on the app.** Real customers need Business Verification plus App Review (Advanced Access) for the permissions above. This takes weeks, so start it in parallel.
- A public HTTPS frontend URL registered as a valid OAuth redirect (`{FRONTEND_BASE_URL}/integrations/meta/callback`). `localhost` is allowed only in development mode.
- The customer needs a Business Manager, an ad account **with a payment method**, and a Facebook Page (ads run as a Page).

## Scope
In scope:
- OAuth connect.
- Choosing the ad account, Page, optional Instagram account and optional pixel.
- Publishing at launch, including after owner approval.
- Pause and resume sync.
- Disconnect.
- Two wizard fields Meta requires: destination URL and call-to-action.

Out of scope (later specs):
- Ad images and video upload (SPEC-BE-055). In v1 Meta uses the destination page's preview image (`og:image`).
- Results import: spend, impressions, clicks, conversions (SPEC-BE-056).
- Meta MCP, read-only in Command Chat (SPEC-BE-057, conditional).
- Editing a live campaign, multiple ad sets or ads per campaign, TikTok and Google.

## Configuration (new `config.py` fields; SPEC-BE-002/003 updated to match)
| Field | Default | Notes |
|---|---|---|
| `META_APP_ID` | `""` | From the Meta app dashboard |
| `META_APP_SECRET` | `SecretStr("")` | Never logged or returned |
| `META_LOGIN_CONFIG_ID` | `""` | The Facebook Login for Business configuration ID |
| `META_GRAPH_VERSION` | `"v25.0"` | Configurable: v26 breaking changes reportedly apply to every version from **2026-10-27**. Check the v26 changelog before go-live |

If the app ID, secret or config ID is empty, the connect endpoints return **503** "Meta connection isn't set up on this server", and the app still boots. The existing paste-a-token Meta Ads form (SPEC-BE-052) stays as a fallback.

## Contract
- `GET /api/v1/integrations/meta/connect` (manager+) → `{ login_url }`. The URL has `client_id`, `config_id`, `redirect_uri`, `response_type=code`, and `state`. The state is a signed JWT (tenant, user, 10-minute expiry, single use).
- `POST /api/v1/integrations/meta/callback` (manager+), body `{ code, state }`:
  - It checks the state (tenant and user must match the caller), exchanges the code for a business integration system user token, then lists what that token can reach.
  - → `{ connection_id, ad_accounts:[{id, name, currency, account_status}], pages:[{id, name, instagram:{id, username}|null}], pixels:[{id, name, ad_account_id}] }`.
  - The token is stored encrypted right away, in a `meta_ads` integration row with status `disconnected` until a selection is made. **It is never returned.**
- `POST /api/v1/integrations/meta/select` (manager+), body `{ ad_account_id, page_id, instagram_id?, pixel_id? }`:
  - It checks that each ID came from the callback list and runs a test call on the ad account.
  - → the integration card (as in SPEC-BE-052), status `connected`, account name = the ad account's name.
  - Stored as `account_external_id` = ad account ID, and `settings` = `{page_id, page_name, instagram_id, pixel_id, currency, business_id}`.
- `DELETE /api/v1/integrations/meta_ads` (existing): wipes the token and settings. Campaigns already on Meta keep running there, and the response says so.
- **Campaign draft (SPEC-BE-044 amendment):** `PATCH /campaigns/{id}` accepts:
  - `destination_url`: https only, at most 2,048 characters, public host (the same SSRF rule as SPEC-BE-052).
  - `call_to_action`: one of SHOP_NOW, LEARN_MORE, SIGN_UP, ORDER_NOW, CONTACT_US, BOOK_NOW, GET_OFFER; default LEARN_MORE.
  - Both are stored in `campaigns.metadata.wizard`. `missing` gains `destination` when the campaign has a Meta channel and no URL.
- **Launch result:** `CampaignDetail` gains `meta: { published: bool, campaign_id, adset_id, ad_id, ads_manager_url } | null` and `published_channels: [..]`.

## Mapping rules (each one documented as a code comment)
- **Which channels publish:** only facebook, instagram and messenger publish to Meta, mapped to `publisher_platforms` `facebook`, `instagram` and `messenger`. Other channels (tiktok, whatsapp, email, sms, web) stay internal, as today, and the result lists them as not published. With no Meta channel, launch works exactly as today.
- **Instagram:** the instagram channel requires an Instagram account selected at connect. Otherwise launch returns **422** "Connect an Instagram account to run on Instagram".
- **Objective** (Meta outcome objectives):
  | Our objective | Meta objective | Ad set optimization |
  |---|---|---|
  | awareness | OUTCOME_AWARENESS | IMPRESSIONS |
  | reach | OUTCOME_AWARENESS | REACH |
  | traffic | OUTCOME_TRAFFIC | LINK_CLICKS |
  | engagement | OUTCOME_ENGAGEMENT | POST_ENGAGEMENT |
  | conversions | OUTCOME_SALES | OFFSITE_CONVERSIONS. **Needs the pixel** (promoted object pixel + PURCHASE). Without one: 422 "Select a Meta Pixel to run a Conversions campaign" |
  | message_replies | not in v1 | 422 "Messages campaigns aren't supported on Meta yet" (see open decision 3) |
- **Special ad categories:** always sent (required): `[]` by default. Housing, employment, credit and politics are out of scope.
- **Budget:** one ad set with `lifetime_budget` = the campaign's `budget_cents`, plus `start_time` and `end_time`. Meta's minor units match our cents. The campaign currency **must equal the ad account currency**; otherwise 422 before any Meta call. Meta's own minimum-budget errors are shown to the user as returned.
- **Targeting** (from the audience):
  - countries → `geo_locations.countries`.
  - age → `age_min`/`age_max`, clamped to Meta's 18–65.
  - gender male → `[1]`, female → `[2]`, all → omitted.
  - Regions, interests and languages need Meta IDs. They are resolved by exact name through Meta's targeting search (`adgeolocation`, `adinterest`, `adlocale`). **Any unresolved term blocks the launch with a 422 listing it**, never silently dropped (open decision 2).
- **Creative:**
  - `object_story_spec.page_id` = the selected Page.
  - `link_data`: link = destination URL, name = variant headline, message = variant description (falling back to the headline), and call to action.
  - `instagram_user_id` when Instagram is selected.
  - No image in v1, so Meta uses the link's preview image.
- **Status:** objects are created **PAUSED** in the order campaign → ad set → creative → ad. Only when all four exist does the campaign switch to ACTIVE. For a future `starts_at`, Meta holds delivery until `start_time` (our status = `scheduled`).
- **Stored IDs:**
  - `campaigns.metadata.meta` = `{campaign_id, adset_id, creative_id, ad_id, ad_account_id, published_at}`.
  - `ad_groups.external_id` = ad set ID.
  - `ads.external_ad_id` = ad ID.
  - `ads.external_url` = the Ads Manager link.

## Functional rules
1. **Launch order:**
   - The approval rule (SPEC-BE-047/032) runs first, unchanged: a non-owner's over-cap launch still goes to owner approval and **nothing is sent to Meta until it is approved**.
   - Publishing happens inside `_go_live`, so an owner's launch and an owner's approval both publish.
2. **All or nothing:**
   - If any Meta call fails, the objects already created are deleted on Meta (best effort, campaign first, which cascades).
   - The DB transaction is rolled back: the campaign stays a draft, no ad group or ad rows remain, and nothing is half-launched.
   - The response is **502**, with Meta's user-facing message (`error_user_msg`, or `message`, up to 300 characters).
   - An audit row `campaign.publish_failed` is written in its own commit.
3. **Approved, then publishing fails:** the approval stays approved and the campaign stays a draft with `metadata.meta.last_error`. The owner can press Launch again; their launch counts as the approval (open decision 4).
4. **Pause and resume:**
   - For a published campaign, the Meta campaign status is set first (PAUSED or ACTIVE), then ours.
   - If Meta fails: 502, and our status is unchanged.
   - An unpublished campaign behaves as today.
5. **Token problems:** a Meta auth error (code 190) sets the integration to `expired` with `last_error`, and launch then returns 409 "Reconnect Meta in Integrations".
6. **HTTP calls:**
   - Every Meta call goes through one client in `integrations/meta_ads.py`: `httpx`, a 20-second timeout, `appsecret_proof` on every call, and secrets never logged.
   - The client is injectable, so tests can use `httpx.MockTransport` as SPEC-BE-052 did.
7. **Audit and isolation:** every action is audited (`integration.meta_connected`, `integration.meta_selected`, `campaign.published`, `campaign.publish_failed`, `campaign.meta_paused/resumed`) and tenant-scoped. Another tenant's state or IDs → 404.

## Edge cases
- **Expired or reused `state`:** 400.
- **Callback with an empty list** (no ad accounts or Pages): 422 that explains what is missing.
- **Ad account not active** (`account_status` ≠ 1, e.g. unpaid or disabled): blocked at select, with Meta's reason.
- **Destination URL that is private or not https:** 422.
- **Launch with a Meta channel but no connection:** 409 "Connect Meta in Integrations to run on Facebook/Instagram". Non-Meta channels can't launch alone through this path; the whole launch is blocked (open decision 1).
- **Clicking Launch twice:** the existing draft-status guard prevents publishing twice.

## Open decisions (each with a recommendation)
1. **A campaign mixing Meta and non-Meta channels when Meta isn't connected.** *Recommend:* block the launch (409), so the user isn't misled into thinking it's running. The alternative is launching internally only.
2. **Unresolved interest or region names.** *Recommend:* block the launch with a 422 listing them, so the user fixes the audience. The alternative is dropping them with a warning, which changes who sees the ad.
3. **Messages objective.** *Recommend:* not in v1. It needs a Messenger or WhatsApp destination setup, so it gets its own spec with WhatsApp.
4. **Publishing fails after an owner's approval.** *Recommend:* keep the approval, and let the owner's next Launch publish. The alternative is reopening the approval.
5. **More than one ad account per company.** *Recommend:* one in v1. The unique index `(tenant_id, provider, account_external_id)` already allows more later.

## Acceptance criteria (verified on live Postgres in a rolled-back transaction; every Meta call answered by `httpx.MockTransport`, no real Meta call)
1. **Connect:** returns a login URL with the config ID and a signed state. Callback with a valid code and state → token stored encrypted (never in the response or logs), plus the lists. A bad, expired or other-tenant state → 400.
2. **Select:** saves the chosen IDs and the card shows `connected`. An ID not from the callback list → 422. An inactive ad account → 422.
3. **Owner launch (traffic, facebook + instagram):**
   - Exactly 4 create calls in order, with the documented bodies (objective, lifetime budget, start/end, targeting, page_id, link_data, instagram_user_id, all PAUSED), then 1 activate call.
   - IDs stored in metadata, `ad_groups.external_id` and `ads.external_ad_id`.
   - Status `running` or `scheduled`, plus audit `campaign.published`.
4. **Failure at the creative step:** 502 with Meta's message, cleanup DELETE called for the created campaign, the campaign still a draft, no ad group or ad rows, and audit `campaign.publish_failed`.
5. **Approval path:** a manager's over-cap launch → approval item and **0 Meta calls**. The owner's approval → publishes (as in criterion 3).
6. **Guards:**
   - Currency mismatch, a conversions objective without a pixel, instagram without an IG account, an unresolved interest, or a missing destination URL → 422 before any Meta call.
   - No connection → 409.
   - Code 190 → integration `expired` + 409.
7. **Pause and resume** send the matching Meta status call. A Meta failure leaves our status unchanged.
8. **Non-Meta-only campaign** (e.g. email): launch unchanged, 0 Meta calls.
9. **Missing app config** → 503 on connect, and the app still boots.
10. **Lint and types:** ruff and mypy add no new errors. No secret appears in any response or log line (checked by grepping the captured logs for the token).
11. **Optional live check** once the Meta app exists: one real run against a Meta **sandbox ad account** (it doesn't spend money), recorded as pass/fail.

## Target files
- `backend/app/config.py`, plus the matching update to `specs/SPEC-BE-002.md` / `SPEC-BE-003.md`.
- `backend/app/integrations/meta_ads.py`: the stub becomes the Meta client.
- `backend/app/services/integration_service.py`: connect, callback and select.
- `backend/app/services/campaign_service.py`: publish inside `_go_live`, the pause/resume sync, and the destination fields.
- `backend/app/api/v1/integrations.py`, `backend/app/schemas/integration.py`.
- `backend/app/schemas/campaign.py`: `destination_url`, `call_to_action`, and `meta` / `published_channels` on the detail.
- No new files.

## Follow-on specs
- **SPEC-FE-039:** the "Connect with Facebook" button, the callback page, the account/Page/pixel picker, and the wizard's destination URL and call-to-action fields. The review step shows "Will run on: Facebook, Instagram", and the launch result links to Ads Manager.
- **SPEC-BE-055:** ad image and video upload (storage plus Meta `adimages`/`advideos`).
- **SPEC-BE-056:** results import, filling spend, impressions, clicks and conversions into `analytics_events`, which brings CTR, ROAS and the Analytics page to life.
- **SPEC-BE-057** (conditional): Meta's hosted MCP, read-only in Command Chat, only if Meta allows third-party app tokens.

## Implementation notes (2026-10-01)
Approved plan changes:
- **A:** `integrations/verify.py` now uses `META_GRAPH_VERSION` (it was hard-coded to v19.0). The pasted-token Meta Ads form gained optional `page_id`, `instagram_id` and `pixel_id` fields, so that path can publish too.
- **B:** a missing destination link → 422 at launch. `missing` does **not** gain `destination` yet; that comes with SPEC-FE-039.
- **C:** the token from the callback is held as `settings.meta_pending`, so an existing connection is untouched until select.
- **D:** messenger alone → 422 "Messenger needs Facebook too".

Other deviations and decisions:
- **Activation:** the campaign is created PAUSED, and the ad set and ad are created ACTIVE *under* it, so nothing delivers until the single final campaign→ACTIVE call. This is the same safety as "all PAUSED" with one activate call.
- **What "before any Meta call" means:**
  - Static checks run in `launch` before the approval branch, with no network at all: connection, Page, objective, pixel, Instagram, messenger, destination.
  - The currency and targeting checks need read-only Meta GETs (ad account, targeting search). They still fail with 0 create calls.
- **`integrations.account_external_id`** is read and written through a Core table, because the `Integration` model doesn't map it. The model isn't a target file.
- **Placeholder row timestamp:** the placeholder row made by `GET /meta/connect` sets `connected_at` (NOT NULL live).
- **Disconnect:** returns 204 with no body, so "campaigns keep running on Meta" must be said by the UI (SPEC-FE-039).
- **Log leak fixed:** found during verification. httpx logs every request URL at INFO, and Graph GETs carry `access_token` (and the app secret during the code exchange) in the query string. `meta_ads.py` sets the `httpx` logger to WARNING process-wide, which also fixes the same pre-existing leak in `verify.py`'s connection tests. Re-verified: no token or secret in any log line.
- **Unverified assumption:**
  - Assets are listed with `/me/adaccounts` and `/me/accounts`. Meta's docs don't name the edges for this token type. Confirm in the sandbox run (criterion 11).
  - Offset-1 currencies (whole units) per Meta's currency table, 2026-10-01: CLP, COP, CRC, HUF, ISK, IDR, JPY, KRW, PYG, TWD, VND.
- **Behaviour change for existing data:** a campaign with facebook, instagram or messenger can no longer launch without a real Meta connection (decision 1). dev-shop's seeded "connected" Meta rows hold `demo://` placeholders, so they count as not connected. Campaigns without a Meta channel launch exactly as before.
