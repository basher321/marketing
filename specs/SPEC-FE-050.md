# SPEC-FE-050: Organic Marketing dashboard

Status: IMPLEMENTED (code, 2026-10-03; approved by the user). `npx tsc --noEmit` and `next build` are clean (all 9 routes build). **E2E acceptance 1–9 is pending:** the live Postgres DB was unreachable. See "Implementation notes". Backend: SPEC-BE-074…078. Navigation: SPEC-FE-049.

## Routes (all under `app/(app)/marketing/organic/`)
| Route | Page |
|---|---|
| `/marketing/organic` | **Dashboard**: KPI cards (scheduled next 7 days, published 30 days, failed needing attention, engagement 30 days — "—" when null), upcoming queue (next 10), quick actions (Create post · Create with AI · Generate photo · Generate video), connected-accounts strip, recent history (5), scheduler running/stopped indicator |
| `/marketing/organic/create` | **Create**, with tabs **Manual** and **AI/Prompt** |
| `/marketing/organic/content/[id]` | **Content editor**: master + one tab per platform version, preview, schedule panel |
| `/marketing/organic/photo` | **Photo Generation** |
| `/marketing/organic/video` | **Video Generation** |
| `/marketing/organic/calendar` | **Content Calendar** (month/week, tenant timezone) |
| `/marketing/organic/accounts` | **Connected Social Accounts** |
| `/marketing/organic/history` | **Published Content/History** |
| `/marketing/organic/analytics` | **Organic Analytics** |

A sub-navigation tab bar (`.tabs`, as on other pages) links the sections.

## Creation flows
**Manual** (`create?mode=manual`):
1. Write the caption (character counter shows the strictest selected platform's limit), hashtags and CTA, and an optional link.
2. Upload or pick media from the library (`POST /media`, `GET /media`); images and videos, with upload progress.
3. Select platforms/accounts from `GET /social/accounts`. Disconnected or missing-permission accounts show disabled, with the reason.
4. Choose "Create versions": the rules adaptation by default, with an "Adapt with AI" option.
5. The editor opens.

**AI/Prompt** (`create?mode=ai`):
1. Enter the prompt, optional products (product picker), tone and platforms.
2. Pick the media mode: none · use media · generate photo · generate video. Generation options appear inline.
3. Generate. A copy-loading state is shown; the media shows "generating…" with polling (`GET /organic/generations/{id}` every 3 s for photos, 10 s for video).
4. The editor opens with "Needs approval".

**Editor** (`content/[id]`):
- **Master panel:** caption, hashtags, CTA, link, media, and "Re-adapt versions" (only versions not edited by hand).
- **Per-platform tab:**
  - editable fields and media (choose or derive a crop: 1:1, 4:5, 9:16, 1.91:1);
  - warnings and blocking errors;
  - **Regenerate** with checkboxes for caption, hashtags, CTA and title (with an optional instruction); media is always kept;
  - a version history with revert;
  - a **platform preview**: a mock of how the post looks on FB, IG, TikTok and LinkedIn, using `GET /organic/versions/{id}/preview` text (exactly what is sent) and showing the "…more" cut-off.
- **Approval:** AI content shows an **Approve** button (manager+). Schedule and Publish stay disabled until approved, with a tooltip saying why.
- **Schedule panel:**
  - date, time and **timezone** (searchable select from `GET /tenants/locale-options`, defaulting to the company timezone), per platform or "same time for all";
  - **Save draft** · **Schedule** · **Publish now** (with a confirmation);
  - 422 errors from the backend are listed by platform and field.

## Photo / Video Generation pages
- **Form:**
  - prompt, product/service (picker), reference media (upload or library, shown only when the readiness says the provider supports it), aspect ratio, style and target platform (pre-selects the ratio);
  - video also has duration, with the provider's supported durations shown next to it from `GET /organic/generation/providers`.
- **Readiness banner** when no provider is set up: a link to Integrations › AI Models.
- **Job card:**
  - while running: status, elapsed time and Cancel;
  - when done: the preview (`<img>` / `<video controls>` from the signed URL) and the effective settings ("12 s generated; 15 s requested");
  - actions: **Regenerate** · **Edit prompt & regenerate** · **Edit image** (instruction; images only) · **Approve** · **Approve & create post**, which opens the editor with this media.
- **History list** of the user's generations, with lineage ("regenerated from…").

## Scheduler pieces
- **Calendar:**
  - month and week views in the company timezone, with posts as chips by platform and status color;
  - clicking a chip opens a drawer with the preview, status, error, and Reschedule / Cancel / Retry / Open on platform (`external_url`);
  - clicking an empty day opens Create with that date pre-filled.
- **History:**
  - a table of published, failed and cancelled posts, filtered by platform and status, paginated;
  - failed rows show the platform's error and Retry.
- **Accounts:**
  - cards per platform: status, profile, capabilities and limits, last error and a "Test" button;
  - not-connected platforms link to Integrations with the needed permissions listed;
  - the "Use my Meta connection" shortcut (SPEC-BE-075);
  - the TikTok "posts are private until your app is audited" note.

## Analytics
- Range 7d / 30d / 90d.
- Totals cards (null → "—" with a tooltip saying "no data imported yet"), a per-platform table, a daily chart built from the hand-rolled `.chart`/`.bar` markup (no chart library, per `frontend/CLAUDE.md`), and top posts.
- An "Import now" button (manager+) with the throttle message.

## Conventions
- API modules: `lib/api/organic.ts`, `media.ts`, `generation.ts`, `social.ts`; types mirror the backend schemas field for field in `lib/types/…`.
- Server state uses TanStack Query.
- Colors come only from the CSS tokens. Layout works at narrow widths.
- Role-gated buttons are hidden or disabled by role (agent: drafts only; manager+: approve, schedule, publish), and the backend 403 is still handled.
- No client-side simulation: every action calls the backend, and every status shown comes from the backend.

## Acceptance (E2E against the running backend + live DB, dev fakes, `LLM_PROVIDER=fixture`; temporary company deleted afterwards)
1. The dashboard renders KPIs, the queue and accounts from real API data; empty states are correct.
2. Manual: upload image → select FB + IG → versions → IG preview shows "link in bio" → schedule tomorrow 20:00 Asia/Dhaka → the calendar shows it on the right day → the job publishes it (fake) → it appears in History as published with a link.
3. AI: prompt → copy + generated photo (fake) → Approve → Schedule. Before approval, the Schedule button is disabled.
4. Regenerate caption only → the caption changes and the image is unchanged; revert works.
5. Video generation: 15 s request → the job card shows the effective duration → Approve & create post → the editor opens with the video.
6. Failed publish (injected fake error) → shows in History with the error → Retry → published.
7. Reschedule and cancel from the calendar drawer.
8. Analytics renders nulls as "—" and numbers after a fake import.
9. An agent can create drafts but cannot schedule (buttons disabled; a forced call → 403 is shown).
10. `npx tsc --noEmit` is clean.

## Target files
- New pages under `frontend/app/(app)/marketing/organic/**`.
- New components under `frontend/components/organic/**`.
- New `lib/api/{organic,media,generation,social}.ts` and `lib/types/{organic,media,generation,social}.ts`.
- `frontend/CLAUDE.md` (routes).

## Implementation notes (2026-10-03)
- **Files:**
  - pages under `app/(app)/marketing/organic/` (dashboard, create, content/[id], photo, video, calendar, history, accounts, analytics);
  - components under `components/organic/` (shared, media-picker, platform-preview, content-editor, create-form, generation-studio);
  - `lib/api/{organic,media,generation,social}.ts` and `lib/types/{organic,media,generation,social}.ts`.
- **Also changed:**
  - `components/integrations/ai-models.tsx` (video model picker, "Videos" creative kind);
  - `components/chat/plan-card.tsx` (Organic / Paid module labels);
  - `lib/types/{integrations,ai-campaigns,orchestrator}.ts`.
- **Roles (deviation):** the client has no current-user role (neither the token nor any endpoint carries it). Following the existing frontend practice in `frontend/CLAUDE.md`, buttons show to every role, the backend enforces the rule, and a 403 shows "Your role can't do this; ask a manager or the owner." Criterion 9 becomes "agent sees that message on Schedule".
- **Calendar "+" on a day:** opens Create without pre-filling that date (scheduling happens in the editor). Small deviation.
- **Polling:** content with pending media every 5 s; photo jobs every 3 s; video jobs every 10 s; the dashboard summary every 60 s.
- **Pending (needs the running backend + live DB):** acceptance 1–9.
