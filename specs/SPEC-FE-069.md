# SPEC-FE-069: Super admin — Companies section (per-company key access)

Status: IMPLEMENTED (2026-10-11), backend SPEC-BE-103. `npx tsc --noEmit` is clean. **The browser E2E is pending**: the
Chrome extension wasn't connected, and signing in needs the Super admin's password.

## Requirements

- On `/admin`, under AI Models, a **Companies** section lists every company (25 per page, with Previous/Next) and has a
  search by name or slug.
- Each row shows:
  - the name, slug and status (shown when it isn't active);
  - one switch per group (AI, SocialAPI, Zernio, Meta app, TikTok app, LinkedIn app), using the existing `.cc-switch`;
  - "Shared services": whether the company has a SocialAPI brand and a Zernio profile, plus its last SocialAPI error.
- Switching **off** asks for confirmation ("They lose it right away"); switching on saves at once. The response updates
  the row in the query cache. A failed save shows its message.
- Companies see the backend's 403 text (e.g. "PilotSonic hasn't enabled SocialAPI for your company. Contact PilotSonic
  support.") wherever the error already shows. No page-specific change.

## Acceptance criteria (browser E2E on the running app) — pending

1. As the Super admin, `/admin` shows Companies with all switches on.
2. Searching a slug narrows the list.
3. Switching SocialAPI off for a company (confirm) persists after a reload. That company's "Accounts via SocialAPI"
   shows the blocked message, and switching it back on restores the page.

## Files

`app/(app)/admin/page.tsx`, `lib/api/platform.ts`, `lib/types/platform.ts`.
