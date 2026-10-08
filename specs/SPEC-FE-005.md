# SPEC-FE-005: Dashboard — Top Summary Cards

## Purpose
Wire the Dashboard page's top row of 4 summary cards (Revenue (24h), Orders, Ad Spend, Open Conversations) to real, already-implemented backend data, replacing SPEC-FE-002's static title-only stub for the dashboard route with real content for this one section.

## Scope
In scope: exactly the grid-4 row of 4 cards at the top of the Dashboard page, each showing a title, a value, and a delta/sub-line, matching the mockup's markup:
- Revenue (24h): value + "vs yesterday" delta
- Orders: value + "new since morning" delta
- Ad Spend: value + ROAS sub-line
- Open Conversations: value + "awaiting reply" delta

Explicitly NOT being built by this spec:
- The "Automation Engines" section (3 engine cards) — a later spec
- The "Recent Activity" timeline — a later spec
- Any interactivity beyond displaying fetched values (no click-through, no drill-down)

## Contract
The real backend endpoints already implemented for these 4 metrics (per the backend specs that built them: revenue-24h extends the orders domain, orders-count is the orders domain's own metric, ad-spend+ROAS extends the campaigns domain, open-conversations-count is the conversations domain's own metric). Do not assume field names, route paths, or response shapes — confirm them from the real backend code per Functional Rule 1 before writing any fetch code.

## Functional rules
1. Before writing any code, read the real backend's actual route/schema files for the orders, campaigns, and conversations domains (app/api/v1/orders.py, app/api/v1/campaigns.py, app/api/v1/conversations.py and their schemas, plus CLAUDE.md) to determine, for each of the 4 cards: the exact endpoint path, the exact response field(s) carrying the headline value, and the exact response field(s) (if any) carrying a comparison/delta value. If any of the 4 cannot be confidently located or its shape is ambiguous, stop and report exactly which card and why, rather than guessing a field name.
2. lib/api/dashboard.ts exports four functions (fetchRevenueSummary, fetchOrderSummary, fetchAdSpendSummary, fetchConversationSummary or equivalent names), each calling apiFetch (from SPEC-FE-003) against the confirmed real endpoint and returning a value typed per lib/types/dashboard.ts.
3. Use TanStack Query (per SPEC-FE-003) to fetch all four in parallel on the Dashboard page, each with its own query key (e.g. ["dashboard","revenue"], ["dashboard","orders"], etc.).
4. Render exactly the 4 cards from the mockup's grid-4 row, in the same order, with the exact literal titles "Revenue (24h)", "Orders", "Ad Spend", "Open Conversations", using the .card/.card-title/.card-value/.card-delta visual structure and tokens from SPEC-FE-001.
5. Value formatting: Revenue and Ad Spend use the literal "৳" symbol with comma-grouped thousands (e.g. ৳48,320) — do not substitute a different currency symbol. Orders and Open Conversations are plain integers.
6. Delta line text: reproduce the mockup's exact template per card, substituting real fetched values for the dynamic parts — Revenue: "{arrow} {pct}% vs yesterday"; Orders: "{arrow} {n} new since morning"; Ad Spend: "{arrow} ROAS {roas}x"; Open Conversations: "{arrow} {n} awaiting reply". If the confirmed real backend response for a given card does not actually include the specific value a template needs (e.g. no "awaiting reply" sub-count exists), do not invent a number — omit that card's delta line entirely and add a code comment stating which piece of data was unavailable from the real response.
7. Up/down arrow and color (.up = green/▲, .down = red/▼):
