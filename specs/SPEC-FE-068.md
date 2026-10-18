# SPEC-FE-068: Super admin screen; companies only connect; Skip a job

Status: IMPLEMENTED (2026-10-10). Backend: SPEC-BE-101, SPEC-BE-102. AC5 passes (`tsc`, `next build`); the pages serve
on the running app. **The browser E2E (AC1–AC4) is still pending**: no browser tool was available in the build session.

## Requirements

- **FR1 (Super admin screen, `/admin`):**
  - **Access:** the sidebar shows **Super admin** only when `GET /platform/me` says so. Anyone else sees "Not found".
  - **Sections:**
    - **AI providers:** the SPEC-FE AI Models editor (keys, models, order, test), pointed at `/platform/ai-models`;
    - **SocialAPI master key** (save / test / remove);
    - **Zernio key**;
    - **Sign-in apps:** Meta (app id, secret, login config ids), TikTok (client key / secret) and LinkedIn (client id /
      secret).
  - **Keys:** shown masked, and saving a field never needs the old secret. A value coming from `backend/.env` shows as
    "from server settings".
- **FR2 (company AI Models):**
  - Integrations › AI Models shows "AI is provided by PilotSonic": each provider with its model, its place in the order,
    and ready / not set up.
  - No key fields, Save & test, Delete or MCP tools.
  - The creative order and the slideshow sound settings stay.
- **FR3 (SocialAPI):** the key card (Integrations, and Organic › SocialAPI) is replaced by "Provided by PilotSonic" (and
  "not set up yet" until the Super admin adds the key). The Connect buttons stay.
- **FR4 (Integrations):**
  - **Facebook, Instagram, TikTok, LinkedIn and the ad platforms:** no token form. They show:
    - "Connect with …" (the sign-in app) where it exists;
    - otherwise links to "Connect through Zernio" (ads) / "Connect through SocialAPI" (pages);
    - an existing connection as Connected, with Test and Disconnect.
  - **Store, CRM and email cards:** unchanged.
- **FR5 (Skip):** on the job board and the plan card, a queued, waiting-for-approval, needs-input or failed job has
  **Skip** (with a confirm naming how many dependent jobs go too).

## Acceptance criteria (browser E2E on the running app)

- **AC1:** the Super admin signs in, sees "Super admin" and the screen, and saves and tests a key. A company owner has no
  such link, and `/admin` shows Not found.
- **AC2:** company AI Models shows PilotSonic's providers and no key inputs.
- **AC3:** Integrations shows Connect options, not token forms, for social and ad platforms; an existing Facebook
  connection shows Connected.
- **AC4:** Skip a queued job → it shows Skipped, and the chat shows the line.
- **AC5:** `tsc` and `next build` pass.

## Files

- **Changed:** `components/integrations/ai-models.tsx` (an `admin` mode), the Integrations page / provider cards,
  `components/socialapi/publishing.tsx` (key card), `components/shell/sidebar.tsx` (link), `components/chat/job-board.tsx`,
  `components/chat/plan-card.tsx`, and `lib/api` / `lib/types` for ai-models, integrations, socialapi and orchestrator.
- **New (approved with the build):** `app/(app)/admin/page.tsx`, `lib/api/platform.ts`, `lib/types/platform.ts`.
