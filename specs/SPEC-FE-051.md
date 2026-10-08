# SPEC-FE-051: Paid Marketing tabs — Campaigns, Ad Sets, Ads, Drafts, Analytics

Status: IMPLEMENTED (code, 2026-10-03). `npx tsc --noEmit` and `next build` are clean. **Pending:** E2E acceptance 1–4 (needs the live DB). Requested by the user: the final UI lists Paid Marketing › Campaigns / Ad Sets / Ads / Drafts / Analytics. Backend: SPEC-BE-079. Builds on SPEC-FE-049.

## Purpose
`/marketing/paid` has two tabs today (Campaigns, which shows live campaigns and drafts stacked; and AI runs). Ads Manager-style navigation gives each level its own tab.

## Changes (`/marketing/paid`, tab in `?tab=`)
| Tab | `?tab=` | Content |
|---|---|---|
| **Campaigns** | none | The existing "Live campaigns" table (unchanged). |
| **Ad Sets** | `ad-sets` | `GET /paid/ad-sets`: name, campaign, platform, status (with Meta's effective status when it differs), budget (`formatMoney` + "/day" / "lifetime" / "campaign budget"), schedule, performance goal, ads, spend, CTR. |
| **Ads** | `ads` | `GET /paid/ads`: thumbnail (when there is one), name + headline, ad set › campaign, platform, status / review feedback, CTA, destination, spend, CTR. |
| **Drafts** | `drafts` | The existing "Drafts" table, moved off the Campaigns tab (unchanged otherwise). |
| **Analytics** | `analytics` | The existing `AdsReport` component (`GET /analytics/ads`) with the shared 7/30/90-day selector. |
| **AI runs** | `ai` | Unchanged. |

**Ad Sets and Ads tables:**
- Filters above the table: platform (all + the platforms that appear), status, search (debounced 300 ms), and a "campaign" chip when opened with `?campaign=<id>` (from a campaign row's new "Ad sets" link). The Ads tab also takes `?ad_set=<id>` (from an ad set row's "Ads" link).
- The range for the result columns uses the same 7/30/90-day selector (default 30 days).
- Paging: 50 per page, Previous / Next, "x–y of N".
- Results: `null` shows "—". When `results_level = "campaign"` the cell's title says "This platform reports results per campaign."
- **Row actions:** Open (→ `/marketing/paid/{campaign_id}/edit`), and Pause / Resume when the status allows it (running/scheduled → Pause, paused → Resume). They call `POST /paid/{ad-sets|ads}/{id}/pause|resume`; on success the list refetches; on error the backend's message shows on the row. Nothing is simulated.
- Empty states: "No ad sets yet. Create a campaign to add one." with a link to `/marketing/paid/ad-manager`.
- Loading / error states as elsewhere (`Loading…`, the backend's message in `text-danger`).

Everything else on the page (header, "+ New campaign", legacy `?draft=` wizard) stays.

## Acceptance (E2E against the running backend and the live DB, dev fakes for the ad platforms)
1. The tab bar shows Campaigns, Ad Sets, Ads, Drafts, Analytics, AI runs, and each tab's URL survives a reload.
2. With the SPEC-BE-079 seed, Ad Sets shows 4 rows and Ads 5, with the right platform and campaign names; the platform filter, the status filter, search and paging change the rows to match the API.
3. Pause on a published Meta ad set → status becomes paused after the refetch; Resume brings it back. A failing call shows the backend's message.
4. Drafts shows the same rows as before the change; Analytics shows the Ads report and the range selector works.
5. `npx tsc --noEmit` and `next build` are clean.

## Target files
- `frontend/app/(app)/marketing/paid/page.tsx`
- New `frontend/components/campaigns/paid-lists.tsx` (Ad Sets and Ads tables, filters, paging)
- New `frontend/lib/api/paid.ts`
- New `frontend/lib/types/paid.ts`

## Out of scope
Editing from the lists, bulk selection, column pickers, exports.
