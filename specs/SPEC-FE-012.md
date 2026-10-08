# SPEC-FE-012: Marketing — Summary Cards

## Purpose
Wire the Marketing Automation page's top 4 summary cards (Active Campaigns, Scheduled Posts, Avg. ROAS, CTR (7d)) to real, already-implemented backend data (SPEC-BE-009/010/011).

## Scope
In scope: exactly the grid-4 row of 4 cards at the top of the Marketing page.

Explicitly NOT being built by this spec, and not backed by any real endpoint today:
- The "Active Campaigns" table (per-campaign objective/channels/budget/ROAS/status) — SPEC-BE-009 explicitly excluded a campaign-list endpoint, campaign detail, create/launch/pause, and "Active Campaigns table" from its scope, and no later backend spec has added one. Do not fabricate a fetch against a nonexistent endpoint. This section is deferred until a real backend campaign-list spec exists.
- The "Content Calendar" (per-day scheduled-post details) — only a scheduled-posts *count* endpoint exists (SPEC-BE-010); no per-post schedule/day/channel detail endpoint exists. Deferred for the same reason.
- The "+ New Campaign" button's actual behavior.

## Contract
The real backend endpoints already implemented for active-campaign count, scheduled-post count, avg. ROAS (and its week-over-week delta, if it exists), and CTR(7d). Do not assume field names, route paths, or response shapes — confirm them from the real backend code per Functional Rule 1.

## Functional rules
1. Before writing any code, read the real backend's campaigns, scheduled_posts, and ads routes/schemas (and CLAUDE.md) to determine: the exact endpoint(s) and field names for active-campaign count, scheduled-post count, avg. ROAS, and CTR(7d), and specifically whether avg. ROAS's response includes a week-over-week comparison value (the mockup shows "▲ 0.4 vs last week") or only the raw current value. If any of these four metrics cannot be confidently located, stop and report exactly which one and why, rather than guessing.
2. lib/api/marketing.ts exports the fetch functions for these four metrics, calling apiFetch against the confirmed real endpoints.
3. lib/types/marketing.ts holds the corresponding response types.
4. Render exactly the 4 cards, in the mockup's order, with the exact literal titles "Active Campaigns", "Scheduled Posts", "Avg. ROAS", "CTR (7d)", using the .card/.card-title/.card-value/.card-delta structure and tokens already ported by earlier specs.
5. Avg. ROAS's delta line: if the confirmed real response includes a week-over-week comparison value, render "▲/▼ {value} vs last week" using the same up/down derivation rule established in SPEC-FE-005/006 (sign of the value, not a hardcoded direction). If no such comparison value exists in the confirmed real response, omit the delta line entirely and add a code comment stating the mockup's "vs last week" comparison could not be reproduced without real week-over-week data.
6. Active Campaigns, Scheduled Posts, and CTR (7d) render as plain values with no delta line, matching the mockup (none of these three show a delta in the mockup either).
7. Each card shows its own independent loading state while its query is in flight, and its own independent error indicator if its query fails.

## Edge cases
- A metric value of exactly 0: render "0" plainly, not as loading or error.
- Backend temporarily unreachable: each card shows its own error state independently.

## Non-functional rules
- No mock/hardcoded data anywhere.
- Do not build the Active Campaigns table or Content Calendar sections in this spec — see Scope.
- Must not change SPEC-FE-002's other 9 routes or the sidebar/topbar.
- No new dependency beyond what's installed.

## Acceptance criteria
1. All 4 cards render with the exact titles, in the exact order, matching the mockup.
2. Every displayed value traces to a real backend response field confirmed in the plan step.
3. Avg. ROAS's delta line only appears if backed by a real week-over-week value; otherwise it's correctly omitted with the documenting comment.
4. Each card's loading/error state is independent of the others.
5. No Active Campaigns table or Content Calendar content was added.
6. SPEC-FE-002's other 9 routes and the sidebar/topbar are unchanged.

## Assumptions
- The real backend contract for these 4 metrics is authoritative per Functional Rule 1.
- The Active Campaigns table and Content Calendar are confirmed-absent in the current backend (per SPEC-BE-009's own explicit exclusions) and are deferred pending new backend work, not something this spec should guess at.

## Target files
- app/(app)/marketing/page.tsx (extends SPEC-FE-002's stub)
- components/marketing/summary-cards.tsx (new)
- lib/api/marketing.ts (new)
- lib/types/marketing.ts (new)
