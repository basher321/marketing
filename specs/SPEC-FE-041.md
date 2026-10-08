# SPEC-FE-041: Command Chat control UI — clarifications, editable plans, live execution status, results

Status: IMPLEMENTED, NOT YET VERIFIED ON THE LIVE DB (2026-10-01). The plan was approved as recommended (all 9 decisions). Done: ruff/mypy at baseline, the app imports, `next build` passes, and the logic was checked in-process with `httpx.MockTransport` (no DB). Still open: the additive DDL and the rolled-back live-Postgres acceptance run, both blocked by the session's permission rules. The user must run the DDL, then re-run verification. Backend: SPEC-BE-059 and SPEC-BE-060. Extends `components/chat/{chat-panel,plan-card,approvals-panel}.tsx`.

Implementation notes: plan cards poll every 2 s while steps are queued or running. Chat result links deep-link to `/workflows?open=<id>` and `/ecommerce?tab=shipping`.

## Changes
- **Clarifying questions:**
  - An AI question that belongs to a pending draft shows a chip such as "Waiting for: budget, countries".
  - The composer placeholder becomes the question's hint.
  - "Start over" discards the pending draft.
- **Plan card** (one per plan). Actions are numbered and grouped by module icon (E-Commerce, Shipping, Marketing, Meta, Workflows). Each action shows:
  - A risk badge: Read / Draft / Needs approval / Owner approval.
  - Its parameters in a readable form, and dependency arrows ("after #1").
  - A status that updates live. The card polls `GET /orchestrator/plans/{id}` every 2 s while any action is approved or running, and stops when the plan finishes. The statuses are:
    - Pending approval → Running (spinner).
    - **Succeeded**, with result links: Ads Manager, open in Campaign builder, open workflow in builder, shipping zone.
    - **Failed**, with the classified error and a Retry button (manager+).
    - **Skipped**, with the reason.
- **Edit before approval:** "Edit" on a pending action opens a small form built from the action's params (the same fields the backend validates). Saving re-validates and shows errors inline.
- **Approve / Reject:**
  - Per action, plus "Approve all I can", which only sends the items the user's role may approve.
  - Owner-only items show "Owner approval required" to non-owners.
- **Workflow draft preview:** for `create_workflow` and `update_workflow`, a mini trigger → condition → actions diagram, reusing the node styles from `components/workflows/canvas.tsx`, with an "Open in Workflow Builder" link.
- **Result summary** messages render tables and links from the backend's structured result. The client never makes up numbers.

## Acceptance criteria
Run in headless Edge against the running backend and the live Postgres. The LLM is a dev-only deterministic fixture provider; Meta and store calls use the fixture transport.
1. **Command-A/B:** the multi-module example produces a plan card with 4 actions. Drafts show Succeeded right away. Approving the rest shows Running → Succeeded, followed by the summary message.
2. **Command-C / Workflow-C:** a command without a budget shows the question and the chip, and answering it completes the plan.
3. A Meta failure shows Failed with Retry, and its dependents show Skipped.
4. Edit before approval works and re-validates.
5. `npx tsc --noEmit` passes.

## Open decision
- **The LLM in E2E.**
  - *Recommend:* a dev-only `LLM_PROVIDER=fixture`, refused in production, that replays recorded JSON responses by prompt hash. This keeps chat E2E deterministic.
  - *Alternative:* run E2E against a real LLM key. It isn't deterministic, and it costs money.

## Target files
Existing: `components/chat/chat-panel.tsx`, `components/chat/plan-card.tsx`, `components/chat/approvals-panel.tsx`, `components/chat/decisions.ts`, `app/(app)/chat/page.tsx`, `lib/api/orchestrator.ts`, `lib/types/orchestrator.ts`, `lib/api/approvals.ts`.

**New file (needs approval):** `components/chat/workflow-preview.tsx`.
