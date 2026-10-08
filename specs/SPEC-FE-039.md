# SPEC-FE-039: Meta connect + Ads Manager-style campaign builder (UI)

Status: IMPLEMENTED, NOT YET VERIFIED ON THE LIVE DB (2026-10-01). The plan was approved as recommended (all 9 decisions). Done: ruff/mypy at baseline, the app imports, `next build` passes, and the logic was checked in-process with `httpx.MockTransport` (no DB). Still open: the additive DDL and the rolled-back live-Postgres acceptance run, both blocked by the session's permission rules. The user must run the DDL, then re-run verification. Backend: SPEC-BE-054 (connect/publish) and SPEC-BE-055 (builder). This is the companion spec SPEC-BE-054 asked for, and it also replaces the simplified wizard (`components/campaigns/wizard.tsx`). Follows `frontend/CLAUDE.md`: TanStack Query, `apiFetch`, CSS variable tokens only, and no chart or UI library.

Implementation notes: `/campaigns` is now the campaign list. A legacy wizard draft still opens at `/campaigns?draft=<id>`. Dev-only `META_FAKE_TRANSPORT=true` (new `integrations/dev_fakes.py`, refused in production) answers Meta, Shopify and WooCommerce calls from fixtures, for E2E.

## Purpose
1. **Connect Meta** on the Integrations page. "Connect with Facebook" opens Facebook Login for Business, which returns to a `/integrations/meta/callback` page. There the user picks the ad account, Page, Instagram account and pixel, and the card shows connected. The paste-a-token form stays as "Advanced".
2. **Campaign builder** at `/campaigns/new` and `/campaigns/{id}/edit`, laid out like Meta Ads Manager:
   - a left **tree** (Campaign → Ad sets → Ads, with add, duplicate and delete);
   - a right **editor** for the selected node;
   - a sticky footer: Save draft · Validate · Preview · Publish ▾ (Publish now / Publish paused / Schedule).

## Screens
Each field is shown only when the objective or category allows it. This is driven by `GET /meta/objectives` and never hard-coded a second time.
- **Objective picker** (first step, a modal like Ads Manager's): six tiles (Awareness, Traffic, Engagement, Leads, App Promotion, Sales) with Meta's one-line descriptions. Unavailable tiles are disabled with the backend's reason.
- **Campaign:**
  - Name.
  - Special ad categories (multi-select plus country), with a warning about restricted targeting.
  - Buying type: Auction. Reservation is disabled, with its reason.
  - Advantage+ campaign budget toggle → daily or lifetime amount, plus bid strategy (plus bid cap, cost cap or minimum ROAS when chosen).
  - Spend limit.
- **Ad set:**
  - Name, conversion location (per objective), performance goal, pixel/dataset and conversion event.
  - Budget and schedule (when not using a campaign budget), with start and end date-time in the tenant timezone.
  - Audience:
    - Load a saved audience.
    - Locations search: country, region, city plus radius, or zip, via `/meta/targeting/search`.
    - Age range, gender and languages.
    - Detailed targeting search: interests, behaviors, demographics.
    - Custom and lookalike audiences, include or exclude.
    - Advantage+ audience toggle.
  - Estimated daily reach from `/meta/reach-estimate`, or "estimate unavailable".
  - Placements: Advantage+, or manual (platform checkboxes, then positions per platform, then devices).
- **Ad:**
  - Name and identity (Page and Instagram account, from the connection).
  - Format: single image, single video, or carousel (2–10 cards).
  - Media uploader: drag and drop → `/meta/media`, with progress and the video processing state.
  - Primary text, headline and description, with character counters at Meta's recommended lengths (125 / 40 / 30).
  - CTA select.
  - Destination: website URL, app store, or instant form picker.
  - URL parameters, with a "Build UTM" helper.
  - "Use AI copy" pulls in a SPEC-BE-046 creative variant.
- **Preview:** a right-side panel with a format switcher (Facebook feed, Instagram feed, Stories, Reels…). It renders Meta's `iframe_html` in a sandboxed iframe limited to Meta's preview domain.
- **Validation:** inline errors from `missing` and `/validate`:
  - Each `{level, id, field}` puts a red dot on the tree node and the message under the field.
  - Meta errors show their class: permission, auth, missing asset, unsupported, or rate limit.
- **Publish result:**
  - A status badge per node from Meta's `effective_status`: Active, In review, Scheduled, Paused, or Disapproved plus its reason.
  - An "Open in Ads Manager" link and pause/resume toggles per node.
  - A pending-approval result shows "Waiting for owner approval", with a link to the approvals panel.
- **Campaign list** (`/campaigns`): status (from `effective_status`), budget, real spend and results (SPEC-BE-056), last sync, and Sync now.

## Rules
- The browser never talks to Meta except through Meta's OAuth dialog and the preview iframe. Every create and update goes through our backend.
- An unsaved-changes guard, and draft autosave every 10 s while editing (PATCH with only the changed fields).
- Money is entered in major units, with the ad account currency shown. Offset-1 currencies have no decimals.
- The tree is keyboard-navigable, and every input has a label.

## Acceptance criteria
Run end to end in headless Edge against the running backend and the live Postgres. Meta calls are answered by fixtures (see the open decision).
1. **Meta-A:** the objective → campaign → ad set → ad navigation works for all six objectives, and fields are shown or hidden per objective.
2. **Meta-B:** every field in the screens list saves and reloads.
3. **Meta-C:** Save draft, Publish paused, Publish now, Schedule, pause and resume each make the backend calls and show the right badges.
4. Validation and preview render, and each Meta error class shows its message.
5. `npx tsc --noEmit` passes, and screenshots are checked against Ads Manager's layout conventions and the mockup's tokens.

## Open decision
- **E2E without a real Meta app.**
  - *Recommend:* a dev-only backend switch, `META_FAKE_TRANSPORT=true`, refused when `ENVIRONMENT=production`. It answers Meta calls from fixtures, so the UI can be tested end to end.
  - *Alternative:* wait for the Meta developer app and a sandbox ad account, and test live.

## Target files
Existing: `app/(app)/campaigns/page.tsx`, `app/(app)/integrations/page.tsx`, `components/campaigns/wizard.tsx` (replaced by the builder), `components/campaigns/creative-variants.tsx`, `components/integrations/connect-panel.tsx`, `components/integrations/integrations-grid.tsx`, `lib/api/campaigns.ts`, `lib/api/integrations.ts`, `lib/types/campaigns.ts`, `lib/types/integrations.ts`.

**New files (need approval):**
- Pages: `app/(app)/campaigns/new/page.tsx`, `app/(app)/campaigns/[id]/edit/page.tsx`, `app/(app)/integrations/meta/callback/page.tsx`.
- Builder components: `components/campaigns/builder/{tree,campaign-form,adset-form,ad-form,audience-editor,placements-editor,media-uploader,preview-panel}.tsx`.
- API and types: `lib/api/meta.ts`, `lib/types/meta.ts`.
