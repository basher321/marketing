# SPEC-FE-013: Customer Service — Open Conversations Table

## Purpose
Wire the Customer Service page's Open Conversations table to real, already-implemented backend data (SPEC-BE-007), and establish conversation selection as the input to the AI Reply Draft panel (built next, in SPEC-FE-014).

## Scope
In scope: exactly the left-hand card in the grid-2 layout — its header with a live open-conversation count, and the table (Customer, Channel, Topic, Waiting, Status columns).

Explicitly NOT being built by this spec:
- The AI Reply Draft panel on the right — SPEC-FE-014
- Any conversation detail/thread view beyond this row-level table

## Contract
The real backend endpoint already implemented for the conversations list (SPEC-BE-007). Do not assume field names, route paths, response shape, the exact status enum values, or the "Waiting" time's source field — confirm all of these from the real backend code per Functional Rule 1.

## Functional rules
1. Before writing any code, read the real backend's conversations routes/schemas (and CLAUDE.md) to determine: the exact list endpoint path and response shape (per-conversation customer name/identifier, channel, topic, a timestamp to compute "Waiting" from, and the real status enum's exact values), and whether the response includes a total/open count or the frontend should use the array length. If any of this is ambiguous, stop and report exactly what's unclear rather than guessing.
2. Render the card header as "Open Conversations ({n})" where {n} is the real count from Functional Rule 1.
3. Render one table row per real conversation, in whatever order the confirmed endpoint returns (do not impose an unconfirmed sort).
4. "Waiting" column: compute an elapsed-time label ("{n}m" under 60 minutes, "{n}h" at 60 minutes and above, matching the mockup's format) client-side from the real timestamp field confirmed in Functional Rule 1.
5. "Status" column: render a badge whose color/label maps to the real status value — badge-warn for a "draft ready"-equivalent value, badge-success for an "auto-replied"-equivalent value, badge-danger for an "escalated"-equivalent value, per the exact real enum confirmed in Functional Rule 1. If the real enum has values beyond these three, stop and report rather than inventing a badge color for an unrecognized one.
6. Row selection: clicking a row selects that conversation (visually indicated — e.g. a subtle background highlight using existing tokens) and exposes the selected conversation's id via shared state (e.g. a small client-side store or lifted state in the page component) for SPEC-FE-014's Reply Draft panel to consume. Default: the first conversation in the list is selected on initial load, matching the mockup's default view of showing one draft. Document this selection behavior as a reasoned UI interpretation, since the static mockup shows no visible selected-row styling of its own — this spec adds the interactivity the two-panel layout implies.
7. Table loading/empty/error states: a skeleton or lightweight loading indicator while fetching; a plain "No open conversations" message if the real list is empty; an inline error message if the fetch fails.

## Edge cases
- A conversation with a missing/null topic or customer name: render an em dash "—" rather than blank or "undefined".
- Very long topic text: no truncation logic invented; let normal cell wrapping apply.

## Non-functional rules
- No mock/hardcoded conversation rows anywhere.
- Must not change SPEC-FE-002's other 9 routes or the sidebar/topbar.
- No new dependency beyond what's installed.

## Acceptance criteria
1. Every rendered conversation row's fields trace to real backend data confirmed in the plan step.
2. Status badges use only the real enum values confirmed in the plan step, with no invented mapping for anything unrecognized.
3. The header count matches the real confirmed count/array length.
4. Clicking a row updates the selection state correctly, with the first row selected by default.
5. Loading/empty/error states render distinctly and correctly.
6. SPEC-FE-002's other 9 routes and the sidebar/topbar are unchanged.

## Assumptions
- The real conversations-list contract is authoritative per Functional Rule 1.
- Row-click selection is a reasoned interpretation of the mockup's implied two-panel master-detail UX, not something the static mockup explicitly specifies.

## Target files
- app/(app)/customer/page.tsx (extends SPEC-FE-002's stub, establishing the grid-2 layout and selection state)
- components/customer/conversations-table.tsx (new)
- lib/api/conversations.ts (new)
- lib/types/conversations.ts (new)
- app/globals.css (extends, adding .grid-2 verbatim from the reference mockup, if not already present)
