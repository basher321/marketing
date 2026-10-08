# SPEC-FE-019: Analytics — Sales Summary Cards & Revenue-by-Day Chart

## Purpose
Wire the Analytics page's Sales tab — 4 summary cards and the Revenue by Day chart — to real, already-implemented backend data (SPEC-BE-015).

## Scope
In scope: the tabs row (Sales/Ads/Engagement/Customer Service, Sales active by default), the grid-4 summary cards (Revenue (7d), Orders (7d), AOV, Refund Rate), and the Revenue by Day bar chart with its legend.

Explicitly NOT being built by this spec:
- Content for the Ads, Engagement, or Customer Service tabs — the mockup has no markup for them; they may toggle active state but show no content yet
- The "Explain this ⓘ" button's real behavior — the architecture doc describes an LLM chart-narration feature, but no backend spec has ever built an endpoint for it. Render it present but non-functional, with a code comment noting this is deferred pending a real narration endpoint.
- The Top Products table — SPEC-FE-020

## Contract
The real backend endpoint(s) already implemented for the sales summary metrics and, if it exists, a daily revenue time series (SPEC-BE-015). Do not assume field names, route paths, response shapes, or whether a day-by-day breakdown endpoint exists at all — confirm from the real backend code per Functional Rule 1.

## Functional rules
1. Before writing any code, read the real backend's analytics routes/schemas (and CLAUDE.md) to determine: the exact endpoint(s) and fields for Revenue (7d), Orders (7d), AOV, and Refund Rate (each with its delta value if one exists), and specifically whether a real endpoint returns a per-day revenue breakdown for the trailing 7 days (needed for the chart) or only the aggregate totals. If a day-by-day endpoint does not exist, stop and report this — do not fabricate a 7-day series by dividing the aggregate.
2. Render the 4 cards with the mockup's exact titles, using the .card/.card-title/.card-value/.card-delta structure already ported. Apply the same up/down delta derivation rule established in SPEC-FE-005 (sign of the real comparison value, not a hardcoded per-card direction) to all 4, and the same "omit + document" fallback if a card's real data has no comparison value.
3. Revenue by Day chart: only build this if Functional Rule 1 confirms a real daily-breakdown endpoint. Render one bar per real day in the trailing 7-day window ending today, with day-of-week labels computed from real dates (not hardcoded "Sun"–"Sat"). Each bar's height is proportional to its value relative to the maximum value in the real 7-day series (a standard scaling computation, not fabricated data). Use the mockup's default chart-1 gradient for every bar except today's, which uses the chart-3 gradient and is labeled "{Day} (today)" in the legend — do not reproduce the mockup's additional chart-2 highlighting on two arbitrary non-today bars, since no real rule justifies which days those would be; document this simplification in a code comment.
4. If no real daily-breakdown endpoint exists (per Functional Rule 1's finding), do not render the chart at all — render a plain message in its place (e.g. "Daily revenue breakdown not yet available") rather than fabricating one from the aggregate.
5. Tabs row renders with the 4 literal labels, Sales active by default; no content is built for the other 3 (per Scope).

## Edge cases
- A metric with no comparison value: omit its delta line per Functional Rule 2's reused fallback rule.
- All 7 days having equal revenue (a degenerate case): every bar renders at full height rather than dividing by zero.

## Non-functional rules
- No mock/hardcoded metric or chart data anywhere.
- Do not build the Ads/Engagement/Customer Service tab content or the Top Products table.
- Must not change SPEC-FE-002's other 9 routes or the sidebar/topbar.
- No new dependency beyond what's installed.

## Acceptance criteria
1. All 4 cards render with the exact titles, and every value/delta traces to real backend data confirmed in the plan step.
2. The Revenue by Day chart only renders if backed by a real daily-breakdown endpoint; otherwise the honest fallback message renders instead.
3. Day labels and bar heights are computed from real dates/values, not hardcoded.
4. Only today's bar uses the distinct highlight color; no fabricated highlighting rule is applied to other bars.
5. "Explain this" is present and visibly non-functional, with the documenting comment.
6. SPEC-FE-002's other 9 routes and the sidebar/topbar are unchanged.

## Assumptions
- The real analytics contract (including whether a daily-breakdown endpoint exists) is authoritative per Functional Rule 1.
- The Ads/Engagement/Customer Service tabs and chart narration are deferred.

## Target files
- app/(app)/analytics/page.tsx (extends SPEC-FE-002's stub)
- components/analytics/sales-summary.tsx (new)
- components/analytics/revenue-chart.tsx (new)
- lib/api/analytics.ts (new)
- lib/types/analytics.ts (new)
- app/globals.css (extends, adding .chart, .bar, .chart-legend, .legend-dot verbatim from the reference mockup; .tabs/.tab/.section-title already ported by earlier specs — reuse, do not duplicate)
