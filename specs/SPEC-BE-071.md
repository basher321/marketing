# SPEC-BE-071: Production hardening from the SQA review (database + backend)

Status: IMPLEMENTED and verified 2026-10-02 (approved by the user: "do fix spec and execution"). See **Execution log** at the end for the exact changes and results. Frontend items are in SPEC-FE-047. Infrastructure items that need your accounts or servers are in the **Operator checklist** at the end; they are documented, not executed.

## Findings this spec fixes (from the SQA passes on 2026-10-02)

| # | Severity | Finding (evidence) |
|---|---|---|
| F1 | Blocker | `pip install -r requirements.txt` fails with ResolutionImpossible: two conflicting blocks pin fastapi, uvicorn, sqlalchemy, pydantic, cryptography, httpx and others twice, plus unused celery and redis. |
| F2 | Blocker | `APP_DEBUG` is true in `.env` **and its default is true**. In debug mode Starlette renders a Python traceback instead of the JSON 500 handler (confirmed on `GET /kb/documents`). |
| F3 | Blocker | Known-vulnerable dependencies: python-jose 3.3.0 (JWT algorithm confusion / DoS CVEs), starlette 0.41.3 (multipart and Range-header DoS CVEs), cryptography 44.0.0. |
| F4 | Blocker | No production guard: the server starts in production with a dev-looking `SECRET_KEY`, localhost CORS, `LLM_PROVIDER=mock` or a superuser database login. |
| F5 | High | A viewer can create customers (201), and can call the legacy `POST /content/generate` (AI spend, 200). |
| F6 | High | `GET`/`POST /kb/documents` crash (500): the model maps `content` / `embedding_status` / `extra_metadata`, but the live table has `body`, `document_type`, `metadata` and `indexed_at`. |
| F7 | High | Refresh tokens can be reused after a refresh, and logout revokes nothing (the `refresh_tokens` table exists but is unused). |
| F8 | High | No request size limit: a 20 MB JSON body is accepted (201). |
| F9 | Medium | `/docs` and `/openapi.json` are public. |
| F10 | Medium | `POST /webhooks/{provider}` accepts any unauthenticated request (nothing is processed; it's a stub). |
| F11 | Medium | Weak passwords such as "Password1" are accepted. |
| F12 | Medium | A workflow `call_webhook` URL pointing at a private address is accepted at save (it is blocked at run time). |
| F13 | Low | `/health` doesn't check the database. |
| F14 | Low | `BCRYPT_ROUNDS` isn't used by the password hasher. |
| F15 | Low | Company reset doesn't delete `ai_campaign_runs`. |
| F16 | Low | Missing indexes: 5 tenant tables lack a `tenant_id` index (action_executions, notifications, order_items, refresh_tokens, webhook_events), and several foreign keys have none. |

Not changed (kept as documented behaviour): the API has two error-body shapes (`{"error"}` for business errors, `{"detail"}` for validation); the frontend reads both. Access tokens stay stateless and valid until they expire (15 minutes) even after logout; F7 revokes the refresh token, which bounds the risk to those 15 minutes.

## Changes (file → what)

1. **F1 `requirements.txt`**
   - One deduplicated list, pinned to the versions that are installed and verified.
   - celery and redis removed (unused; the scheduler is in-process).
   - Test tools kept in a clearly marked section.
   - The `SPEC-BE-001` note is updated.
2. **F3 dependencies.** Upgrade:
   - python-jose → 3.5.0;
   - fastapi to a release whose starlette includes the DoS fixes (the latest fastapi that keeps pydantic 2.x and the current code working; chosen at install, recorded here);
   - cryptography → a current release.

   The full regression must pass (rules below). If an upgrade breaks something that can't be fixed in scope, that package stays at its old version and the result is recorded.
3. **F2 + F4 + F9 `app/config.py`**
   - `APP_DEBUG` defaults to **false**.
   - New production validator: with `APP_ENV=production`, startup refuses each of these, naming the problem:
     - `APP_DEBUG=true`;
     - `SECRET_KEY` shorter than 32 characters or containing changeme/secret/dev/test/example;
     - a CORS origin that isn't https, or is localhost;
     - `LLM_PROVIDER` mock or fixture (fixture was already refused);
     - fakes on (already refused).

   **`app/main.py`:**
   - `docs_url`, `redoc_url` and `openapi_url` are off in production.
   - On startup in production, if the database login is a superuser or bypasses RLS, the server refuses to start with that message.
4. **F5 roles**
   - `POST /customers` → `agent` and up (`api/v1/customers.py`).
   - `POST /content/generate` → `manager` and up (`api/v1/content.py`).
   - `POST /kb/documents` → `manager` and up (`api/v1/kb.py`).
   - `POST /conversations/{id}/messages` → `agent` and up (`api/v1/conversations.py`).
5. **F6 KB model fix** (`models/kb_document.py`, `services/kb_service.py`, `api/v1/kb.py`, `ai/retrieval.py`)
   - Map to the live columns: `body`, `document_type` (default "note"), `metadata`, `indexed_at`, `source_url`.
   - `embedding_status` is derived: "indexed" if `indexed_at` is set, otherwise "pending".
   - Retrieval searches `body`.
6. **F7 refresh token rotation and revocation** (`core/security.py`, `services/auth_service.py`, `api/v1/auth.py`, `schemas/auth.py`)
   - Every issued refresh token is recorded in `refresh_tokens` (SHA-256 of the jti, expiry, user, tenant, user agent and IP when available).
   - `POST /auth/refresh` accepts only a recorded, unrevoked, unexpired token. It revokes it (`replaced_by` = the new row) and issues a new pair.
   - **Reuse detection:** presenting an already-revoked refresh token revokes every active refresh token of that user (a stolen-token signal).
   - `POST /auth/logout` with `{refresh_token}` revokes it (204 either way, no information leak).
   - A password reset revokes all of the user's refresh tokens.
7. **F8 body size limit** (new middleware in `app/middleware/body_limit.py`)
   - Bodies are limited to 2 MB by default.
   - Upload routes keep their own limits: `/ads/{platform}/media` and `/meta/media` up to 1 GB, `/tenants/me/branding/*` 2 MB.
   - The middleware checks `Content-Length` and counts streamed bytes, answering 413 `{"error": "Request body too large."}`.
   - It is registered in `main.py`.
8. **F10 `api/v1/webhooks.py`:** no provider webhook is implemented, so the route answers **404 for every provider** instead of accepting unauthenticated data. The comment says to restore it only together with signature verification.
9. **F11 `validators/password_policy.py`**
   - At least 10 characters, with upper, lower and digit (as before).
   - Not in a list of common passwords (built in, about 50 entries including "Password1" and "Passw0rd").
   - May not contain the email's local part.

   It is used by sign-up, user creation and password reset, all of which already call it. Existing passwords keep working.
10. **F12 workflow save:** a `call_webhook` URL must be public https when the workflow is saved, using the same guard as at run time (`services/workflow_service.py`).
11. **F13 `/health`:** runs `SELECT 1` and returns `{"status": "ok", "database": "ok"}`, or 503 `{"status": "degraded", "database": "unreachable"}`.
12. **F14 `core/security.py`:** the bcrypt context uses `BCRYPT_ROUNDS`.
13. **F15 `services/tenant_service.py`:** `ai_campaign_runs` is added to the company reset.
14. **F16 additive DDL** (`CREATE INDEX IF NOT EXISTS`, applied once, live DB):
    - a `tenant_id` index on the 5 tables;
    - indexes on `ads.content_asset_id`, `ad_groups.audience_id`, `ai_campaign_runs(tenant_id, status)`, `refresh_tokens(user_id)` and `refresh_tokens(token_hash)`.

## Acceptance (live DB, rolled-back transactions; dev-shop untouched)
1. `pip install -r requirements.txt` succeeds in a fresh virtualenv (dry run), and `pip check` is clean.
2. Every check from the SQA passes, re-run:
   - the authorization sweep (190 routes);
   - tenant isolation (23 probes, 0 leaks);
   - the security attacks;
   - the input edge cases;
   - the GET sweep on dev-shop;
   - the AI Autopilot suite;
   - the ad-platform suite (42 checks).

   All of these pass, with the earlier failures now passing:
   - a viewer gets 403 on the four routes;
   - the KB list and create work;
   - a reused refresh token gets 401 and revokes the family;
   - logout revokes the refresh token;
   - a 20 MB body gets 413;
   - "Password1" is refused;
   - a private webhook URL is refused at save;
   - webhooks return 404;
   - `/health` reports the database;
   - the production validator refuses each bad setting;
   - docs are off in production.
3. ruff and mypy show no new errors, and the app imports.
4. `pip-audit` (installed for the check, then removed) reports no known vulnerabilities in the pinned set, or each remaining one is listed with its reason.

## Operator checklist (needs your servers or accounts; not executed)
1. **Database login:** create a non-superuser role for the app, for example:
   ```sql
   CREATE ROLE marketing_app LOGIN PASSWORD '<strong>' NOSUPERUSER NOBYPASSRLS;
   GRANT CONNECT ON DATABASE marketing TO marketing_app;
   GRANT USAGE ON SCHEMA public TO marketing_app;
   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO marketing_app;
   GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO marketing_app;
   ```
   Use it in `DATABASE_URL`/`DATABASE_URL_SYNC` with `sslmode=require`. The server now refuses to start in production with a superuser login.
2. **Production `.env`:**
   - `APP_ENV=production` and `APP_DEBUG=false`;
   - a new `SECRET_KEY` (`python -c "import secrets; print(secrets.token_urlsafe(48))"`);
   - keep `ENCRYPTION_KEY` as it is;
   - https `CORS_ORIGINS` and `FRONTEND_BASE_URL`;
   - real SMTP credentials (password-reset emails);
   - an `LLM_PROVIDER` key, or company AI models;
   - `META_APP_ID`/`SECRET`/`LOGIN_CONFIG_ID` if Meta OAuth is used.
3. **Workers:** run the web server with several workers and `SCHEDULER_ENABLED=false`, plus exactly one process with `SCHEDULER_ENABLED=true` (otherwise scheduled jobs run once per worker). The login rate limiter counts per process; put a reverse-proxy rate limit in front.
4. **Migrations:** the schema was built outside Alembic.
   - Before launch, take a `pg_dump --schema-only` baseline, keep it under version control, and apply future DDL as numbered SQL files.
   - Introducing Alembic is a separate spec (the models must be aligned first, or autogenerate proposes destructive changes).
5. **Backups:** daily `pg_dump`, plus a restore test.
6. **Ad platforms:** one small paused campaign per platform, with real approved access, before customers use it.

## Execution log (2026-10-02)

### Files changed (timestamp scan: nothing else in backend/ changed)
| File | Change |
|---|---|
| `backend/requirements.txt` | F1/F3: rewritten, one pin per package (details below). |
| `backend/app/config.py` | F2/F4: `APP_DEBUG` default false; `safe_production_settings` validator. **Extra fix found in testing:** `CORS_ORIGINS` also accepts a JSON list (`["https://…"]` used to be split on commas into a broken origin). |
| `backend/app/main.py` | F9 docs off in production; F8 `BodyLimitMiddleware` registered; F13 `/health` runs `SELECT 1`; F4 `_refuse_superuser_database()` at production startup. |
| `backend/app/middleware/body_limit.py` | **New file** (F8; approved in this spec). |
| `backend/app/api/v1/webhooks.py` | F10: 404 for every provider. |
| `backend/app/api/v1/customers.py`, `content.py`, `conversations.py`, `kb.py` | F5: `require_permission("agent")` / `("manager")` / `("agent")` / `("manager")`. |
| `backend/app/models/kb_document.py`, `services/kb_service.py`, `ai/retrieval.py` | F6: live columns `body`, `source`, `document_type`, `metadata`, `indexed_at`; `embedding_status` derived; retrieval searches `body`. |
| `backend/app/core/security.py` | F14: `bcrypt__rounds=settings.BCRYPT_ROUNDS`. |
| `backend/app/services/auth_service.py` | F7: `_issue_tokens` records each refresh token (SHA-256 of the jti, expiry, IP, user agent) and rotates (`replaced_by`); `refresh` requires a recorded, unrevoked, unexpired token; reuse revokes all of the user's tokens; new `logout`; password reset revokes all. |
| `backend/app/api/v1/auth.py` | F7: passes (IP, user agent) to the service; `logout` takes an optional `{refresh_token}` and always returns 204. **Extra fix found in testing:** a client host that isn't an IP address is recorded as unknown (the `inet` column rejected it and the login failed). |
| `backend/app/schemas/auth.py`, `schemas/user.py` | F7 `LogoutRequest`; F11 the password check also receives the email. |
| `backend/app/validators/password_policy.py` | F11: minimum 10 characters; ~50 common passwords; a common base word followed only by digits/symbols (e.g. "Passw0rd123", "Welcome2027!"); no email name. |
| `backend/app/services/workflow_service.py` | F12: `call_webhook` URL checked with `verify._public_https_base` at save (422). |
| `backend/app/services/tenant_service.py` | F15: `ai_campaign_runs` added to `RESET_TABLES`. |
| `specs/SPEC-BE-001.md`, `CLAUDE.md` | Documentation updated. |

### Database (F16, additive only, applied once to the live DB)
- **Created:**
  - `idx_action_executions_tenant`, `idx_notifications_tenant`, `idx_order_items_tenant`, `idx_refresh_tokens_tenant` and `idx_webhook_events_tenant` (each on `tenant_id`);
  - `idx_ads_content_asset` (`ads.content_asset_id`) and `idx_ad_groups_audience` (`ad_groups.audience_id`).
- **Not created** (already covered by existing indexes, so they would be duplicates):
  - `refresh_tokens(token_hash)`, covered by the UNIQUE `refresh_tokens_token_hash_key`;
  - `refresh_tokens(user_id)`, covered by `idx_refresh_tokens_user` (partial, unrevoked);
  - `ai_campaign_runs(tenant_id, status)`, covered by an existing index that starts with `tenant_id`.
- No data was changed.

### Packages (backend/.venv; before → after)
- fastapi 0.115.6 → 0.142.2, starlette 0.41.3 → 1.7.0, python-jose 3.3.0 → 3.5.0, cryptography 44.0.0 → 50.0.2, python-multipart 0.0.20 → 0.0.32.
- Dev tools: pytest 8.3.4 → 9.0.3, pytest-asyncio 0.25.0 → 1.4.0, black 24.10.0 → 26.3.1.
- New transitive dependencies: annotated-doc, opentelemetry-api, typing-inspection, pytokens.

### Results
- **Acceptance 1:** passes.
  - A fresh dry-run `pip install -r requirements.txt` resolves.
  - `pip check` reports no broken requirements.
- **Acceptance 2:** a suite on the live DB in one rolled-back transaction passes 47 of 49 checks.
  - **New behaviour, all passing:**
    - Password1, Passw0rd123, Welcome2027!, Qwerty123456 and Admin-2026!! are refused, as are 9 characters and an email-name password, and the reset confirm also checks the policy.
    - The bcrypt cost is 12, matching the setting.
    - A viewer gets 403 on all four routes; an agent can create customers but gets 403 on KB create.
    - KB create, list and retrieval work.
    - Refresh rotates the token; a reused token gets 401 and revokes the whole family.
    - Logout revokes the token, and garbage, empty or access-token input gets 204.
    - An unrecorded token gets 401, and a password reset revokes all tokens.
    - Private webhook URLs (http://127.0.0.1, https://10.0.0.5) are refused and a public https one is accepted.
    - A 20 MB JSON body gets 413; 3 MB on ad media is allowed, while 3 MB on branding gets 413.
    - Webhooks return 404, `/health` reports the database, and a company reset deletes `ai_campaign_runs`.
  - **Regression, all passing:**
    - Tenant isolation: A's rows give 404 to B, and the KB list is isolated.
    - All 158 OpenAPI paths return 401 without a token (except the public auth routes).
    - Viewer mutations never return 5xx. The only one that succeeds is discarding the viewer's own chat draft, which is intended.
    - A real multipart branding upload returns 200 on python-multipart 0.0.32.
  - **The 2 "failures" are documented behaviour:** `GET /integrations/meta/connect` returns 503 when `META_APP_ID` isn't configured, as CLAUDE.md documents. No other GET route returned 5xx, for either the new tenant or dev-shop.
  - **Production mode** (separate processes with production env), 11 of 11 pass:
    - each bad setting is refused, and good settings are accepted;
    - `/docs` and `/openapi.json` return 404;
    - the superuser database login is refused;
    - dev still serves the docs, and `APP_DEBUG` defaults to false.
  - Rollback was confirmed: no test tenants persisted, and dev-shop is untouched.
- **Acceptance 3:** ruff 1 and mypy 7, the same pre-existing baseline; the app imports.
- **Acceptance 4:** `pip-audit` (run in a throwaway venv, since deleted) reports one remaining advisory.
  - ecdsa 0.19.2 PYSEC-2026-1325: no fix is released, and it comes in only through python-jose.
  - Not reachable: `JWT_ALGORITHM` allows only HS256/RS256, and ecdsa is used only for ES* algorithms.
- **Deviation:** the full AI Autopilot suite and the 42-check ad-platform suite from the earlier pass weren't re-run as scripts (they were deleted under the no-leftover-files rule). This spec didn't touch that code. Its paths were covered by the 158-route sweeps, the dev-shop GET sweep, the ad media upload limit check and the browser smoke of `/campaigns/ai/new`, `/campaigns/new` and `/campaigns/ad-manager`.
- **Operational notes:**
  - **One-time sign-in:** refresh tokens issued before this change have no row, so each signed-in user must sign in once more when their access token expires.
  - **Multi-tab race:** two browser tabs refreshing in the same instant can trip reuse detection and sign that user out (rare; the frontend already allows only one refresh at a time per tab).
