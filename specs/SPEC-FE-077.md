# SPEC-FE-077: Branding page (Super admin app branding / everyone's profile) and Super admin integrations

Status: IMPLEMENTED (2026-10-22). Browser E2E: profile save, app name in the sidebar, Super admin integrations health and Twilio numbers on /admin. Backend SPEC-BE-113, SPEC-BE-108 FR1, SPEC-BE-112 FR7.

## Requirements

- **`/branding`** for everyone:
  - **My profile:** name, phone, avatar upload with preview and remove.
  - **Company branding** (owner/admin only, the existing SPEC-FE-048 logo/banner/head photo and brand voice
    controls moved here from Settings; Settings links to it).
  - **App branding** — shown only when `GET /platform/me` says `super_admin`: app name, tagline, logo (light /
    dark), favicon with previews.
- The app name and logo from `GET /platform/branding` are used in the sidebar, the login/sign-up shell, the
  browser title and the favicon, loaded once and cached (falls back to the built-in PilotSonic logo).
- **`/admin` → Integrations** section (Super admin): health per provider (configured, tested, companies
  connected / with errors), an errors log with filters, the new **Twilio** group (account sid, auth token,
  test, numbers list, assign a number to a company in Companies) and **WhatsApp app** group (config id, verify
  token, the webhook URL to copy).
- Regular users never see App branding, `/admin`, developer app settings or token fields (the backend refuses
  them too).

## Files

New `app/(app)/branding/page.tsx`, `components/branding/*`, `lib/api/platform.ts`, `lib/api/users.ts`,
`lib/types/platform.ts`, `app/(app)/admin/page.tsx`, `app/(app)/settings/page.tsx`,
`components/shell/sidebar.tsx`, `components/auth/auth-shell.tsx`, `app/layout.tsx`.
