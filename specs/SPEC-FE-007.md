# SPEC-FE-007: Dashboard — Recent Activity Timeline

## Purpose
Wire the Dashboard page's "Recent Activity" timeline to the real, already-implemented backend activity-feed endpoint (SPEC-BE-022), completing the Dashboard page.

## Scope
In scope: exactly the "Recent Activity" card beneath its section title, rendering a list of timeline items, each with a colored dot, a relative time label, and a message body — matching the mockup's markup.

Explicitly NOT being built by this spec:
- The top 4 summary cards (SPEC-FE-005) or the Automation Engines cards (SPEC-FE-006), both already done
- Any pagination, "load more", or filtering of the activity feed — render whatever the confirmed endpoint returns for its default call
- Click-through from a timeline item into the entity it references

## Contract
The real backend endpoint built by SPEC-BE-022. That spec itself was written with a deliberate caveat: its exact target files/route were left for Claude Code to identify from CLAUDE.md, or to stop and report if no suitable stub existed. Do not assume this endpoint's path, response shape, or field names — confirm them from the real backend code per Functional Rule 1, and be prepared for the possibility that it was never actually built, per Functional Rule 1's fallback.

## Functional rules
1. Before writing any code, check the real backend repo and CLAUDE.md for whatever SPEC-BE-022 actually produced: its route path, its response shape (is it a flat list of items, or paginated?), and each item's exact fields (timestamp field, message/body field, any category/severity/type field). If SPEC-BE-022 was never implemented, or its shape is ambiguous, stop and report this plainly rather than building against a guessed contract or fabricating one.
2. lib/api/dashboard.ts gets one additional function (e.g. fetchRecentActivity) calling apiFetch against the confirmed real endpoint.
3. lib/types/dashboard.ts gets the corresponding response type, matching the real confirmed fields exactly.
4. Relative time: compute the "N min ago" / "N hour(s) ago" label client-side from the real timestamp field the backend returns (do not expect the backend to return a pre-formatted relative string unless the confirmed contract shows it already does) — matching the mockup's granularity style (minutes for under 60 minutes, hours for 60 minutes and over).
5. Dot color: if the confirmed real response includes a category/severity/type field, map it to a dot color using SPEC-FE-001's tokens (a "success"-like value → --success green, a "warning"-like value → --warn amber, anything else or absent → the default --accent indigo, matching the mockup's own default). If no such field exists in the confirmed response at all, render every dot with the default --accent color and add a code comment stating that per-item color coding could not be reproduced because the real data has no category field — do not invent a classification scheme.
6. Message body: render exactly the text the confirmed real response provides for each item. If that field is a plain string with no markup, render it as plain text — do not invent logic to guess which words to bold. If the confirmed real response does embed some form of emphasis marker (e.g. markdown-style **bold** or a structured field naming which substring to emphasize), reproduce that emphasis; otherwise render plain text and note in a code comment that the mockup's bolded entities could not be reproduced without a real backing field for them.
7. Render items in the order the backend returns them (do not assume newest-first if the confirmed contract doesn't already guarantee it — if ordering is unspecified by the real endpoint, note this in a code comment rather than silently imposing a sort the backend didn't promise).
8. Use the .card/.timeline-item/.timeline-dot/.timeline-time/.timeline-body structure and tokens from SPEC-FE-001.

## Edge cases
- Zero activity items returned: render the card with a plain "No recent activity" message rather than an empty container or an error.
- The query still loading: render a lightweight loading state inside the card (e.g. a few skeleton rows) rather than nothing.
- The query errors: render a small inline error message inside the card without affecting the rest of the Dashboard page (summary cards, engine cards).

## Non-functional rules
- No mock/hardcoded activity items anywhere.
- Must not change SPEC-FE-005's or SPEC-FE-006's components, fetch functions, or rendered output.
- Must not change SPEC-FE-002's other 9 routes or the sidebar/topbar.
- No new dependency beyond what's already installed.

## Acceptance criteria
1. If SPEC-BE-022 exists and its contract is confirmable, the timeline renders real items with real timestamps converted to relative time, matching the mockup's visual structure.
2. If SPEC-BE-022 cannot be confirmed to exist or its shape is ambiguous, implementation stops with a clear report rather than a guessed/fabricated endpoint call.
3. Dot color coding only appears if backed by a real category/severity field in the confirmed response; otherwise every dot is the default accent color, with the honest limitation documented in a code comment.
4. Message bodies are never partially bolded unless the real response actually supports identifying which substring to emphasize.
5. Zero items, loading, and error states are each handled distinctly per Edge Cases.
6. SPEC-FE-005, SPEC-FE-006, and SPEC-FE-002's other 9 routes/shell are unchanged.

## Assumptions
- The exact shape of SPEC-BE-022's endpoint (if it exists) is authoritative per Functional Rule 1 — this spec does not assert it.
- Relative-time formatting granularity follows the mockup's own examples (minutes under an hour, hours at and above).

## Target files
- app/(app)/dashboard/page.tsx (extends SPEC-FE-006's version, adding this section — completing the Dashboard page)
- components/dashboard/recent-activity.tsx (new)
- lib/api/dashboard.ts (extends SPEC-FE-006's version)
- lib/types/dashboard.ts (extends SPEC-FE-006's version)
