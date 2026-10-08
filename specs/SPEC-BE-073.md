# SPEC-BE-073: Live Meta sandbox run (first real Meta call)

Status: DRAFT (2026-10-02). Not started; waiting for the Meta developer app (prerequisites below). This closes SPEC-BE-054 criterion 11 and SPEC-BE-055 criterion 12. Every Meta check so far used `httpx.MockTransport` or `META_FAKE_TRANSPORT`; nothing has reached the real Graph API.

## Purpose
Prove, once and on the record, that the existing Meta code works against the real Graph API: connect → select → build → validate → preview → publish → pause/resume → results import → cleanup. It uses a Meta **sandbox ad account**, so no money is spent and nothing is delivered.

This is a **verification spec**. No code changes are expected. Any mismatch found becomes a small, separately approved fix (see "When something fails").

## Prerequisites (the owner does these, outside the code)
1. **Meta developer app** (type Business) with Facebook Login for Business and a **configuration**:
   - Token type: business integration system user.
   - Assets: ad accounts, Pages, Instagram accounts, pixels.
   - Permissions: `ads_management`, `ads_read`, `business_management`, `pages_show_list`, `pages_read_engagement`, `instagram_basic`.
   - The app stays in **Development mode**; the person connecting must have a role on the app (admin/developer/tester).
2. **Valid OAuth redirect URI:** `http://localhost:3000/integrations/meta/callback` (localhost is allowed in development mode). It must equal `{FRONTEND_BASE_URL}/integrations/meta/callback` exactly.
3. **Sandbox ad account:** created in the app dashboard (Marketing API → Tools → sandbox ad account). Note its ID and currency.
4. **A Facebook Page** the connecting user administers (ads run as a Page; sandbox ads still need one). An Instagram account and a pixel are optional; without them, those checks are skipped, not failed.
5. **`backend/.env`:** `META_APP_ID`, `META_APP_SECRET`, `META_LOGIN_CONFIG_ID` set; `META_GRAPH_VERSION=v25.0`; `META_FAKE_TRANSPORT=false`; `APP_ENV` not `production`. Restart the backend afterwards (the reload trick for `.env` changes applies).

The app secret is never pasted into the chat. The owner edits `.env` directly.

## How the run is done
- Against the **running app** (backend :8000 + frontend :3000) and the **live Postgres DB**. This run is *not* rolled back: real Meta objects get real IDs, so the DB rows must match them until cleanup.
- A **dedicated test company** registered for this run (e.g. slug `meta-sandbox-test`), not dev-shop, so seeded data isn't touched. The owner of that company does the Facebook login in the browser, because OAuth needs a human.
- Claude drives the API steps inline (no saved scripts, no files), and reads results from the API, the DB and Meta's Graph API with the stored token. Tokens and the app secret never appear in output or logs.
- At the end, everything is cleaned up (see "Cleanup").

## Steps and acceptance criteria
Each is recorded as pass / fail / skipped, with evidence (Meta object IDs, HTTP status, short response excerpt).

1. **Config:** `GET /integrations/meta/connect` returns a login URL containing `config_id` and a signed `state` (not 503).
2. **Connect:** the owner completes Facebook login; the callback stores the token (encrypted; `credentials_ref` isn't plaintext) and returns ad accounts and Pages.
   - **Open question from SPEC-BE-054:** does `/me/adaccounts` / `/me/accounts` list assets for this token type? Record what comes back.
   - If the sandbox account is **not listed** (sandbox accounts may not be assignable to a business-integration system user), fall back to the pasted-token path: generate a user token for the sandbox account in the app dashboard and save it via `PUT /integrations/meta_ads` with `ad_account_id`, `page_id` (amendment A of SPEC-BE-054). Record which path was used.
3. **Select:** choosing the sandbox account + Page → the integration shows `connected`; the account's currency matches what Meta reports.
4. **Build:** in the Meta builder, a Traffic campaign → 1 ad set (one country, broad audience, small daily budget) → 1 single-image ad with a real destination URL. The image upload (`POST /meta/media`) returns an `image_hash`.
5. **Validate:** `POST /campaigns/{id}/validate` → Meta `validate_only` runs and returns `ok` (or field errors mapped to `{level, id, field}`; either way a real Meta reply is recorded).
6. **Preview:** `generatepreviews` returns `iframe_html` for at least the Facebook feed format.
7. **Publish:** all four objects are created in Meta (campaign, ad set, creative, ad); their IDs are stored in `campaigns.metadata`, `ad_groups.external_id`, `ads.external_ad_id`; audit `campaign.published`. A Graph GET of each ID confirms it exists with the expected objective, budget (offset handled for the currency) and status.
8. **Status read-back:** `effective_status` is read and stored (sandbox values are recorded as-is).
9. **Pause / resume:** both reach Meta (confirmed by a Graph GET after each), and our status follows.
10. **Rollback on failure (real API):** a second publish with an injected bad field at the ad step (e.g. an invalid `image_hash`) → 502 with Meta's message, the already-created Meta campaign and ad set are **deleted on Meta** (Graph GET returns not found or `DELETED`), and nothing persists in our DB.
11. **Results import:** `POST` the on-demand import → it completes without error. Sandbox accounts usually return no insights; empty results with our metrics still null is a **pass**. Any rows written must have `source='meta'`.
12. **Errors:** revoke the app's access (or use an expired token) → the next call marks the integration `expired` and returns 409.
13. **No leaks:** a grep of the backend log for the access token and app secret finds nothing (the `httpx` logger stays at WARNING).
14. **Graph version:** record any deprecation warnings Meta returns for v25.0. Meta's v26 breaking changes reportedly start 2026-10-27; if v25 is affected, note it for a follow-up spec.

## Cleanup
- Delete the test campaign(s) on Meta (DELETE on the campaign ID cascades to ad sets and ads); confirm with a Graph GET.
- Disconnect the integration (`DELETE /integrations/meta_ads`), then delete the test company's rows from the live DB, in dependency order, inside one transaction. Confirm zero rows remain for that `tenant_id`.
- Revoke the test token in Meta Business settings if a pasted user token was used.
- The sandbox ad account and the Meta app are kept for future runs.

## When something fails
- A failure is recorded with Meta's error code, subcode and message, not fixed on the spot.
- Each needed fix is proposed (file, change, reason) and waits for approval. Expected fix sites, all existing files: `integrations/meta_ads.py` (field names, edges, version), `services/meta_builder_service.py` (request bodies), `services/integration_service.py` (asset listing). No new files.
- After fixes, only the failed steps and the publish path (7–10) are re-run.

## Target files
- None for the run itself.
- This spec gets a "Results (date)" section with the pass/fail table.
- SPEC-BE-054 (criterion 11) and SPEC-BE-055 (criterion 12) status lines are updated to point here.
- `CLAUDE.md`'s Meta section gets one line saying whether the live run passed.

## Out of scope
- A real (non-sandbox) campaign that spends money. That is the next step after this passes, done by the owner with a small budget, and recorded as an amendment here.
- App Review / Business Verification for other companies.
- The other six platforms (each needs its own approved API access; one live-run spec per platform when it arrives).
- Upgrading to Graph v26.
