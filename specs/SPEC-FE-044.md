# SPEC-FE-044: Ad Manager — choose a platform, then its objective

Status: IMPLEMENTED (2026-10-02), plan approved. Verified E2E in headless Edge on dev-shop against the running backend and the live DB:
- New campaign → Ad Manager with 7 cards, whose badges match `GET /ads/platforms`.
- Meta → the unchanged objective page, and its draft opens the Meta builder.
- TikTok → its own objectives, with the catalog one disabled. The draft is stored with `metadata.platform = tiktok`, objective `conversions` and channels `{tiktok}`, then the editor opens.
- Google → Continue stays disabled until a campaign type is picked.
- Unknown platform → message.

The 3 test drafts and their audit rows were deleted afterwards, leaving dev-shop at 11 campaigns as before. `tsc --noEmit` passes. `npm run build` was not run, because of the running `next dev`. The non-Meta editor screen itself is SPEC-FE-045 (next step). Until then, `/campaigns/<id>/edit` for a TikTok/Google draft still renders the Meta builder, whose API now answers 404 for it. Backend: SPEC-BE-062 (`GET /ads/platforms`, `POST /ads/{platform}/campaigns`). The builder screen for non-Meta platforms is SPEC-FE-045.

Amendment (2026-10-02): **8 cards**, with YouTube added. It is published through Google Ads, so its card shows the Google Ads connection.

## Flow (as the user described it)
`/campaigns` "+ New campaign" → **`/campaigns/ad-manager`** (new: pick a platform) → **`/campaigns/new?platform=<key>`** (that platform's objectives + name) → the editor at `/campaigns/<id>/edit`.

## Functional rules
1. **"+ New campaign"** on `/campaigns` links to `/campaigns/ad-manager`. That's the only change on the list page.
2. **Ad Manager page** (`/campaigns/ad-manager`), titled "Ad Manager":
   - One card for each of the 7 platforms from `GET /ads/platforms`: Meta, TikTok, Google Ads, LinkedIn, X, Snapchat, Pinterest.
   - Each card shows the platform name, where ads run (e.g. "Search, YouTube, Display, Gmail, Discover" for Google), its hierarchy ("Campaign → Ad group → Ad") and a connection badge ("Connected: <account>" or "Not connected").
   - Picking a card opens `/campaigns/new?platform=<key>`.
   - A not-connected platform can still be picked to build a draft. Its card says "Connect in Integrations to publish", with a link to `/integrations`.
   - Platform marks are text labels. No third-party logo images or new dependencies are added.
3. **`/campaigns/new?platform=<key>`:**
   - `platform=meta`, or a missing parameter, renders today's Meta objective page **unchanged** (SPEC-FE-039), plus a "← Choose another platform" link.
   - Any other platform renders the same layout: a heading "Create new <Label> campaign", that platform's objectives from the registry (unavailable ones disabled with the reason), and a Campaign name field. Google Ads also shows a "Campaign type" choice (Search, Performance Max, Display, Demand Gen, YouTube).
   - Continue sends `POST /ads/{platform}/campaigns` → `/campaigns/<id>/edit`.
   - An unknown `platform` shows "Unknown platform" and a link back to the Ad Manager.
4. A 403 shows "Only managers and above can create campaigns." Other errors show the backend's message.

## Acceptance (E2E, headless Edge, dev-shop, test rows removed afterwards)
1. New campaign → Ad Manager shows 7 cards with real connection states.
2. Meta → today's objective page. Creating a draft still opens the Meta builder (regression).
3. TikTok and Google → their own objectives. Continue creates the draft in the DB (`metadata.platform` checked), then opens the editor.
4. `npx tsc --noEmit` and `npm run build` pass.

## Target files
- `app/(app)/campaigns/page.tsx` (link target only)
- `app/(app)/campaigns/new/page.tsx`: platform switch; the Meta branch stays as-is
- New: `app/(app)/campaigns/ad-manager/page.tsx`
- New: `lib/api/ads.ts` and `lib/types/ads.ts`
