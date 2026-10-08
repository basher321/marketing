# SPEC-FE-042: Analytics shows real Meta results

Status: IMPLEMENTED, NOT YET VERIFIED ON THE LIVE DB (2026-10-01). The plan was approved as recommended (all 9 decisions). Done: ruff/mypy at baseline, the app imports, `next build` passes, and the logic was checked in-process with `httpx.MockTransport` (no DB). Still open: the additive DDL and the rolled-back live-Postgres acceptance run, both blocked by the session's permission rules. The user must run the DDL, then re-run verification. Backend: SPEC-BE-056.

Implementation notes: the Dashboard's Ad Spend card shows ROAS as "—" when it's null.

## Changes
- **Analytics → Ads report** (`/analytics`, the SPEC-BE-050 UI):
  - CTR and ROAS series show real values. "—" with its reason appears only when the backend returns null.
  - New KPI tiles: impressions, reach, clicks, conversions.
  - A "Source: Meta · last synced 10:42" line, with "Sync now" (manager+). It shows the throttle message when used within 5 minutes.
- **Marketing page:** the CTR (7d) card shows the real value or "—", since the response can now be null.
- **Campaign detail results** (on the builder's campaign page):
  - A per-day chart of spend and results, hand-rolled from the `.chart/.bar` markup as `frontend/CLAUDE.md` requires.
  - A per-ad-set and per-ad table with `effective_status`.

## Acceptance criteria
1. **Meta-D:** after a fixture insights import, the Analytics and Marketing pages show exactly the imported numbers. A campaign that the fixture marks disapproved or paused shows that status.
2. With no Meta data, every card shows "—" with its reason. There are no 0% placeholders.
3. `npx tsc --noEmit` passes.

## Target files
Existing: `app/(app)/analytics/page.tsx`, `components/analytics/*`, `components/marketing/*` (the CTR card), `lib/api/analytics.ts`, `lib/types/analytics.ts`, `lib/api/marketing.ts`, `lib/types/marketing.ts`. No new files: the campaign results view lives in SPEC-FE-039's new campaign pages.
