Deviation from draft: Scope item 3's route list named the pages descriptively ("command chat", "e-commerce", "customer service", "knowledge base"); it now uses the real path segments from app/(app)/ — dashboard, chat, ecommerce, marketing, customer, kb, campaigns, workflows, analytics, integrations — since the draft itself requires the real segments, not guessed names.

# SPEC-FE-022: Frontend System Check (Build, Routes, Auth Guard, Query-Wiring Integrity)

## Purpose
End-to-end verification that everything specified in SPEC-FE-001 through SPEC-FE-021 actually builds, type-checks, lints clean, and behaves correctly when run against the real backend — catching any drift between what those specs described and what the current code actually does, before any further feature specs are layered on top. This is a checking spec, not a feature spec.

## Scope
1. Run the project's build command, `tsc --noEmit`, and the configured linter. Record raw pass/fail output for each.
2. Confirm the real env var gating the API base URL (per SPEC-FE-003 — confirm its actual name from lib/api/client.ts, do not assume) is required, and that the app fails fast with a clear error at startup if it is unset.
3. Confirm all 10 nav routes (/dashboard, /chat, /ecommerce, /marketing, /customer, /kb, /campaigns, /workflows, /analytics, /integrations — the real path segments of the actual app/(app)/ directory) resolve to a rendered page with no unhandled runtime error, both while authenticated and while unauthenticated.
4. Confirm the auth guard built in SPEC-FE-004 behaves exactly as that spec defined: visiting a protected route while signed out redirects to login; a successful login redirects back to the originally-requested route (or to dashboard if none was requested). Read SPEC-FE-004's own acceptance criteria as the source of truth and confirm current behavior matches it — do not substitute a different, "more correct" behavior.
5. For every TanStack Query hook added across SPEC-FE-005 through SPEC-FE-021: re-read that spec's own Functional Rules and Acceptance Criteria, then confirm the loading state, error state, and (where specified) empty state it required are still present in the current code. A later spec editing a shared file (e.g. SPEC-FE-006/007 editing SPEC-FE-005's dashboard files) must not have silently dropped an earlier spec's required state handling.
6. Confirm the shared query-key invalidation between SPEC-FE-009 (plan card approve/reject) and SPEC-FE-010 (approvals panel) still holds — approving or rejecting from either surface must still invalidate both.
7. Confirm that no page makes a request to any endpoint that an earlier SPEC-FE-0XX explicitly flagged as confirmed-unbacked (Marketing's Active Campaigns table/Content Calendar, Campaign Wizard steps 1/2/4/5/6 + create/launch, Workflow canvas natural-language node generation, Integrations OAuth connect/reconnect). These must still render as explicitly absent or non-functional per their original spec — not accidentally wired to a guessed endpoint by a later spec's copy-paste.
8. Write a single findings report to specs/reports/SPEC-FE-022-findings.md listing every check above, its pass/fail result, and for any fail: the exact file and line, what the original spec required, what the code currently does, and the minimal corrective diff (not yet applied — see Functional Rules).

## Explicitly NOT being built
- No new UI, no new page content, no new backend endpoints.
- No workaround or fabricated fallback for a check that fails because a real backend endpoint genuinely doesn't exist or doesn't match a spec's assumption — that goes in the findings report as a gap, and execution stops there for that item.
- No "improvement" beyond what an original SPEC-FE-0XX already specified — this pass restores drift, it does not redesign.

## Target files / outputs
- New: specs/reports/SPEC-FE-022-findings.md
- Existing files: touched only for a mechanical regression fix (a dropped loading/error state, a stale query key, an env var name typo) that clearly restores what an earlier spec already required. Any such fix must be named explicitly in the findings report with a before/after and which spec it restores compliance with.

## Functional Rules
1. Do the read-only audit (Scope items 1–7) completely and write the full findings report before making any code change.
2. Do not guess at "correct" behavior when a spec's own acceptance criteria are ambiguous about it — quote the ambiguous criterion in the report and stop; do not silently pick an interpretation.
3. Treat each prior SPEC-FE-0XX's own Acceptance Criteria section as the sole source of truth for what "correct" means for that file — never substitute your own judgment of what would be better.
4. Any fix applied must be the smallest possible diff that restores the original spec's stated behavior — no refactoring, renaming, or restructuring beyond that.
5. If a genuine backend gap is found (an endpoint a spec assumed exists does not, per the real backend code), report it by name and do not touch the frontend code that calls it.

## Acceptance Criteria
- Build, typecheck, and lint all reported clean, or every failure is documented in the findings report with cause.
- All 10 routes confirmed rendering correctly, authenticated and unauthenticated.
- Auth guard behavior confirmed against SPEC-FE-004's own criteria.
- Every prior spec's required loading/error/empty states confirmed present, with any drift documented.
- Shared query-key invalidation (SPEC-FE-009/010) confirmed intact.
- No confirmed-unbacked endpoint is accidentally called anywhere.
- specs/reports/SPEC-FE-022-findings.md exists and is complete.
- Any code change made is named in the report with the spec it restores compliance with.
