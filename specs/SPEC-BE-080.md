# SPEC-BE-080: OAuth connect for social accounts (Facebook/Instagram, TikTok, LinkedIn)

Status: IMPLEMENTED (code, 2026-10-03). 12 no-DB checks against dev fakes pass: authorize URLs, code exchange for all three flows, Page and organization listing, TikTok refresh, and invalid grant → auth error. `ruff`/`mypy` add no errors. **Pending:** acceptance 2–8 on the live DB (Postgres isn't installed or running here). Nothing has been tried against the real platforms; that needs the user's app credentials and registered redirect URIs. Requested by the user (item 12: "OAuth for connected platforms … Track connection status, account ID, permissions, token status, last sync and errors"). SPEC-BE-075 left OAuth out (pasted tokens only). Frontend: SPEC-FE-052.

## Purpose
Each company connects its own social accounts with the platform's sign-in ("Connect with Facebook / TikTok / LinkedIn") instead of pasting tokens. Access and refresh tokens stay on the backend, encrypted, and are refreshed before they expire. Pasted tokens keep working; both paths store the same integration shape, so publishing (SPEC-BE-075/076) and analytics (SPEC-BE-078) don't change.

## Flows
`{flow}` is `meta` (Facebook Page and its linked Instagram account), `tiktok` or `linkedin`. The redirect URI is `FRONTEND_BASE_URL + /marketing/organic/accounts/callback/{flow}` (it must be registered in each developer app).

1. `GET /social/oauth/{flow}/connect` (manager+) → `{login_url}`. The `state` is a signed JWT (`typ=social_oauth`, flow, tenant, user, nonce, 10-minute expiry), and the nonce is stored on the flow's integration row in `settings.oauth_nonce`. It's single use, exactly like SPEC-BE-054.
2. The platform sends the browser back to the callback page, which posts `{code, state}` to `POST /social/oauth/{flow}/callback` (manager+). The backend checks the state, consumes the nonce, exchanges the code server to server, and:
   - **meta:** short-lived user token → long-lived user token (`grant_type=fb_exchange_token`) → `GET /me/accounts?fields=id,name,access_token,picture,instagram_business_account{id,username,profile_picture_url}` and `GET /me/permissions`. Page tokens derived from a long-lived user token don't expire. The choices are held encrypted in `settings.oauth_pending` → response `{flow, choices: [{id, name, avatar_url, instagram: {id, username} | null}], scopes}`.
   - **linkedin:** token (60 days, plus a refresh token when LinkedIn issues one) → `GET /rest/organizationAcls?q=roleAssignee&role=ADMINISTRATOR&state=APPROVED`, then `GET /rest/organizations/{id}` for each name → choices of company pages, held pending as above.
   - **tiktok:** token (access 24 h, refresh 365 days, `open_id`, `scope`) → saved at once (one TikTok account per sign-in) → response `{flow, saved: true, choices: []}`.
3. `POST /social/oauth/{flow}/select` (manager+) `{account_id, include_instagram}`:
   - **meta:** saves the chosen Page into the `facebook` integration (`page_id`, Page token), and, when `include_instagram` and the Page has one, into `instagram` (`ig_account_id`, the same Page token).
   - **linkedin:** saves `organization_urn` and the token into `linkedin`.
   - An id that wasn't in the pending list → 422. Nothing pending → 409.

**Saving** (`integration_service.save_oauth_credentials`, new): writes the same `settings.fields` and encrypted `settings.secrets_enc` (now also holding `refresh_token` when there is one) as the pasted-token form, plus `settings.oauth = {via: "oauth", scopes, access_expires_at, refresh_expires_at, external_account_id}`. `integrations.expires_at` = the refresh token's expiry (or the access token's when there's no refresh token; null when the token doesn't expire), so the SPEC-BE-017 status turns `needs_reconnect` when the connection can no longer be renewed. Then the SPEC-BE-075 connection test runs, the profile is stored, and an audit row is written (`integration.oauth_connected`, never a token in it).

## Token refresh
- **Before use:** `social_account_service.connection()` refreshes when the access token expires within 5 minutes and a refresh token exists. The refresh is committed in its own session, so a failed publish can't roll back a rotated refresh token.
- **Job:** `social_token_refresh` (every 30 minutes, in `workers/tasks/sync_tasks.py`) refreshes OAuth tokens expiring within 2 hours (TikTok) or 7 days (LinkedIn).
- **Failure:** a refresh rejected by the platform (invalid/expired grant) marks the integration `expired` with the platform's message, so the Accounts page shows Reconnect. A network or 5xx failure is retried on the next run.
- **Meta Page tokens** don't expire and are never refreshed; a revoked one fails the connection test or a publish with code 190, as today.

## Connection status (item 12)
`GET /social/accounts` items gain:
- `connected_via`: `oauth` | `token` | null
- `account_id`: Page ID / IG account ID / TikTok `open_id` / organization URN
- `scopes`: the granted permissions (OAuth path; empty when unknown)
- `token_status`: `valid` | `expiring_soon` (access expires within 24 h and can't be refreshed, or the refresh token expires within 7 days) | `expired` | `no_expiry` | `unknown` (pasted tokens)
- `token_expires_at`, `reconnect_by` (the refresh token's expiry)
- `last_checked_at` (the last connection test), `last_synced_at` (the last successful organic metrics import for that platform; SPEC-BE-078's import now sets `integrations.last_sync_at`)
- `oauth_available`: the server has that platform's app credentials

## Configuration (`config.py`, documented in SPEC-BE-003)
| Variable | Use |
|---|---|
| `META_APP_ID` / `META_APP_SECRET` | already exist (SPEC-BE-054); reused for the social sign-in |
| `META_SOCIAL_LOGIN_CONFIG_ID` | optional Facebook Login for Business configuration (user access token). Without it the dialog asks for the scopes `pages_show_list, pages_read_engagement, pages_manage_posts, read_insights, instagram_basic, instagram_content_publish, instagram_manage_insights, business_management` |
| `TIKTOK_CLIENT_KEY` / `TIKTOK_CLIENT_SECRET` | TikTok Login Kit; scopes `user.info.basic, video.publish, video.upload, video.list` |
| `LINKEDIN_CLIENT_ID` / `LINKEDIN_CLIENT_SECRET` | LinkedIn; scopes `r_organization_admin, w_organization_social, r_organization_social` |

A flow without its app credentials → 503 "… sign-in isn't set up on this server." The app always boots without them.

## Security
- Tokens are never returned, never logged, and never put in audit metadata. The `httpx` logger stays at WARNING.
- State: signed, 10 minutes, bound to tenant + user + flow, single-use nonce.
- Disconnect (`DELETE /integrations/{provider}`) also drops `oauth`, `oauth_pending` and `oauth_nonce`.
- Pending choices (with their tokens) are encrypted and expire with the next connect.

## dev_fakes
With `META_FAKE_TRANSPORT=true`: Graph `oauth/access_token` (code and `fb_exchange_token`), `/me/accounts`, `/me/permissions`; TikTok `/v2/oauth/token/` (code and refresh); LinkedIn `/oauth/v2/accessToken`, `/rest/organizationAcls`, `/rest/organizations/{id}`. A code of `bad` → the platform's invalid-grant error.

## Acceptance criteria (live DB, rolled back, dev fakes)
1. `connect` for each flow returns the platform's authorize URL with `client_id`/`client_key`, the exact redirect URI, the scopes (or `config_id`) and a state. Missing app credentials → 503.
2. meta: callback → choices with the Page and its Instagram account. select with `include_instagram` → the `facebook` and `instagram` integrations are connected, `GET /social/accounts` shows `connected_via="oauth"`, the `account_id`s, the scopes and `token_status="no_expiry"`.
3. linkedin: callback → company pages; select → `linkedin` connected with the URN; `token_expires_at` ≈ now + 60 days.
4. tiktok: callback saves directly; `token_status="valid"`; `reconnect_by` ≈ now + 365 days.
5. State: a reused state, another user's state, an expired state, or a state for another flow → 400. A select with an unknown id → 422; with nothing pending → 409.
6. Refresh: a TikTok access token that expires in 1 minute → `connection()` refreshes it (a new encrypted token, `access_expires_at` moves on). A refresh answered with invalid grant → integration `expired`, `token_status="expired"`. The job refreshes only tokens inside its window.
7. Pasted-token integrations still work and show `connected_via="token"`, `token_status="unknown"`.
8. No token appears in responses, logs or `audit_log.metadata` (grep of the captured output and rows).
9. `ruff check` and `mypy` add no new errors.

## Target files
- New: `app/services/social_oauth_service.py`
- Changed: `app/api/v1/social.py`, `app/schemas/social.py`, `app/services/social_account_service.py`, `app/services/integration_service.py` (`save_oauth_credentials`, disconnect keys), `app/integrations/facebook.py`, `tiktok.py`, `linkedin.py` (authorize URL, code exchange, refresh, account listing), `app/integrations/dev_fakes.py`, `app/services/analytics_service.py` (`last_sync_at` after a successful import), `app/workers/tasks/sync_tasks.py` + `app/workers/schedules.py` (refresh job), `app/config.py`, `specs/SPEC-BE-003.md`

## Out of scope
Revoking tokens at the platform on disconnect, several accounts per platform per company, OAuth for the ad platforms other than Meta, X / YouTube / Pinterest.
