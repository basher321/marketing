# SPEC-BE-001 — Backend Python Dependency Manifest
Target File: backend/requirements.txt
Layer: Foundation - Environment
Status: Approved

## Scope
In: web framework, ASGI server, async DB driver, ORM, migrations, auth, crypto, TOTP, in-process scheduler, HTTP client, rate limiting, logging, testing, static analysis.
Out:  message brokers (Celery/Redis/Kafka), frontend tooling, LLM SDKs, OS packages.

## Functional Requirements
FR-001 List every runtime dependency required by any backend module
FR-002 Every dependency pinned with ==
FR-003 Support Python 3.11 and 3.12
FR-004 Group dev/test dependencies with comments
FR-005 Install cleanly via single pip install -r requirements.txt
FR-006 Include async PostgreSQL driver
FR-007 Include sync PostgreSQL driver for Alembic
FR-008 Include in-process job scheduler

## Non-Functional Requirements
Security: bcrypt hashing, JWT (cryptography backend), TOTP, symmetric encryption for credentials at rest, rate limiting, email validation, Bandit scanner, zero known CVEs at pinned versions.
QA: pytest + pytest-asyncio, pytest-cov, faker, ruff, black, mypy, httpx.
Performance: asyncpg as primary driver, uvicorn production-capable.
Compliance: structlog for audit formatting, zero unpinned/range versions.

## Acceptance Criteria
AC-001 File exists at backend/requirements.txt
AC-002 Every line blank, comment, or pinned dependency
AC-003 Grouped by role with section headers
AC-004 Installs clean on 3.11 and 3.12
AC-005 pip check - no conflicts
AC-006 Every FR/NFR mapped to a package

## Amendment (SPEC-BE-071, 2026-10-02)
- **Before:** the file broke FR-005/AC-005. Two blocks pinned the same packages at different versions, so `pip install -r` failed with ResolutionImpossible.
- **Now:** one deduplicated list, pinned to the installed and verified versions. Highlights:
  - fastapi 0.142.2 (starlette 1.7.0), python-jose 3.5.0, cryptography 50.0.2 and python-multipart 0.0.32, all security upgrades;
  - pytest 9.0.3, pytest-asyncio 1.4.0, black 26.3.1.
- **Removed:** celery, redis and pyjwt (unused, and out of scope per this spec).
- **Verified:**
  - a fresh dry-run resolve passes, and `pip check` is clean;
  - `pip-audit` finds one advisory: ecdsa PYSEC-2026-1325, a python-jose dependency with no fixed release. It is unreachable here because `JWT_ALGORITHM` allows only HS256/RS256, so the "zero known CVEs" requirement holds with that one exception.

## Amendment (SPEC-BE-072, 2026-10-02)
- **Added `tzdata==2026.4`:** it was installed but not listed. Without it, a fresh Windows install has no timezone database, so every timezone would be refused.
- **Added `babel==2.18.0`:** CLDR data for the worldwide country, currency and language lists and for money formatting.

## Amendment (SPEC-BE-074, 2026-10-03)
- **Added `pillow==12.0.0`:** crops or pads media library images to each platform's ratio (1:1, 4:5, 9:16, 1.91:1), and fits Sora reference images to the video size. Approved by the user (decision D3). Videos are still never transcoded (no ffmpeg).

## Amendment (SPEC-BE-093, 2026-10-09)

Added `imageio-ffmpeg==0.6.0`, under "Video". It ships a static ffmpeg binary (7.1, with libx264) as a
platform wheel, so no system ffmpeg is needed. Command Chat uses it to turn OpenAI images into a slideshow
MP4, because OpenAI's Sora video API shut down on 2026-09-24.
