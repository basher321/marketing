# SPEC-FE-020: Analytics — Top Products Table

## Purpose
Wire the Analytics page's "Top Products" table to real, already-implemented backend data (SPEC-BE-016), completing the Analytics page's Sales tab.

## Scope
In scope: exactly the Top Products table (Product, Units Sold, Revenue, Trend columns).

Explicitly NOT being built by this spec:
- Any change to SPEC-FE-019's summary cards or chart
- Content for the Ads/Engagement/Customer Service tabs

## Contract
The real backend endpoint already implemented for top products (SPEC-BE-016, extending SPEC-BE-015's files). Do not assume field names, route paths, response shape, or the trend calculation's basis — confirm from the real backend code per Functional Rule 1.

## Functional rules
1. Before writing any code, read the real backend's analytics routes/schemas (and CLAUDE.md) to determine: the exact top-products endpoint path and response shape (product name, units sold, revenue, and the trend value's basis — e.g. vs. the prior 7-day period — and whether it's returned as a signed number or with an explicit direction). If any of this is ambiguous, stop and report exactly what's unclear rather than guessing.
2. Render one row per real product, in whatever order the confirmed endpoint returns (do not impose an unconfirmed sort, such as assuming it's always revenue-descending, unless the real contract guarantees that ordering).
3. Revenue formatting: literal "৳" symbol with comma-grouped thousands, matching the mockup.
4. Trend column: derive up/down (▲ green / ▼ red) from the real value's sign, using the same derivation rule established in SPEC-FE-005/006/012/019 — not a hardcoded assumption.
5. Table loading/empty/error states: a skeleton or lightweight loading indicator while fetching; a plain "No product data yet" row if the real list is empty; an inline error message if the fetch fails.

## Edge cases
- A product with a trend value of exactly 0: render "0%" with no arrow/color (neither up nor down), rather than forcing it into one direction.
- Very long product names: no truncation logic invented; let normal cell wrapping apply.

## Non-functional rules
- No mock/hardcoded product rows anywhere.
- Must not change SPEC-FE-019's cards/chart.
- Must not change SPEC-FE-002's other 9 routes or the sidebar/topbar.
- No new dependency beyond what's installed.

## Acceptance criteria
1. Every rendered product row's fields trace to real backend data confirmed in the plan step.
2. Trend arrows/colors are derived from the real signed value, with a neutral rendering at exactly 0.
3. Revenue formatting uses the literal "৳" symbol with comma grouping.
4. Loading/empty/error states render distinctly and correctly.
5. SPEC-FE-019's cards/chart are unchanged.
6. SPEC-FE-002's other 9 routes and the sidebar/topbar are unchanged.

## Assumptions
- The real top-products contract, including the trend's basis and sign convention, is authoritative per Functional Rule 1.

## Target files
- app/(app)/analytics/page.tsx (extends SPEC-FE-019's version, adding this table)
- components/analytics/top-products-table.tsx (new)
- lib/api/analytics.ts (extends SPEC-FE-019's version)
- lib/types/analytics.ts (extends SPEC-FE-019's version)
