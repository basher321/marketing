# SPEC-FE-074: Analytics — Profit & Loss tab and expenses

Status: IMPLEMENTED (2026-10-22). Browser E2E: totals match the backend, an added expense updates profit, rules shown, CSV button present. Backend SPEC-BE-110.

## Requirements

- New first tab **Profit & Loss** on `/analytics` (the other tabs are unchanged). Range: 7 / 30 / 90 days,
  month to date, year to date, custom from–to.
- Cards: **Sales total** (net revenue, change vs the previous period, sparkline), **Cost breakdown** (product,
  ads by platform, shipping, operating, other; bars), **Profit or loss** (green profit / red loss label, never
  colour alone; margin; change vs previous).
- Chart: revenue vs costs vs profit by day (hand-rolled `.chart` markup, as the other analytics charts).
- Tables: by product (units, revenue, cost or "no cost set"), and "Not counted as sales" (pending, cancelled,
  returned, refunded).
- **Honesty banners:** `complete: false` → "N order lines have no product cost; profit is overstated until you
  set costs" with a link to Products; unavailable ad spend (Zernio) and excluded-currency spend are named.
  Unavailable values show "—", never 0.
- "How this is calculated" expander shows the `rules[]` text.
- **Download CSV** button (the `.csv` route, through `apiFetch` as a blob).
- **Expenses** panel (manager+ to add/edit/delete; others read): list by period, add form (category,
  amount, date, description, vendor).
- Money through the shared currency formatter in the company currency.

## Files

`app/(app)/analytics/page.tsx`, new `components/analytics/profit-loss.tsx`, `components/analytics/expenses.tsx`,
`lib/api/analytics.ts`, new `lib/api/expenses.ts`, `lib/types/analytics.ts`, new `lib/types/expenses.ts`.
