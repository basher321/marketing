# SPEC-FE-006: Dashboard — Automation Engines Cards

## Purpose
Wire the Dashboard page's "Automation Engines" section (3 engine cards: E-Commerce, Marketing, Customer Service) to real, already-implemented backend data.

## Scope
In scope: exactly the grid-3 row of 3 engine cards beneath the "Automation Engines" section title, each with a header (engine name + status dot) and 4 metric rows, matching the mockup's markup:
- E-Commerce: Active workflows, Orders (24h), Low-stock alerts, Pending approvals
- Marketing: Active campaigns, Scheduled posts, Avg. ROAS, Pending approvals
- Customer Service: Open threads, Avg. response, Deflection rate, CSAT (7d)

Explicitly NOT being built by this spec:
- The top 4 summary cards (SPEC-FE-005, already done)
- The "Recent Activity" timeline — a later spec
- Any click-through/drill-down from an engine card into its own engine page

## Contract
The real backend endpoints already implemented for these 12 metrics across the workflows, orders, inventory, approval_queue, campaigns, scheduled_posts, and conversations domains. Do not assume field names, route paths, or response shapes — confirm every one from the real backend code per Functional Rule 1 before writing any fetch code.

## Functional rules
1. Before writing any code, read the real backend's actual route/schema files (and CLAUDE.md) for: workflows (active-workflow count), orders (24h order count — the same metric SPEC-FE-005 already fetches for the Dashboard's "Orders" card), inventory (low-stock alert count), approval_queue (per-engine pending-approval counts, one count each for "ecommerce" and "marketing"), campaigns (active-campaign count and avg. ROAS — the same ROAS metric SPEC-FE-005 already fetches for "Ad Spend"), scheduled_posts (count), and conversations (open-thread count — the same metric SPEC-FE-005 already fetches for "Open Conversations"; plus avg. response time, deflection rate, and CSAT(7d)). For each of the 12 metrics, determine the exact endpoint path and exact response field name. If any cannot be confidently located or is ambiguous, stop and report exactly which metric and why, rather than guessing.
2. Wherever a metric is identical to one SPEC-FE-005 already fetches (24h order count, avg. ROAS, open-thread count), reuse the same lib/api/dashboard.ts function and the same TanStack Query cache entry — do not issue a second, duplicate fetch for the same real value.
3. Extend lib/api/dashboard.ts with the additional functions needed for the remaining 9 metrics not already covered by SPEC-FE-005, each calling apiFetch against its confirmed real endpoint.
4. Extend lib/types/dashboard.ts with the corresponding response types.
5. Render exactly the 3 engine cards, in the mockup's exact order (E-Commerce, Marketing, Customer Service), each with its exact engine name, its 4 metric rows in the mockup's exact order and exact labels ("Active workflows", "Orders (24h)", "Low-stock alerts", "Pending approvals", etc.), using the .engine-card/.engine-header/.engine-name/.engine-metric/.engine-metric-label structure and tokens from SPEC-FE-001.
6. The status dot + "Active" label next to each engine name: since no backend spec computes an engine-level health/status value, render this statically as "Active" for all three cards, exactly matching the mockup — this is not a fabrication, since the mockup itself hardcodes it with no backing data source either. Add a code comment stating this is intentionally static pending a future engine-health spec, if one is ever written.
7. Avg. response time formatting: if the confirmed real backend response already returns a pre-formatted string (e.g. "2m 14s"), render it directly. If it returns a raw numeric duration (seconds or minutes), format it as "{m}m {s}s" to match the mockup's exact template. Confirm which case applies from the real response — do not assume.
8. Deflection rate and CSAT: render exactly as the confirmed backend response provides them, formatted as "{n}%" and "{n}/5" respectively to match the mockup's exact templates, using the real returned numbers.
9. Each metric value renders its own independent loading state (e.g. "—") while its query is in flight, and its own independent error indicator if its query fails — one metric's failure must not blank the rest of its card or the other cards.

## Edge cases
- A count metric of exactly 0 (e.g. 0 low-stock alerts): render "0" plainly, not as loading or error.
- A metric shared with SPEC-FE-005 that is still loading when this section first renders: show the same loading state SPEC-FE-005 shows for it, sourced from the same cached query — no separate, out-of-sync loading indicator.

## Non-functional rules
- No mock/hardcoded data anywhere except the static "Active" status dot per Functional Rule 6.
- Must not change SPEC-FE-005's summary-cards component or its fetch functions beyond the reuse described in Functional Rule 2.
- Must not change SPEC-FE-002's other 9 routes or the sidebar/topbar.
- No new dependency beyond what's already installed.

## Acceptance criteria
1. All 3 engine cards render with the exact names, in the exact order, each with its exact 4 metric labels in the exact order, matching the mockup.
2. Every displayed metric value traces to a real backend response field confirmed in the plan step — none are hardcoded, except the static "Active" status dot.
3. The 3 metrics shared with SPEC-FE-005 (orders 24h, avg. ROAS, open threads) are fetched exactly once each and reused, not duplicated.
4. Avg. response, deflection rate, and CSAT render using the exact mockup templates with real numbers substituted.
5. Each metric shows an independent loading/error state without affecting sibling metrics or cards.
6. SPEC-FE-005's summary cards and SPEC-FE-002's other 9 routes/shell are unchanged.

## Assumptions
- The exact backend route paths and response field names for these 12 metrics are authoritative per Functional Rule 1.
- The engine status dot is intentionally static per Functional Rule 6, since the mockup itself has no dynamic source for it.

## Target files
- app/(app)/dashboard/page.tsx (extends SPEC-FE-005's version, adding this section)
- components/dashboard/engine-cards.tsx (new)
- lib/api/dashboard.ts (extends SPEC-FE-005's version)
- lib/types/dashboard.ts (extends SPEC-FE-005's version)
