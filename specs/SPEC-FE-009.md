# SPEC-FE-009: Command Chat — Plan Card & Approve/Reject Actions

## Purpose
Replace SPEC-FE-008's placeholder "AI proposed a plan — see below" bubble with the real, fully-wired plan card (proposed actions, per-action approval status, and Approve All / Reject All / Review Each controls), backed by the real orchestrator/approval_queue endpoints (SPEC-BE-031/032/033/024).

## Scope
In scope: exactly the .plan-card element within the chat message stream — its title, its list of actions with badges, and its three buttons — wired to real data and real approve/reject calls.

Explicitly NOT being built by this spec:
- The Pending Approvals side panel — SPEC-FE-010
- Any change to plain user/AI message rendering from SPEC-FE-008
- Any new plan-generation trigger — plans are already generated server-side when a message is sent (SPEC-FE-008); this spec only renders and acts on them

## Contract
The real backend endpoints already implemented for plan/action data and for approving or rejecting actions (from SPEC-BE-031/032/033, and SPEC-BE-024's approval_queue approve/reject/approve-all/reject-all). Do not assume field names, route paths, or response shapes — confirm them from the real backend code per Functional Rule 1.

## Functional rules
1. Before writing any code, determine from the real backend code (and CLAUDE.md): whether the message-history/send response (already confirmed in SPEC-FE-008) embeds the full action list with per-action id/description/approval-status, or whether a separate GET call (e.g. GET /orchestrator/plans/{id}) is needed to fetch it; and the exact real endpoint(s) for approving/rejecting one action and for approving/rejecting all actions in a plan — including whether the frontend should call orchestrator-level plan endpoints or approval_queue-level endpoints directly, since both exist on the backend and only the real integration decides which is authoritative here. If any of this is ambiguous, stop and report exactly what's unclear rather than guessing.
2. Render the plan card's title as "Proposed Plan · {n} actions" where {n} is the real count of actions in the plan.
3. Render one .plan-action row per real action, with its real human-readable description prefixed with "▸ " (per the mockup), and a badge showing its real approval state: "Needs approval" (badge-warn) while pending and requiring approval, "Auto-approved" (badge-success) if the confirmed data marks it as not requiring approval, or its real terminal state (e.g. approved/rejected, badge-success/badge-danger) if already decided. Do not fabricate a description string if the backend only returns structured type+params with no ready-made description — in that case stop and report rather than inventing prose. Do not invent additional badge states beyond what the real status field actually supports.
4. "Approve All" calls the real confirmed bulk-approve endpoint for this plan/its actions; "Reject All" calls the real confirmed bulk-reject endpoint. Both must update every action's badge to reflect the new real state once the call succeeds (via the confirmed contract's actual response or a refetch).
5. "Review Each": a client-side-only toggle with no backend call of its own. When active, each action row still in "Needs approval" state shows two small inline buttons — Approve / Reject — each calling the real confirmed single-action approve/reject endpoint for just that action. Document this as a reasoned UI interpretation, since the mockup's static markup doesn't specify "Review Each"'s behavior beyond being a button, and no backend endpoint is dedicated to it specifically.
6. Disable the relevant button(s) while an approve/reject call is in flight; on failure, surface the real ApiError message near the plan card without discarding the rest of its content.

## Edge cases
- A plan with zero actions: title reads "Proposed Plan · 0 actions", no action rows render, and all three buttons are disabled.
- A plan where every action is already decided before the user acts: show each one's real final badge only; if calling Approve All/Reject All/an individual action on an already-decided action errors per the real backend, stop and report rather than silently swallowing the error.

## Non-functional rules
- No mock/hardcoded plan or action data anywhere.
- Must not regress SPEC-FE-008's plain user/AI message rendering.
- No new dependency beyond what's installed.

## Acceptance criteria
1. Every rendered plan title, action description, and badge state traces to real backend data confirmed in the plan step.
2. Approve All / Reject All / per-action Approve / Reject (via Review Each) each call the real confirmed endpoint and correctly update the UI once the real state changes.
3. "Review Each" is purely a client-side reveal with no backend call of its own.
4. A plan with pre-decided actions renders their real final state, not a hardcoded "Needs approval".
5. Failure of any approve/reject call surfaces the real error message without breaking the rest of the plan card.
6. SPEC-FE-008's plain message rendering and SPEC-FE-002's shell/other routes are unaffected.

## Assumptions
- The real contract confirmed per Functional Rule 1 is authoritative for how plans/actions are fetched and acted on.
- "Review Each"'s exact behavior is a documented, reasoned UI interpretation, since no backend contract addresses it specifically.

## Target files
- components/chat/message-list.tsx (extends SPEC-FE-008, replacing the plan-message placeholder with the real plan card)
- lib/api/orchestrator.ts (extends SPEC-FE-008)
- lib/types/orchestrator.ts (extends SPEC-FE-008)
- app/globals.css (extends, adding .plan-card, .plan-title, .plan-action, .plan-buttons, .badge, .badge-success, .badge-warn, .badge-danger, .badge-neutral verbatim from the reference mockup)
