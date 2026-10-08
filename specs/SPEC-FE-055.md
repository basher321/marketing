# SPEC-FE-055: Zernio campaigns in Paid Marketing

Status: IMPLEMENTED (2026-10-08). Decisions are as in SPEC-BE-084: one server key, live
from Zernio, any manager+ publishes, phase 1.
- **Acceptance 1 passes:** `tsc --noEmit` and `next build` (with `NEXT_BUILD_DIR`) are
  clean. The build's edits to `tsconfig.json` / `next-env.d.ts` were reverted.
- **Acceptance 2 (real-browser end to end) is pending:** this session had no browser tool.
  The backend behind every screen passed SPEC-BE-084's 25 checks.
- **Acceptance 3:** existing pages only gained one tab each (see below).

Notes:
- **Disconnect (added 2026-10-08):** each platform card lists its connected ads and
  posting accounts, each with a Disconnect button (`DELETE /zernio/accounts/{id}`,
  manager+). Every connected account uses one Zernio plan slot (the free plan has 2).
- **Meta previews:** only the `facebook.com` iframe address is shown.
- **Boost:** it skips the Ad step.
- **Times:** they are entered in the company timezone and sent as UTC.
Backend: SPEC-BE-084.

## Context

The user wants Zernio (one paid-ads API for every company) inside `/marketing/paid`, with
every option under "+ New campaign": choose the social media platform, then all of its
related sub-options. Nothing else in the software changes. The existing Meta builder, the
multi-platform builder, Create with AI, and the current tabs keep working exactly as
before.

## Functional requirements

1. **Entry points:**
   - The Ad Manager page (`/marketing/paid/ad-manager`, reached by "+ New campaign") gets a
     third mode tab, **"Zernio (all platforms)"**, next to "Build manually" and "Create
     with AI". It opens `/marketing/paid/zernio/new`.
   - `/marketing/paid` gets one more tab, **"Zernio"** (`?tab=zernio`), which lists the
     company's Zernio campaigns.
2. **New campaign wizard** (`/marketing/paid/zernio/new`). It has 7 steps in a stepper,
   with Back/Next; each step validates before Next.
   1. **Platform.** Cards for Facebook, Instagram, TikTok, LinkedIn, Pinterest, X and
      Google Ads (from `GET /zernio/platforms`).
      - Each card shows its connected account(s), or **Connect ↗**. Connect opens Zernio's
        sign-in in a **new tab**; when that tab finishes it tells this page and closes
        (the same pattern as SocialAPI).
      - The user can also choose **Boost an existing post** instead of a new ad.
   2. **Account.** The connected account, then the ad account (name · currency · timezone;
      unusable ones are disabled, with the reason), then the identity:
      - Meta: Page + Instagram account;
      - TikTok: identity;
      - LinkedIn: Company Page;
      - Pinterest: board.
   3. **Goal.** Only the goals this platform accepts, each with a one-line explanation.
      Goal-specific fields appear only when needed:
      - Pixel + event for conversions;
      - lead form id for lead generation;
      - app id + store URL for app promotion;
      - Google: Display or Search.
   4. **Budget & schedule.**
      - **Budget:** daily or lifetime, amount in the ad account's currency
        (`formatMoney`), with the ad account's minimum daily budget shown.
      - **Schedule:** start now or at a time, and an end time (required for lifetime),
        with times shown in the company timezone.
      - **Bid strategy:** platform-allowed choices only, plus the bid amount or ROAS floor
        when the strategy needs it.
   5. **Audience.**
     - **Places:** location search (countries, regions, cities with an optional radius,
       zips, metros), pin + radius (Meta/Google), and excluded locations.
     - **People:** age range, gender, languages, interests and behaviours (search
       pickers, platform-only fields hidden), and income tier where allowed.
     - **Reach:** a live **reach estimate** ("no estimate for this platform" when Zernio
       has none).
     - **Meta delivery:** placements (Automatic, or manual
       platforms/positions/devices) and special ad categories.
     - **Google Search:** keywords with match type.
   6. **Ad.**
      - **Copy:** headline, long headline (Google), primary text, description (Meta), and
        CTA (platform list only), with live character counts against the platform's
        limits.
      - **Destination:** the link URL.
      - **Media:** an image or video from the media library (the existing `MediaPicker`).
        Google Display asks for landscape + square, TikTok is video only, and X is an
        image website card.
      - **Preview:** Meta shows Zernio's rendered placement previews.
   7. **Review.**
      - **Summary:** everything chosen, with **Check with platform** (validate where
        supported).
      - **Publish:** **Publish live** or **Create paused** (manager+).
      - **On success:** the campaign opens on the Zernio tab.
      - **Errors:** the backend's message is shown inline on the step it belongs to.
3. **Zernio tab** (`/marketing/paid?tab=zernio`).
   - **Table:** campaign → ad sets → ads, expandable, with filters (platform, status,
     search) and the 7/30/90-day range. Columns: status, review status, budget, spend,
     impressions, clicks, CTR, conversions and ROAS; "—" when null.
   - **Row actions:** Pause/Resume (each level), Edit name/budget, Delete (confirm), and
     **Analytics**, a drawer with the daily timeline and, on Meta, age/gender/country
     breakdowns. "Zernio is still collecting results" shows on a 202.
   - **Banner:** "Zernio isn't set up on this server" shows when the backend says 503.
4. **Sign-in return:** `/marketing/paid/zernio/callback` finishes the connection (and the
   Facebook Page choice if asked), broadcasts to the opener, and closes itself.
5. **Roles:** buttons show to every role, as elsewhere. A 403 shows the standard "Your role
   can't do this…". Creating, publishing, pausing and resuming need manager+.

## Target files

- New:
  - `frontend/app/(app)/marketing/paid/zernio/new/page.tsx`;
  - `frontend/app/(app)/marketing/paid/zernio/callback/page.tsx`;
  - `frontend/components/zernio/wizard.tsx` (steps);
  - `frontend/components/zernio/campaigns.tsx` (tab table + analytics drawer);
  - `frontend/lib/api/zernio.ts`;
  - `frontend/lib/types/zernio.ts`.
- Changed:
  - `frontend/app/(app)/marketing/paid/ad-manager/page.tsx` (one mode tab);
  - `frontend/app/(app)/marketing/paid/page.tsx` (one tab);
  - `frontend/CLAUDE.md` (one paragraph).

This is more than the usual "page + 3 files". The wizard needs its own route, and the
spec asks for that exception explicitly.

## Acceptance criteria

1. `tsc --noEmit` and `next build` (with `NEXT_BUILD_DIR`) are clean.
2. In a real browser against the running backend with `dev_fakes`:
   - all 7 steps work for Facebook, TikTok and Google Search;
   - only the allowed goals, CTAs and fields show per platform;
   - Connect opens a new tab and refreshes this page;
   - a campaign is created, both live and paused;
   - it appears in the Zernio tab, and pause/resume/delete/analytics work.
3. The existing tabs, Build manually, Create with AI, and the Meta / multi-platform
   builders are unchanged.
