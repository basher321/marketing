# SPEC-FE-014: Customer Service — AI Reply Draft Panel

## Purpose
Wire the Customer Service page's AI Reply Draft panel to the real, already-implemented backend draft/actions endpoints (SPEC-BE-026/027/028), reacting to whichever conversation SPEC-FE-013's table has selected.

## Scope
In scope: exactly the right-hand card in the grid-2 layout — the draft header, body, confidence/grounding line, and the Edit/Handoff/Send Reply buttons, for whichever conversation is currently selected.

Explicitly NOT being built by this spec:
- Any change to the Open Conversations table or its selection mechanism from SPEC-FE-013
- Draft generation's underlying AI logic (already built server-side by SPEC-BE-027/028) — this spec only calls it
- Any conversation without a documented real draft/generate contract — see Functional Rule 4 for the honest fallback

## Contract
The real backend endpoints already implemented for a conversation's pending draft (fetch, edit, generate), and its send-reply/handoff actions (SPEC-BE-026/028). Do not assume field names, route paths, response shapes, confidence format, or grounding-source format — confirm all of these from the real backend code per Functional Rule 1.

## Functional rules
1. Before writing any code, read the real backend's conversations routes/schemas and any ai/ schema file involved (and CLAUDE.md) to determine: how a conversation's current pending draft is fetched (embedded in the conversation-detail response, or a separate endpoint) and its exact fields (draft body text, confidence value and its scale — 0–1 or 0–100 — and its exact grounding-source representation); the exact edit-draft endpoint (request/response shape); the exact send-reply endpoint (does it send the current draft body as-is, or does the frontend need to submit edited text explicitly?); and the exact handoff endpoint. Also confirm whether a generate-draft endpoint exists for a conversation with no current draft. If any of this is ambiguous, stop and report exactly what's unclear rather than guessing.
2. When the selected conversation (from SPEC-FE-013) has a real pending draft, render: "For: {customer} · {channel}" using the real values; the draft body text (rendering any bold entities only if the real data marks them for emphasis — do not invent which words to bold if the field is plain text, per the same rule used in SPEC-FE-007); "Confidence: {pct}% · Grounded in {sources}" using the real confidence value (converted to a percentage if the real scale is 0–1) and the real grounding-source list joined with the mockup's exact separator style.
3. When the selected conversation has no real pending draft: render an honest empty state (e.g. "No pending draft for this conversation") rather than fabricating placeholder draft content. If a real generate-draft endpoint was confirmed in Functional Rule 1, show a "Generate Draft" button that calls it and then displays the result once it returns; if no such endpoint exists, omit that button and note in a code comment that draft generation could not be wired without a confirmed endpoint.
4. "Edit": reveals an editable text area pre-filled with the current draft body. Saving the edit calls the real confirmed edit-draft endpoint with the new text; canceling discards the local change without calling anything.
5. "Send Reply": calls the real confirmed send endpoint with whatever body the confirmed contract expects (the original draft, or the just-edited text — per what Functional Rule 1 determined). On success, update the conversation's status in SPEC-FE-013's table (via shared query invalidation) to reflect its new real state, and clear/replace the draft panel accordingly.
6. "Handoff": calls the real confirmed handoff endpoint. On success, update the conversation's status in SPEC-FE-013's table (via shared query invalidation) to reflect escalation.
7. Disable the relevant button(s) while any of these calls is in flight; on failure, show the real ApiError message inline in the panel without discarding the currently-shown draft.

## Edge cases
- No conversation selected yet (shouldn't happen given SPEC-FE-013's default-select-first-row rule, but guard for it): render an empty panel state rather than erroring.
- Switching the selected conversation while an edit is in progress: discard the unsaved edit and load the newly-selected conversation's draft state fresh.
- Sending a reply for a conversation whose draft was already sent/resolved by someone else in the meantime (a real conflict response): surface the real error and refresh both the panel and SPEC-FE-013's table rather than leaving stale state.

## Non-functional rules
- No mock/hardcoded draft content, confidence value, or grounding sources anywhere.
- Must not change SPEC-FE-013's table rendering or selection logic, only consume the selection it exposes.
- Must not change SPEC-FE-002's other 9 routes or the sidebar/topbar.
- No new dependency beyond what's installed.

## Acceptance criteria
1. The panel's customer/channel line, draft body, confidence, and grounding text all trace to real backend data confirmed in the plan step, for whatever conversation is selected.
2. Edit/Send Reply/Handoff each call their real confirmed endpoint with the correct payload, and their success updates both this panel and SPEC-FE-013's table consistently.
3. A conversation with no real pending draft shows an honest empty state, with a working Generate Draft action only if a real endpoint for it was confirmed.
4. Switching selected conversations correctly discards any in-progress unsaved edit.
5. Failure of any action surfaces the real error message without losing the currently-displayed draft.
6. SPEC-FE-013's table and SPEC-FE-002's other 9 routes/shell are unchanged.

## Assumptions
- The real draft/edit/send/handoff/generate contracts are authoritative per Functional Rule 1.
- Whether bolded entities in the draft body are reproducible depends on real data supporting emphasis markers, per the same honest-fallback rule established in SPEC-FE-007.

## Target files
- app/(app)/customer/page.tsx (extends SPEC-FE-013's version, adding this panel)
- components/customer/reply-draft-panel.tsx (new)
- lib/api/conversations.ts (extends SPEC-FE-013's version)
- lib/types/conversations.ts (extends SPEC-FE-013's version)
