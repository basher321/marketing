# SPEC-FE-010: Command Chat — Pending Approvals Panel

## Purpose
Wire the Command Chat page's "Pending Approvals" side panel to the real, already-implemented approval_queue endpoints (SPEC-BE-020/024/025), completing the Command Chat page.

## Scope
In scope: exactly the .approvals-panel element beside the chat panel — its heading with a live count, its list of approval items (title, engine + relative time, View/Approve buttons), matching the mockup's markup.

Explicitly NOT being built by this spec:
- Any change to the chat message list or plan-card from SPEC-FE-008/009
- A real "View" detail flow — see Functional Rule 5
- Any per-engine drill-down page

## Contract
The real backend endpoints already implemented for the pending-approvals list (SPEC-BE-025, reusing SPEC-BE-020's engine mapping) and for approving/rejecting an item (SPEC-BE-024). Do not assume field names, route paths, or response shapes — confirm them from the real backend code per Functional Rule 1.

## Functional rules
1. Before writing any code, read the real backend's approval_queue routes/schemas (app/api/v1/approvals.py) and CLAUDE.md to determine: the exact GET list endpoint's path and response shape (per-item id, human-readable title field, engine label field, requested-at timestamp), whether the response includes a total count or the frontend should use the array length, and the exact single-item approve/reject endpoint(s) — specifically confirming whether this is the same endpoint SPEC-FE-009 already calls for individual plan-action approve/reject, since both features act on the same underlying approval_queue domain. If any of this is ambiguous, stop and report exactly what's unclear rather than guessing.
2. Render the panel heading as "Pending Approvals ({n})" where {n} is the real count from Functional Rule 1.
3. Render one .approval-item per real item: its real human-readable title (rendered exactly as the backend provides it — SPEC-BE-025 already builds this, do not reconstruct it from raw fields), a meta line "{engine label} · {relative time}" using the real engine label the backend provides (reused from SPEC-BE-020's mapping, per SPEC-BE-025 — do not re-derive an engine label from a raw subject_type on the frontend), and the relative time computed client-side from the real requested-at timestamp.
4. "Approve" calls the real confirmed single-item approve endpoint for that item. On success, remove the item from the list (or update its state per whatever the confirmed contract's real behavior is) and decrement the panel's count.
5. "View": no dedicated backend endpoint exists for this, and no per-engine detail view is built yet in the frontend (the E-Commerce/Marketing/Customer Service pages are still SPEC-FE-002's title-only stubs). Render "View" as present but non-functional for now (matching the honest current state, the same way SPEC-FE-002 left the topbar icons non-functional) — do not fabricate a modal or detail page. Add a code comment noting this is deferred until the relevant per-engine page/detail spec exists.
6. Cross-consistency with SPEC-FE-009: since this panel and the chat plan-card both act on the same approval_queue domain, use a shared TanStack Query key namespace (e.g. a top-level "approvals" key) so that approving/rejecting an action from the chat plan-card (SPEC-FE-009) invalidates and refreshes this panel's list, and vice versa — the two surfaces must never show inconsistent state for the same underlying item.
7. Use the .approvals-panel/.approval-item/.approval-title/.approval-meta/.approval-buttons structure, porting those CSS rules verbatim from the mockup as part of this spec.

## Edge cases
- Zero pending approvals: render "Pending Approvals (0)" with a plain "Nothing pending" message instead of an empty list.
- The list query still loading: render a lightweight loading state in the panel.
- The list query errors: render an inline error in the panel without affecting the chat panel beside it.
- Approving an item that was already resolved by someone else in the meantime (a real 404/409-style response): surface the real error and refresh the list, rather than leaving a stale item in place.

## Non-functional rules
- No mock/hardcoded approval items anywhere.
- Must not change SPEC-FE-008's or SPEC-FE-009's chat-panel rendering, only add this sibling panel.
- Must not change SPEC-FE-002's other 9 routes or the sidebar/topbar.
- No new dependency beyond what's installed.

## Acceptance criteria
1. The panel's heading count and every item's title/engine label/relative time trace to real backend data confirmed in the plan step.
2. Approving an item calls the real confirmed endpoint and updates both this panel and SPEC-FE-009's plan-card (if the same item appears there) consistently, verified via the shared query-key invalidation.
3. "View" is present, visibly non-functional, and documented as deferred — not a fabricated modal or page.
4. Zero-items, loading, and error states are each handled distinctly.
5. SPEC-FE-008/009's chat panel and SPEC-FE-002's other 9 routes/shell are unchanged.

## Assumptions
- The real approval_queue list/approve contract is authoritative per Functional Rule 1.
- Whether the single-item approve endpoint is shared with SPEC-FE-009's is confirmed, not assumed, in the plan step.
- "View"'s real behavior is deferred until a per-engine detail spec exists.

## Target files
- app/(app)/chat/page.tsx (extends SPEC-FE-008/009's version, adding this panel beside the chat container)
- components/chat/approvals-panel.tsx (new)
- lib/api/approvals.ts (new — approval_queue is its own backend domain, distinct from orchestrator)
- lib/types/approvals.ts (new)
- app/globals.css (extends, adding .approvals-panel, .approval-item, .approval-title, .approval-meta, .approval-buttons verbatim from the reference mockup)
