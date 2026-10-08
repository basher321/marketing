# SPEC-FE-008: Command Chat — Message History & Send

## Purpose
Fix a CSS gap left by SPEC-FE-005/006/007 (they used .card/.engine-card/.timeline-* classes that were never actually ported into the codebase), and build the Command Chat page's message list and send functionality against the real, already-implemented orchestrator message endpoints — plain user/AI message bubbles only, deferring full plan-card and approvals-panel rendering to later specs.

## Scope
In scope:
- Retroactive fix: port the missing CSS classes SPEC-FE-005/006/007 already depend on (.card, .card-title, .card-value, .card-delta, .up, .down, .section-title, .engine-card, .engine-header, .engine-name, .status-dot, .engine-metric, .engine-metric-label, .timeline-item, .timeline-dot, .timeline-time, .timeline-body), copied verbatim from the reference mockup into app/globals.css.
- Command Chat page: fetch and render real message history (user/AI bubbles only), and send a new message via the real backend endpoint.
- The .btn/.btn-secondary/.btn-sm base button classes (needed by the chat input's Send button and by later chat-page specs), copied verbatim now since they're shared infrastructure.

Explicitly NOT being built by this spec:
- The plan-card (proposed actions, approve/reject/approve-all/reject-all) — SPEC-FE-009
- The Pending Approvals side panel — SPEC-FE-010
- Any message type other than plain user/AI text — a message associated with a plan renders only a minimal placeholder here (see Functional Rule 4)

## Contract
The real backend orchestrator endpoints already implemented (message history list + send-message, from SPEC-BE-023 as later enhanced by SPEC-BE-033). Do not assume field names, route paths, or response shapes — confirm them from the real backend code per Functional Rule 1.

## Functional rules
1. Before writing any code, read the real backend's app/api/v1/orchestrator.py, its schemas, and CLAUDE.md to determine: the GET message-history endpoint's path and response shape (per-message id, sender/direction field, body text, timestamp, and whatever field — if any — indicates a message is associated with a plan); and the POST send-message endpoint's path, request shape, and response shape (specifically: does it return the new AI reply synchronously in the response body, or must the frontend refetch/poll the message list afterward?). If any of this is ambiguous, stop and report exactly what's unclear rather than guessing.
2. Port the CSS classes listed under Scope into app/globals.css, copying every property value verbatim from the reference mockup — do not approximate or restyle them.
3. On page load, fetch message history via the confirmed GET endpoint. Render each message as a right-aligned user bubble (.msg.user) or left-aligned AI bubble (.msg.ai) based on the confirmed sender/direction field.
4. If a message is associated with a plan (per whatever field the confirmed contract actually uses), render, for this spec only, a minimal placeholder AI bubble reading "AI proposed a plan — see below" in place of the full mockup plan-card markup — this exact wording is a placeholder, not a mockup-matching string, since full plan-card rendering is SPEC-FE-009's job.
5. Sending a message: the chat-input's text field + Send button call the confirmed real POST endpoint with the typed text. On success, clear the input and update the message list — either directly from the response body if it includes the new message(s), or by refetching/invalidating the messages query, whichever actually matches the confirmed contract's real synchronous behavior (do not assume one over the other without confirming in the plan step).
6. While a send is in flight, disable the input and button and show a lightweight sending indicator. On failure, show the real ApiError message inline near the input and do not clear the typed text, so the user can retry.
7. Render the chat header's literal text "Conversation with AI Orchestrator", the input's literal placeholder "Message the orchestrator...", and the button's literal label "Send", matching the mockup exactly.
8. Use the .chat-container/.chat-panel/.chat-header/.chat-messages/.msg/.msg.user/.msg.ai/.chat-input structure, porting those CSS rules verbatim from the mockup as part of this spec (they were never ported before), plus the tokens from SPEC-FE-001.

## Edge cases
- No message history yet (brand-new tenant): render an empty .chat-messages area with no fabricated seed content — the mockup's example conversation ("Launch a Ramadan sale...") is illustrative only, not real seed data to reproduce.
- A very long message body: no truncation logic invented; let normal text wrapping inside .msg's max-width handle it.
- Message history fetch fails: show an inline error in the chat panel rather than a blank page.

## Non-functional rules
- No mock/hardcoded message content anywhere except the one placeholder string in Functional Rule 4.
- Must not change SPEC-FE-005/006/007's own component logic — only add the missing CSS they already depend on.
- Must not change SPEC-FE-002's other 9 routes or the sidebar/topbar.
- No new dependency beyond what's already installed.

## Acceptance criteria
1. All CSS classes listed under Scope now exist in app/globals.css with values verbatim from the mockup, and the Dashboard (SPEC-FE-005/006/007) renders correctly using them (visually verify no missing-class fallback styling).
2. Real message history renders as user/AI bubbles correctly attributed by sender.
3. A plan-associated message (if any exist in real data) renders only the placeholder text from Functional Rule 4, not a fabricated full plan card.
4. Sending a message calls the real endpoint, and the UI updates consistently with whatever the confirmed contract's real synchronous behavior actually is.
5. Send-in-flight and send-failure states behave per Functional Rules 5–6.
6. SPEC-FE-002's other 9 routes and the sidebar/topbar are unchanged.

## Assumptions
- The real orchestrator message-history/send contract is authoritative per Functional Rule 1.
- Full plan-card and approvals-panel rendering are explicitly deferred to SPEC-FE-009/SPEC-FE-010.

## Target files
- app/globals.css (corrective addition of missing CSS classes, extending SPEC-FE-001's version)
- app/(app)/chat/page.tsx (extends SPEC-FE-002's stub)
- components/chat/message-list.tsx (new)
- lib/api/orchestrator.ts (new)
- lib/types/orchestrator.ts (new)
