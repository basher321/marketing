# SPEC-BE-003 — Application Configuration Module

## 1. Spec Metadata
Spec ID: SPEC-BE-003
Title: Application Configuration Module
Target File: backend/app/config.py
Layer: Foundation - Environment
Version: 1.0
Status: Approved
Depends On: SPEC-BE-001, SPEC-BE-002
Blocks: app/main.py, app/db/session.py, app/core/security.py, all modules requiring config

## 2. Purpose
Load and validate all environment variables defined in SPEC-BE-002 into a single typed, cached Settings object using pydantic-settings, so the rest of the application never reads os.environ directly.

## 3. Scope
In Scope: typed Settings class covering every variable in backend/.env.example, field validation, secret masking, cached singleton accessor.
Out of Scope: reading secrets from a vault/KMS (future spec), per-tenant runtime config (stored in DB, not env).

## 4. Functional Requirements
FR-001: Load all environment variables defined in SPEC-BE-002 into a single typed Settings class using pydantic-settings BaseSettings.
FR-002: Provide correct Python types for each variable (str, int, bool, list, SecretStr where sensitive).
FR-003: Validate APP_ENV is one of: development, staging, production.
FR-004: Validate JWT_ALGORITHM is one of: HS256, RS256.
FR-005: Parse CORS_ORIGINS from comma-separated string into list[str].
FR-006: Provide a cached singleton accessor function get_settings() using functools.lru_cache.
FR-007: Auto-load .env file via model_config, no manual dotenv calls elsewhere.
FR-008: Fail fast with a clear validation error at startup if a required variable is missing or malformed.

## 5. Non-Functional Requirements
Security:
NFR-SEC-001: SECRET_KEY, ENCRYPTION_KEY, LLM_API_KEY, SMTP_PASSWORD, STORAGE_SECRET_KEY, DATABASE_URL, DATABASE_URL_SYNC typed as pydantic SecretStr.
NFR-SEC-002: Settings object must never be logged in full; only non-secret fields are loggable.
NFR-SEC-003: SECRET_KEY, ENCRYPTION_KEY, DATABASE_URL have no default value — must be required, no insecure fallback.
NFR-SEC-004: BCRYPT_ROUNDS validated >= 10.
QA:
NFR-QA-001: Settings instantiable in tests via fixture that overrides env vars.
NFR-QA-002: mypy passes with zero errors on this file.
NFR-QA-003: Unit test verifies missing required var raises ValidationError.
NFR-QA-004: Unit test verifies CORS_ORIGINS parses into a list.
Performance:
NFR-PERF-001: Settings loaded once per process via lru_cache, not re-parsed per request.
Compliance:
NFR-COMP-001: Every field has Field(..., description=...).

## 6. Dependencies & Inputs
Requires: pydantic-settings (from SPEC-BE-001), backend/.env.example variable list (from SPEC-BE-002).
Consumed By: app/main.py, app/db/session.py, app/core/security.py, app/core/tenant_context.py, all future modules needing config.

## 7. Acceptance Criteria & Verification
AC-001: File exists at backend/app/config.py.
AC-002: Settings class inherits from pydantic_settings.BaseSettings.
AC-003: get_settings() returns a cached singleton (same object on repeated calls).
AC-004: Missing required env var raises pydantic ValidationError at instantiation.
AC-005: CORS_ORIGINS correctly parsed to list[str].
AC-006: mypy passes with zero errors.
AC-007: All secret fields are SecretStr type.
Test Cases:
TC-001: Instantiate Settings with valid .env -> success.
TC-002: Missing SECRET_KEY -> ValidationError.
TC-003: Invalid APP_ENV value -> ValidationError.
TC-004: CORS_ORIGINS="a,b,c" -> ["a","b","c"].
TC-005: get_settings() called twice -> same object (identity check).

## 8. Traceability
Security built into every phase -> NFR-SEC-001 to NFR-SEC-004
QA built into every phase -> NFR-QA-001 to NFR-QA-004
Multi-tenant SaaS config foundation -> FR-001, Consumed By list
No insecure defaults -> NFR-SEC-003

## 9. Implementation Plan
Step 1: Create backend/app/__init__.py if not present (empty file).
Step 2: Create backend/app/config.py.
Step 3: Define Settings(BaseSettings) with fields grouped by section matching .env.example order (App, Security/JWT, Database, CORS, Rate Limiting, Multi-Tenant, LLM/AI, Email/SMTP, File Storage, Ad Caps, Logging).
Step 4: Add field_validator for APP_ENV, JWT_ALGORITHM, CORS_ORIGINS parsing, BCRYPT_ROUNDS minimum.
Step 5: Set model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="forbid").
Step 6: Add get_settings() with @lru_cache decorator.
Step 7: Create backend/tests/test_config.py covering TC-001 through TC-005.
Step 8: Run mypy and pytest against this file.
Risks: extra="forbid" breaks if .env has stray vars (mitigate: keep .env.example authoritative); SecretStr requires .get_secret_value() at every use site (mitigate: document in this spec for downstream specs to reference).

## 10. Review Checklist
[x] All 8 FRs implemented
[x] All secret fields are SecretStr
[x] SECRET_KEY, ENCRYPTION_KEY, DATABASE_URL have no default
[x] get_settings() is cached singleton
[x] mypy clean on this file
[x] pytest passes all 5 test cases
[x] CORS_ORIGINS parses correctly
[x] Every field has a description

## 11. Execution Log

Date: 2026-09-21

Verified in an isolated throwaway venv built from the SPEC-BE-001 pins
(Python 3.12.7; no `python3.11` binary exists in this environment), not the
project's real `.venv`. `backend/.env` was created by copying
`backend/.env.example` (gitignored, dev-only) so the `get_settings()`
identity check in Step 3.4 had a real `.env` to read.

Two real defects were found and fixed during verification, not just declared
passing:

1. `mypy app/config.py` initially failed with 4 `[call-arg]` errors on
   `Settings()` inside `get_settings()` — pydantic's `dataclass_transform`
   metaclass hint makes mypy treat `SECRET_KEY`, `ENCRYPTION_KEY`,
   `DATABASE_URL`, `DATABASE_URL_SYNC` (no-default fields) as required
   constructor keyword arguments, when in fact `BaseSettings` supplies them
   from the env/dotenv source at runtime, not from the call site. Fixed with
   a narrowly-scoped `# type: ignore[call-arg]` on the `return Settings()`
   line, with a comment explaining why.
2. `pytest tests/test_config.py -v` initially failed TC-004 and TC-005 —
   pydantic-settings' env/dotenv source tries to JSON-decode any list-typed
   field's raw string *before* field validators ever run, so a plain
   `CORS_ORIGINS=a,b,c` (or the default `http://localhost:5173`) blew up
   with `json.decoder.JSONDecodeError` ahead of the custom `mode="before"`
   validator. Fixed by annotating the field
   `Annotated[list[str], NoDecode]` (from `pydantic_settings`) so the raw
   string reaches `parse_cors_origins` unmodified.

### Command outputs

```
$ mypy app/config.py
Success: no issues found in 1 source file
```

```
$ pytest tests/test_config.py -v
collected 5 items

tests/test_config.py::test_tc001_valid_settings_instantiates PASSED      [ 20%]
tests/test_config.py::test_tc002_missing_secret_key_raises PASSED        [ 40%]
tests/test_config.py::test_tc003_invalid_app_env_raises PASSED           [ 60%]
tests/test_config.py::test_tc004_cors_origins_parsed_to_list PASSED      [ 80%]
tests/test_config.py::test_tc005_get_settings_is_cached_singleton PASSED [100%]

5 passed in 0.34s
```

```
$ python -c "from app.config import get_settings; s1=get_settings(); s2=get_settings(); print('cached:', s1 is s2)"
cached: True
```

### Checklist result: PASS (8/8)

| Item | Result |
|---|---|
| All 8 FRs implemented | PASS |
| All secret fields are SecretStr | PASS |
| SECRET_KEY, ENCRYPTION_KEY, DATABASE_URL have no default | PASS (DATABASE_URL_SYNC also has no default, by extension of the same rationale) |
| get_settings() is cached singleton | PASS |
| mypy clean on this file | PASS |
| pytest passes all 5 test cases | PASS |
| CORS_ORIGINS parses correctly | PASS |
| Every field has a description | PASS |

## Amendment (2026-09-29, SPEC-BE-039 login protection)
Rate Limiting section:
- `RATE_LIMIT_LOGIN_ATTEMPTS` now counts only FAILED logins per client IP (default 20, was 5
  of any attempt), and `RATE_LIMIT_LOGIN_WINDOW_MINUTES` defaults to 5 (was 15).
- New `LOGIN_MAX_FAILED_ATTEMPTS` (default 5): consecutive wrong passwords on one account
  before a short, escalating lock.
- New `LOGIN_LOCKOUT_MAX_MINUTES` (default 15): cap for that lock (1, 2, 4, 8 ... minutes).
- New section **Frontend** (SPEC-BE-040): `FRONTEND_BASE_URL` (default `http://localhost:3000`),
  the public web-app URL used to build links in emails (password reset).

## Amendment (2026-10-01, SPEC-BE-054 Meta connect + publishing)
New section **Meta**:
- `META_APP_ID` (default `""`): the Meta developer app ID.
- `META_APP_SECRET` (SecretStr, default `""`): used for the OAuth code exchange and `appsecret_proof`. Never logged.
- `META_LOGIN_CONFIG_ID` (default `""`): the Facebook Login for Business configuration ID.
- `META_GRAPH_VERSION` (default `v25.0`): the Graph/Marketing API version. v26 breaking changes reportedly apply to all versions from 2026-10-27; recheck before go-live.
- `SHOPIFY_API_VERSION` (default `2026-07`): Shopify Admin API version for shipping sync (SPEC-BE-058).
- `GOOGLE_ADS_API_VERSION` (default `v25`, added 2026-10-02 by SPEC-BE-064): Google Ads REST API version, used for Google and YouTube ads. Google releases a major version roughly quarterly, and each one sunsets about 12 months later; recheck before go-live.
- `LINKEDIN_API_VERSION` (default `202609`, added 2026-10-02 by SPEC-BE-065): the `Linkedin-Version` header (YYYYMM). Versions retire after about a year.
- `META_FAKE_TRANSPORT` (default `false`), `META_FAKE_CURRENCY` (default `BDT`): dev-only fixtures for Meta/Shopify/WooCommerce (2026-10-01).
- `LLM_FIXTURE_FILE` (default empty): with `LLM_PROVIDER=fixture`, a JSON list of `{match, response}`; dev only.
- A model validator refuses `META_FAKE_TRANSPORT=true` or `LLM_PROVIDER=fixture` when `APP_ENV=production`.

All four have safe empty defaults, so the app boots without them. If the app ID, secret or config ID is empty, "Connect with Facebook" returns 503.

## Amendment (SPEC-BE-074, 2026-10-03): media storage
- `STORAGE_PROVIDER` default changes from `s3` to `local` (`backend/.env` updated to match). The existing `STORAGE_BUCKET`, `STORAGE_ACCESS_KEY` and `STORAGE_SECRET_KEY` are reused for S3 instead of new `S3_*` names.
- New: `STORAGE_ENDPOINT` (S3-compatible URL, required for s3), `STORAGE_REGION` (default `us-east-1`), `MEDIA_ROOT` (default `media`, relative to `backend/`), `MEDIA_URL_TTL_HOURS` (default 24), `PUBLIC_BASE_URL` (default `http://localhost:8000`; the base of signed media URLs).
- All have safe defaults; the app boots without them. Choosing `s3` without an endpoint or with placeholder keys makes media calls fail with a clear message instead of failing at startup.

## Amendment (SPEC-BE-080, 2026-10-03): social sign-in
New section **Social sign-in**:
- `META_SOCIAL_LOGIN_CONFIG_ID` (default `""`): optional Facebook Login for Business configuration (user access token) for the Page/Instagram sign-in. When empty, the dialog asks for the scopes listed in SPEC-BE-080. The Meta app ID and secret above are reused.
- `TIKTOK_CLIENT_KEY` (default `""`), `TIKTOK_CLIENT_SECRET` (SecretStr, default `""`): TikTok Login Kit.
- `LINKEDIN_CLIENT_ID` (default `""`), `LINKEDIN_CLIENT_SECRET` (SecretStr, default `""`): LinkedIn 3-legged OAuth.
- All have empty defaults, and the app boots without them. A platform with no credentials answers its connect call with 503. Pasted tokens keep working. Secrets are never logged.

## Amendment (SPEC-BE-084, 2026-10-08): Zernio paid ads
New section **Zernio paid ads**:
- `ZERNIO_API_KEY` (SecretStr, default `""`): the one server-wide Zernio key used for every company. While it is empty, every `/zernio/*` route answers 503 and the app still boots. It is never logged or returned.
- `ZERNIO_BASE_URL` (default `https://zernio.com/api/v1`).

## Amendment (SPEC-BE-087, 2026-10-09): embeddings for AI reply retrieval
New section **Embeddings for AI reply retrieval** (one platform key for every company):
- `EMBEDDINGS_PROVIDER` (`Literal["none", "openai", "gemini"]`, default `none`). With `none` or an empty key, retrieval is the full-text search only, and the app always boots.
- `EMBEDDINGS_API_KEY` (SecretStr, default `""`). It is never logged or returned.
- `EMBEDDINGS_MODEL` (default `""` = `text-embedding-3-small` / `gemini-embedding-001`).
- `EMBEDDINGS_DIMENSIONS` (int, default 768, 64–3072).
- (Same day, any-key amendment) `EMBEDDINGS_PROVIDER` is now `Literal["auto", "none", "openai", "gemini", "voyage", "mistral", "cohere", "openai_compatible"]`, default `auto` (the key is recognised by its prefix; an empty key tries `LLM_API_KEY`; Claude/Groq keys mean off). New `EMBEDDINGS_BASE_URL` (default `""`, `openai_compatible` only).
- (Same day) `EMBEDDINGS_MIN_SIMILARITY` (float 0–1, default 0.70: measured for gemini-embedding-001, model-specific).

## Amendment (SPEC-BE-088, 2026-10-09): local Ollama for AI Models
- `OLLAMA_BASE_URL` (default `http://localhost:11434/v1`): Ollama's OpenAI-compatible API on this server. No key is needed.

## Amendment (2026-10-10, SPEC-BE-101): Super admin keys

- **AI keys:** the software's AI keys, the SocialAPI master key, the Zernio key and the Meta / TikTok / LinkedIn
  sign-in apps are managed on the Super admin screen (`platform_settings`). The `.env` values (`ZERNIO_API_KEY`,
  `META_*`, `TIKTOK_CLIENT_*`, `LINKEDIN_CLIENT_*`) remain as the fallback when the screen has no value. `LLM_PROVIDER`
  / `LLM_API_KEY` are the last fallback after the software's AI chain.
- **The production check** no longer refuses `LLM_PROVIDER=mock`, because the keys don't come from `.env` any more.
  `LLM_PROVIDER=fixture` and `META_FAKE_TRANSPORT` are still refused.
