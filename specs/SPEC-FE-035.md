# SPEC-FE-035: Analytics — Ads, Engagement, Customer Service tabs

Status: IMPLEMENTED (2026-10-01; the user said to go ahead with everything). Verified E2E in headless Edge on dev-shop: every tile and table matched the backend, the backend matched raw SQL, and the 7d/90d buttons each refetched with their range. The empty state was checked on a throwaway sign-up tenant, deleted afterwards. No console errors. Depends on SPEC-BE-050. Amends the Analytics page, whose "only Sales has content" rule no longer applies. The Sales tab is unchanged.

## Functional rules
1. A range selector (7 / 30 / 90 days, default 30) applies to the three new tabs.
2. **Ads:**
   - Stat tiles: Spend, Active campaigns, Budget used, CTR, ROAS. CTR and ROAS show "—" with the backend's `missing_reason` as a hint.
   - A "Spend by day" bar chart (hand-rolled SVG, like the existing Revenue chart).
   - A campaign table: name, status badge, channels, budget, spend, pacing % with a thin bar.
3. **Engagement:**
   - Tiles: Published, Scheduled, Pending, Failed posts.
   - A "Posts by day" chart and a "by channel" table.
   - A content pipeline row (Draft → Pending approval → Approved → Published).
   - Likes, comments, shares and reach show "—" with the hint.
4. **Customer Service:**
   - Tiles: Conversations, Avg first response, Avg resolution time, CSAT (with the response count), AI reply share, Deflection.
   - A "New vs resolved by day" chart and a "by channel" table.
5. Loading, empty ("No data in this period") and error states for each tab. No chart library, matching the existing hand-rolled SVG charts.

## Acceptance criteria (verified E2E)
Every tile, chart and table matches the backend numbers, which match the DB (checked for dev-shop). Switching the range refetches the data.

## Target files
- app/(app)/analytics/page.tsx
- components/analytics/ads-report.tsx, engagement-report.tsx, service-report.tsx (new; a small shared bar chart lives in ads-report.tsx and is exported)
- lib/api/analytics.ts, lib/types/analytics.ts

## Implementation notes
- The range selector is shown only on the three new tabs. The Sales tab keeps its fixed 7-day view.
- Shared pieces (`Tile`, `BarChart`, `ReportStatus`, `money`, `pct`, `channelLabel`) are exported from `ads-report.tsx`. The chart reuses the mockup's `.chart`/`.bar` markup, like Revenue by Day, rather than a literal `<svg>`, and has no chart library. Second series = `chart-3`. Hover a bar for its exact value. "Today" is marked on the axis.
- Each tab shows its tiles even when the values are 0 (zeros are real). Charts with all-zero data and empty tables show "No data in this period".
- Customer Service: when conversations are resolved but have no `resolved_at`, Avg resolution says "No resolution time is recorded…" and the chart says why it has no Resolved bars. All 8 resolved dev-shop conversations are in this state. The backend correctly returns null, not an estimate.
- Ads pacing over 100% (spending ahead of schedule) turns the thin bar amber. dev-shop's demo spend gives 226.8% and 911.2% on two campaigns: real numbers from the seeded data.
