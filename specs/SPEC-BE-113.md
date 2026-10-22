# SPEC-BE-113: App branding (Super admin), my profile (everyone), integration health (Super admin)

Status: IMPLEMENTED (2026-10-22). 26/26 rolled-back checks. UI in SPEC-FE-077.

## Requirements

- **FR1 App branding** — `platform_settings` group `app_branding` = `{app_name, tagline?, logo (data URL),
  logo_dark?, favicon?}`. Images: PNG, JPEG or WebP (no SVG), ≤ 1 MB, checked by magic bytes, as
  SPEC-BE-051 does for company branding.
  - `GET /platform/branding` — **public, no auth** → `{app_name, tagline, logo_url, logo_dark_url,
    favicon_url}` with defaults "PilotSonic" + the built-in logo. Cached 30 s (platform_service cache).
  - `PUT /platform/branding` (Super admin) for text, `PUT/DELETE /platform/branding/{logo|logo_dark|favicon}`
    for images. Audited in the Super admin's workspace.
  - Company branding (`/tenants/me/branding`, SPEC-BE-051) is unchanged: that is the company's own logo for
    its posts and pages, not the app's.
- **FR2 My profile** — `GET /users/me`, `PATCH /users/me {first_name, last_name, phone}`, `PUT/DELETE
  /users/me/avatar` (same image rules, stored as a data URL in `users.avatar_url`). Email, role and status
  can't be changed here. Every role, Super admin included. Audited.
- **FR3 Integration health** (Super admin) — `GET /platform/integrations/health` → per provider (Meta,
  TikTok, LinkedIn, SocialAPI, Zernio, Twilio, WhatsApp): configured?, last test result, number of companies
  connected / with errors; `GET /platform/integrations/errors?provider&cursor` → recent failures from
  `integrations.last_error`, failed `webhook_events` (invalid signature, processing error) and failed
  `sms_messages`, newest first, with company name. Never shows a secret or token.
- **FR4 Regular users** never get these: `/platform/*` stays 404 for non-Super-admins
  (`require_super_admin`), except the public `GET /platform/branding`.

## Acceptance criteria (live DB, rolled back)

1. Without settings, branding returns the defaults; after PUT, the new name/logo (no auth needed to read).
2. An SVG or 2 MB logo is 422; a non-Super-admin PUT is 404.
3. `/users/me` PATCH changes only the caller; email in the body is ignored (extra=forbid → 422).
4. Health/errors list a seeded failure for the right company and contain no secrets.

## Files

`api/v1/platform.py`, `services/platform_service.py`, `schemas/platform.py`, `api/v1/users.py`,
`services/user_service.py`, `schemas/user.py`.
