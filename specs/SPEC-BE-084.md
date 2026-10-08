# SPEC-BE-084: Zernio as the paid-ads engine for every company

Status: IMPLEMENTED and verified against dev fakes (2026-10-08). Decisions: D1 A, D2 A,
D3 B, D4 A.
- **Checks:** 25 of 25 pass on the live Postgres, inside one rolled-back transaction
  (`dev_fakes.install()`, real register/login tokens for an owner, a manager, a viewer and
  a second company). They cover acceptance 1–9 plus FR6–FR11 and FR14. Nothing persisted:
  both temporary companies were gone after the rollback.
- **Lint and types (acceptance 10):** `ruff check app` is at its baseline of 1 error, and
  `mypy app` at its baseline of 7 errors in 5 files.
- **Not yet run against the real zernio.com:** that needs `ZERNIO_API_KEY` in
  `backend/.env` and the user's own platform sign-ins.

See "Implementation notes" at the end.
Requested by the user: "I got an API (https://zernio.com/) for paid marketing which will be
for all users … all features under New campaign, like select social media and its related
sub-options. Do not change anything else." Frontend: SPEC-FE-055.

## Context

Zernio (https://zernio.com, API v1.244, OpenAPI at https://zernio.com/openapi.json) is a
third-party REST API.

**What it offers:**
- **Unified ads:** one ads API across Meta (Facebook and Instagram), Google Ads, TikTok,
  LinkedIn, Pinterest, X and OpenAI (ChatGPT) Ads.
- **Organic:** posting on 17 networks (not used by this spec).

**How it works:**
- **Auth:** `Authorization: Bearer <api_key>`; base URL `https://zernio.com/api/v1`.
- **Platform tokens:** Zernio holds them (managed OAuth); we never see them.
- **Profiles:** a Zernio profile groups connected accounts, and one API key can own many
  profiles.

**Rate limits:** 60 req/min on the free tier (first 2 connected accounts), 600 paid,
1,200 enterprise.

**Design (proposed, see Decisions):**
- **One platform-wide key:** a single Zernio key for the whole platform (the user's "for
  all users"), in `backend/.env`.
- **A profile per company:** each company gets its own Zernio profile, created on first
  use, with the id stored on the tenant. Every account, ad account and campaign a company
  touches must belong to its own profile.
- **Self-contained:** campaigns live in Zernio and are read live (`GET /ads/tree`), like
  SocialAPI (SPEC-BE-083). Our `campaigns` / `ad_groups` / `ads` tables, the existing Meta
  builder (SPEC-BE-055), the multi-platform builder (SPEC-BE-062…068), the AI Autopilot,
  analytics imports and the enums are untouched. **No DDL.**

## Decisions (answered 2026-10-08)

- **D1 = A:** one server key, with a Zernio profile per company.
- **D2 = A:** live from Zernio only; no DDL.
- **D3 = B:** any manager+ may create ACTIVE and resume. There is no owner-only rule and
  no spend-cap approval for Zernio campaigns.
- **D4 = A:** phase 1 as listed.

The options as they were offered:

- **D1 Key scope.**
  - **(A, recommended)** One `ZERNIO_API_KEY` in `backend/.env`, used for every company,
    with company isolation done by per-company Zernio profiles + our own ownership checks.
  - (B) Each company pastes its own Zernio key (like SocialAPI).
- **D2 Storage.**
  - **(A, recommended)** Live from Zernio only. Storage is
    `tenants.settings.zernio = {profile_id, created_at}`; no DDL.
  - (B) Also mirror campaigns into our `campaigns` table, so they appear in the existing
    Campaigns tab, Analytics and the spend-cap check. This needs enum DDL
    (`channel_type`), and touches existing services.
- **D3 Spend control.**
  - **(A, recommended)** Managers and admins can build and create campaigns, but only
    **PAUSED**. Going live (create as ACTIVE, or resume) is **owner-only**.
  - (B) Any manager+ can publish live.
  - (C) Reuse the SPEC-BE-032 daily-cap approval queue. This touches `approval_queue`
    handling, which is outside this spec.
- **D4 Scope of this spec (phase 1).** The full Zernio ads API has ~200 endpoints. Phase 1
  covers what a "New campaign" flow needs, listed in the Functional requirements.
  - **Later specs, if wanted:** Google Performance Max and Demand Gen, catalogs and
    product sets, lead forms, the conversions API, custom audiences, keyword lists,
    sitelinks/callouts, reach & frequency, labels, bid-strategy portfolios, and ad
    comments.

## Functional requirements

1. **Config** (SPEC-BE-002/003 updated in the same change):
   - `ZERNIO_API_KEY` (secret, default empty; every Zernio route answers 503 "Zernio isn't
     set up on this server" while empty);
   - `ZERNIO_BASE_URL` (default `https://zernio.com/api/v1`).
   - The key is never logged or returned.
2. **Company profile.**
   - **First use:** the first Zernio call of a company creates its profile (`POST
     /profiles {name: "<company name> · <tenant id first 8>", timezone: tenants.timezone}`,
     with an `Idempotency-Key` = tenant id). The id is saved in
     `tenants.settings.zernio.profile_id`.
   - **Name clash:** a 409 name clash reuses `details.existingProfileId`.
   - **Status:** `GET /zernio/status` → `{configured, profile_id_set, account_count}`
     (viewer+).
3. **Ownership guard (tenant isolation).** Zernio's key sees every company's profile, so
   every route that takes a Zernio id first checks it belongs to the caller's profile:
   - account ids: `GET /accounts?profileId=`;
   - ad-account ids: listed under one of those accounts;
   - campaign / ad-set / ad ids: `GET /ads/tree?profileId=&campaignId=` or the
     campaign's `profileId`.

   Anything else is 404 (never 403), as everywhere in the app.
4. **Platforms.** `GET /zernio/platforms` returns, for each of `facebook, instagram,
   tiktok, linkedin, pinterest, twitter, googleads`:
   - **Label and status:** the label, whether an ads account is connected in this
     company's profile, and the connected account(s);
   - **Options:** the goals that platform accepts (from the Zernio create schema, kept as
     a commented constant), the CTAs it honours, and which targeting fields it accepts
     (portable vs platform-only, per Zernio's TargetingSpec notes);
   - **Rules:** creative rules (image / video / text limits).

   The frontend's options come only from here.
5. **Connect.**
   - **Start:** `POST /zernio/connect {platform}` (manager+) → `{auth_url}` or
     `{already_connected: true}`.
     - Ads connection: `GET /connect/{platform}/ads?profileId&redirect_url`, with
       `loginMode=business` for facebook/instagram (no posting account needed).
     - LinkedIn / Pinterest / X need a posting account first. When Zernio says so, the
       route returns the posting-connect URL (`GET /connect/{platform}`) instead, and the
       UI runs the ads step after it.
   - **Return:** `redirect_url` = `FRONTEND_BASE_URL/marketing/paid/zernio/callback?zs=<signed
     state>`. The state is a JWT (30 min, bound to tenant + user + platform), like
     SocialAPI.
   - **Finish:** `POST /zernio/callback {zs, …query}` checks the state, then reports the
     outcome.
   - **Facebook Page:** Page selection (`/connect/facebook/select-page`) is supported if
     Zernio asks for it.
   - **Disconnect:** `DELETE /zernio/accounts/{id}` (manager+).
6. **Ad accounts.**
   - `GET /zernio/accounts/{id}/ad-accounts` returns id, name, currency, timezone, status,
     `selectable` + `unusable_reason`, and minimum daily budget. An unusable ad account is
     shown, not hidden.
   - TikTok identities (`/ads/tiktok-identities`) and Meta Pages + Instagram identities
     (`/ads/instagram-accounts`) are listed for the identity pickers.
7. **Targeting helpers** (viewer+):
   - `GET /zernio/targeting/search?account_id&q&dimension&geo_type&country` →
     `/ads/targeting/search`;
   - `POST /zernio/targeting/reach {account_id, ad_account_id, targeting, optimization_goal?}`
     → `/ads/targeting/reach-estimate`. `available:false` is shown as "no estimate for
     this platform", never invented.
8. **Media.**
   - **Sources:** creatives use our media library (`media_ids`, SPEC-BE-074). Images and
     videos are passed as **public URLs** (signed `/api/v1/media/f/{token}`); this needs
     `PUBLIC_BASE_URL` to be public https, or S3, the same rule as Instagram organic.
     Otherwise there is a 422 that says so.
   - **Meta images:** may instead be sent as base64 to `POST /ads/images` (≤ 30 MB) when
     there's no public URL.
   - **Meta videos:** `POST /ads/videos {videoUrl, async:true}`, polled at `GET
     /ads/videos/{id}` until ready.
9. **Create campaign** (manager+). `POST /zernio/campaigns` maps 1:1 onto Zernio's `POST
   /ads/create` single-creative shape.
   - **Request fields:**
     - account and naming: `account_id, ad_account_id, name, campaign_name?,
       ad_set_name?, goal`;
     - budget and schedule: `budget {amount (major units, Decimal), type: daily|lifetime},
       start_at?, end_at?` (lifetime needs `end_at`), and `bid {strategy, amount?,
       roas_floor?}`;
     - targeting: the TargetingSpec (countries, regions, cities ± radius, zips, metros,
       custom locations, excluded locations, age_min/max, gender, languages, interests,
       behaviors, income tier);
     - Meta delivery: `placements` (Meta, else automatic), `special_ad_categories`;
     - creative: `headline, long_headline?, body, description?, call_to_action,
       link_url, media_ids` (one image or one video; Google Display needs landscape +
       square);
     - identity: `page_id / instagram_account_id` (Meta), `identity_id` (TikTok),
       `organization_id` (LinkedIn), `board_id` (Pinterest);
     - Google Search: `campaign_type: display|search` and `keywords[{text, match}]`;
     - other: `promoted_object` (pixel/event for conversions), `lead_gen_form_id`
       (lead_generation), and `status: ACTIVE|PAUSED`.
   - **Validation:** our Pydantic schema enforces the per-platform rules from FR4
     (required fields per goal, length limits, mutually exclusive image/video, lifetime ⇒
     end date, start in the future, age 13–100 with min ≤ max). Zernio's own 400 message is
     shown as is for anything it rejects beyond that.
   - **Request handling:** every create carries an `Idempotency-Key`, so a retried click
     never makes two campaigns.
   - **Response:** the created campaign / ad set / ad ids and the stored schedule.
   - **D3 = B:** any manager+ chooses ACTIVE or PAUSED; the choice is sent as is.
10. **Validate and preview.**
    - `POST /zernio/campaigns/validate` sends `validateOnly:true` where Zernio supports it
      (Meta, Google pmax/demand_gen, OpenAI). Other platforms return `{supported:false}`,
      and the UI says "checked on publish".
    - `POST /zernio/campaigns/preview` (Meta) renders `/ads/preview` iframes, shown in a
      sandboxed iframe.
11. **Boost a post** (manager+). `POST /zernio/boost {account_id, ad_account_id,
    post_id, goal, budget, schedule, targeting, status}` → `/ads/boost` (manager+, ACTIVE or
    PAUSED).
12. **List and manage** (viewer+ reads, manager+ writes):
    - **List:** `GET /zernio/campaigns?platform&status&q&page&range=7d|30d|90d` →
      `/ads/tree?profileId=`, which returns the campaign → ad set → ad hierarchy. Each node
      carries status, review status, budget, currency and metrics (spend, impressions,
      clicks, CTR, conversions, ROAS when Zernio reports them). Missing metrics are null,
      never estimated.
    - **Pause/resume:** `POST /zernio/campaigns/{id}/pause|resume`, and the same for
      `ad-sets/{id}` and `ads/{id}` (Zernio's `PUT …/status`).
    - **Change:** `PATCH /zernio/campaigns/{id} {name?, budget?}` → `PUT
      /ads/campaigns/{id}`.
    - **Resume** is allowed for any manager+ (D3 = B).
    - **Delete:** `DELETE /zernio/campaigns/{id}` → Zernio's delete (manager+, confirmed
      in the UI).
    - **Campaign analytics:** `GET /zernio/campaigns/{id}/analytics?range&breakdowns` →
      summary + daily timeline (+ age/gender/country breakdowns on Meta). A 202
      "backfill pending" is shown as "Zernio is still collecting results".
13. **Errors.** Zernio's error message is shown as is.
    - 400/409/422 → 422;
    - 401 → 503 ("the server's Zernio key was rejected", which is logged for the
      operator);
    - 402/403 → 422, shown as "Zernio refused this: <Zernio's reason>" (amended 2026-10-08:
      the app shows every 403 as "your role can't do this", which hid Zernio's reason, such
      as the ads add-on, payment or a plan limit);
    - 404 → 404;
    - 429 → 429 with Retry-After;
    - 501 `feature_not_available` → 422 "not available on this platform";
    - 5xx/network → 502/504.
    - Large-body uploads use URLs (Zernio's base64 limit is about 4.5 MB).
14. **Audit.** Every write adds an `audit_log` row: `zernio.*` (`profile_created`,
    `connect_started`, `account_connected`, `account_disconnected`, `campaign_created`,
    `campaign_paused/resumed/updated/deleted`, `ad_set_*`, `ad_*`, `post_boosted`),
    `resource_type` = tenant, with Zernio ids, platform, goal and budget in the metadata.
    Ad copy is never logged.
15. **Dev fakes.** `dev_fakes` answers `zernio.com` (profiles, accounts, connect,
    ad-accounts, targeting search, reach, create, tree, status, analytics, boost, media)
    for `META_FAKE_TRANSPORT=true` and the tests. The key `zernio_bad` answers 401.

## Non-functional

- **Timeouts:** `httpx` through `base_adapter.http`, a 30 s timeout, 120 s for create,
  boost and video calls.
- **Money and time:** money is a Decimal in major units (Zernio takes whole units, not
  cents), and the currency comes from the ad account. Datetimes are sent as UTC ISO with
  an offset.
- **Logging:** structlog, with no keys, tokens or ad copy in the logs.
- **Lint and types:** no new lint or mypy errors over the baseline.

## Target files

- New:
  - `backend/app/integrations/zernio.py` (client + error mapping + platform rules
    constant);
  - `backend/app/services/zernio_service.py`;
  - `backend/app/schemas/zernio.py`;
  - `backend/app/api/v1/zernio.py`.
- Changed:
  - `backend/app/api/router.py` (register the router);
  - `backend/app/config.py` (2 settings);
  - `backend/app/integrations/dev_fakes.py` (Zernio host);
  - `specs/SPEC-BE-002.md` / `SPEC-BE-003.md` (env vars);
  - `backend/.env` (empty `ZERNIO_API_KEY=` line; the user pastes the key);
  - `CLAUDE.md` (one paragraph).

## Acceptance criteria

These are verified on the live Postgres inside rolled-back transactions, with
`dev_fakes`, using real register/login tokens.

1. No key → every `/zernio/*` route answers 503; the app still boots.
2. The first call creates one profile per company and stores the id. A second company gets
   a different profile; a repeated call creates none.
3. Company A cannot read or change company B's account, ad account, campaign, ad set or ad
   (404 each).
4. `GET /zernio/platforms` lists 7 platforms with goals, CTAs and targeting fields that
   match Zernio's schema.
5. Connect returns an auth URL with our signed state. A tampered or expired state gives
   400, and a good one completes.
6. Create: invalid combinations give 422 with a clear message (lifetime without end, a
   TikTok image, an X CTA, a LinkedIn traffic ad without a link…). A valid one creates a
   campaign and writes an audit row. An Idempotency-Key retry makes no duplicate.
7. D3 = B: a manager's ACTIVE create and resume both work. An agent's or viewer's create,
   pause or resume gives 403.
8. List / pause / resume / update / delete / analytics work through the fakes; null metrics
   stay null.
9. Error mapping matches FR13.
10. `ruff check app` and `mypy app` show only the baseline errors.

## Implementation notes (2026-10-08)

- **Files.** Exactly the target files:
  - new: `integrations/zernio.py`, `services/zernio_service.py`, `schemas/zernio.py`,
    `api/v1/zernio.py`;
  - changed: `api/router.py`, `config.py`, `integrations/dev_fakes.py`, `backend/.env`
    (an empty `ZERNIO_API_KEY=` plus `ZERNIO_BASE_URL`), and SPEC-BE-002/003.
  - Also: a one-line mypy type fix in `integrations/socialapi.py`, for an error the
    same-day SocialAPI fix had added.
- **Deviation, connect state:** a short single-use nonce, not a JWT. It is kept in
  `tenants.settings.zernio.pending` with the user, platform, step and a 30-minute expiry.
  The reason: X carries the redirect inside its OAuth state and caps the URL-encoded
  `redirect_url` at 258 characters, and a JWT doesn't fit. Any other user, a reused nonce
  or an expired one gets 400.
- **Connect flow:**
  - Zernio's hosted mode is used (not headless). Zernio shows its own Facebook Page
    picker, so we have no select-page step.
  - X needs its posting account first. Its connect answers `step: "posting"` and runs
    `GET /connect/twitter`; Connect again then adds the ads account.
  - Instagram reuses the Meta ads connection, which Zernio reports as `alreadyConnected`.
- **Which account goes where:**
  - Create and the ad-account listing use the Zernio ads account (`metaads`,
    `tiktokads`, …).
  - Boost uses the posting account (Zernio's docs: "normally the connected posting
    account"), and its ad account is checked against the company's ads connection for
    that platform.
- **Goals per platform:** Meta, LinkedIn and Google follow Zernio's documented lists. For
  TikTok, Pinterest and X Zernio doesn't list every goal, so the standard objectives are
  offered and Zernio's own message is shown if one is refused. `catalog_sales` and
  `job_applicants` are left for later (D4).
- **Bids:** Meta's bid fields go in `platformSpecificData`, as Zernio prefers. Google uses
  the flat fields.
- **Media:**
  - **TikTok:** `imageUrl` carries the video URL, per Zernio's docs.
  - **Meta images:** with no public address they are sent as base64 to `POST /ads/images`.
  - **Everything else** needs `PUBLIC_BASE_URL` to be public https, or S3. Otherwise the
    answer is a 422 that says so.
- **Idempotency:** creates and boosts send `Idempotency-Key = <tenant>:<request_id>`.
  A replayed answer is audited once: the `request_id` is in the audit metadata.
- **Campaign edits:** Zernio's update covers Meta and Google only. Other platforms answer
  422 with that explanation.
- **Meta preview:** only the `facebook.com` iframe URL from Zernio's HTML is used; the raw
  HTML is never rendered.
- **Verification run:** the harness refused the inline heredoc (a false "Remove-Item"
  match), so the same check script ran from the session scratchpad, outside the repo.
