# SPEC-BE-002 — Environment Variable Template
Target File: backend/.env.example
Layer: Foundation - Environment
Status: Approved
Depends On: SPEC-BE-001

## Scope
In: app config, JWT/security, database, CORS, rate limiting, multi-tenant defaults, LLM/AI, email/SMTP, file storage, ad/marketing spend caps, logging.
Out: any real credential or production value.

## Functional Requirements
FR-001 Every variable has a placeholder value or safe default, no real secrets
FR-002 Variables grouped under comment headers by domain
FR-003 No variable hardcodes a production value
FR-004 Every secret-bearing variable commented as must-rotate-per-environment
FR-005 Aligns with SPEC-BE-001 packages (JWT via python-jose, DB via asyncpg/psycopg2, bcrypt, APScheduler)

## Non-Functional Requirements
Security: no plaintext production secret ever committed; encryption key placeholder present for credentials-at-rest; bcrypt cost factor configurable.
QA: file must be loadable by pydantic-settings without error when copied to .env with dummy values.
Compliance: every var documented with one-line comment explaining purpose.

## Acceptance Criteria
AC-001 File exists at backend/.env.example
AC-002 No blank values without placeholder comment
AC-003 No line contains a real credential
AC-004 Every security/QA package from SPEC-BE-001 has a corresponding config entry

## Amendment (2026-10-01, SPEC-BE-054)
Add a `# --- Meta ---` group: `META_APP_ID=`, `META_APP_SECRET=` (secret, must rotate per environment), `META_LOGIN_CONFIG_ID=`, `META_GRAPH_VERSION=v25.0`. These are placeholders only; real values come from the Meta app dashboard. (There is still no `.env.example` file in the repo; this records the template entries.)

Add (2026-10-02, SPEC-BE-064/065): `GOOGLE_ADS_API_VERSION=v25`, `LINKEDIN_API_VERSION=202609`.

Add (2026-10-01): `SHOPIFY_API_VERSION=2026-07`, and a `# --- Dev-only fakes ---` group with `META_FAKE_TRANSPORT=false`, `META_FAKE_CURRENCY=BDT`, `LLM_FIXTURE_FILE=` (`LLM_PROVIDER` also accepts `fixture`, dev only).

Add (2026-10-08, SPEC-BE-084): a `# Zernio paid ads` section before `# Ad/Marketing Caps`, with `ZERNIO_API_KEY=` (empty; the operator pastes the server-wide key) and `ZERNIO_BASE_URL=https://zernio.com/api/v1`.

Add (2026-10-03, SPEC-BE-074): under `# File Storage`, `STORAGE_PROVIDER=local` (was `s3`; s3 with the placeholder keys can't work), `STORAGE_ENDPOINT=`, `STORAGE_REGION=us-east-1`, `MEDIA_ROOT=media`, `MEDIA_URL_TTL_HOURS=24`, `PUBLIC_BASE_URL=http://localhost:8000` (Instagram needs this to be a public https address, e.g. a tunnel, or S3 storage).
