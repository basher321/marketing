# SPEC-FE-022 Findings — Frontend System Check

Run date: 2026-09-26. Audit performed read-only first (Scope 1–7); this report
was written before any other file was touched. **No code changes were
applied** — the audit found no mechanical regression that an original spec
clearly requires restoring (see "Fixes" at the end).

## Summary

| Scope | Check | Result |
|---|---|---|
| 1 | `tsc --noEmit` | PASS |
| 1 | `npm run build` | PASS (both with and without `NEXT_PUBLIC_API_BASE_URL`) |
| 1 | Lint | FAIL — no linter configured (gap, not drift) |
| 2 | API base-URL env var required, clear error | PASS for SPEC-FE-003's criteria; Scope 2's "at startup" wording is AMBIGUOUS vs SPEC-FE-003 (recorded, not decided) |
| 3 | 10 routes render, unauthenticated | PASS (all 10 + `/` redirect + 404) |
| 3 | 10 routes render, authenticated | BLOCKED — SPEC-FE-004 not implemented; no way to authenticate |
| 4 | Auth guard vs SPEC-FE-004 | FAIL (not implemented) + spec text defects (truncated criterion, conflicting redirect rule) |
| 5 | Required loading/error/empty states still present | PASS for every implemented spec; 3 ambiguities recorded; 11 specs never implemented (gaps) |
| 6 | SPEC-FE-009/010 shared-key invalidation | NOT EXERCISED — key contract intact, but neither surface exists |
| 7 | No confirmed-unbacked endpoint called | PASS (static + observed at runtime) |

## Method and environment

- Frontend: `frontend/` (Next.js 15.5, React 19). Backend: `backend/` (FastAPI) against the live Postgres DB from `backend/.env` (it has no tenants/users/data rows).
- Route walk: Microsoft Edge headless (`msedge --headless=new --virtual-time-budget=8000–10000 --dump-dom --enable-logging=stderr`), which executes client JS, so client-rendered states and browser console output were captured. Deviation from the approved plan: the plan named Claude in Chrome with a `curl` fallback; Chrome tooling was unavailable in the session and headless Edge is a real browser, so it was used instead. HTTP status per route was additionally checked with `curl -L`.
- Two frontend builds were walked:
  - **Pass A** — built and served with `NEXT_PUBLIC_API_BASE_URL` unset (no `.env.local` exists).
  - **Pass B** — built with `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` set on the build process only (no env file written), served with `next start -p 5173` (the only origin the backend's CORS allows), backend `uvicorn app.main:app --port 8000`.
- Pass B's first attempt hit the backend's global `RateLimitMiddleware` (5 requests / 15 min per `.env`): GETs and CORS preflights returned **429**, and a 429 preflight carries no CORS headers, so the browser reported "Failed to fetch". Per the root CLAUDE.md ("override `RATE_LIMIT_LOGIN_ATTEMPTS` via the environment for that process only"), the backend was restarted with `RATE_LIMIT_LOGIN_ATTEMPTS=10000` and the walk repeated. This is a known backend issue (root CLAUDE.md, Security rules), not frontend drift.
- Both servers were stopped afterwards (ports 8000/5173 confirmed free).

## Scope 1 — Build, typecheck, lint

| Command (run in `frontend/`) | Raw result |
|---|---|
| `npx tsc --noEmit` | exit 0, no output |
| `npm run build` (env unset) | exit 0; `✓ Compiled successfully in 1194ms`; 14 static pages; routes `/`, `/_not-found`, `/analytics`, `/campaigns`, `/chat`, `/customer`, `/dashboard`, `/ecommerce`, `/integrations`, `/kb`, `/marketing`, `/workflows`, all `○ (Static)` |
| `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run build` | exit 0; the "Linting and checking validity of types ..." step printed no lint output |
| Lint | **Not run — no linter configured.** `package.json` scripts are only `dev`, `build`, `start`; no ESLint config file and no `eslint` package. `npx next lint` was deliberately not run (Next 15 prompts interactively and installs packages). |

**Gap (lint):** SPEC-FE-022 AC1 requires lint "reported clean, or every failure documented with cause". Cause: SPEC-FE-001 Non-functional rule (line 40) says "Do not hand-author an ESLint/Prettier config; if Next.js's own scaffolding produces a default one, leave it as-is" — none was produced, so none exists. Adding one would be new tooling, not drift restoration, so it is out of this spec's scope.

## Scope 2 — API base-URL env var

- Real name: `NEXT_PUBLIC_API_BASE_URL`, read in `frontend/lib/api/client.ts:58` at call time; no fallback host.
- SPEC-FE-003 AC1 (line 44): "apiFetch throws a clear, named error immediately if NEXT_PUBLIC_API_BASE_URL is unset" — **PASS**. Pass A (unset) rendered, e.g. on `/workflows`: `Failed to load workflows: NEXT_PUBLIC_API_BASE_URL is not set. Copy .env.local.example to .env.local and set it to the backend's base URL.` The same named message appeared on `/analytics` (revenue, top products) and `/integrations`.
- SPEC-FE-003 AC6 (line 49): `.env.local.example` contains exactly `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` — **PASS**.
- **AMBIGUITY (not decided):** SPEC-FE-022 Scope 2 says the app must "fail fast with a clear error **at startup** if it is unset". SPEC-FE-003 Functional Rule 1 (line 23) says the URL is "read … **at call time**. If it is unset, throw a clear error immediately" and its edge case (line 34) says apiFetch "throws immediately … without attempting any network request". The current code matches SPEC-FE-003 exactly: the app boots and every page renders; the error appears where an API call is made. Per SPEC-FE-022 Functional Rule 3 (prior specs' criteria are the source of truth) this passes, but SPEC-FE-022's own wording asks for different behavior. Needs a decision; no change made.

## Scope 3 — Routes

Real route segments (`frontend/app/(app)/`): dashboard, chat, ecommerce, marketing, customer, kb, campaigns, workflows, analytics, integrations.

### Unauthenticated (Pass A: env unset; Pass B: env set, real backend)

| Route | HTTP | Rendered `<h1>` | Shell | Active nav item | Console errors (A/B) | Data components (Pass B, real backend) |
|---|---|---|---|---|---|---|
| `/` | 200 | Dashboard (redirected) | yes | `/dashboard` | 0 / – | – |
| `/dashboard` | 200 | Dashboard | yes | `/dashboard` | 0 / 0 | none (stub) |
| `/chat` | 200 | Command Chat | yes | `/chat` | 0 / 0 | none (stub) |
| `/ecommerce` | 200 | E-Commerce Automation | yes | `/ecommerce` | 0 / 0 | none (stub) |
| `/marketing` | 200 | Marketing Automation | yes | `/marketing` | 0 / 0 | 4 cards each "Failed to load" (backend 401) |
| `/customer` | 200 | Customer Service | yes | `/customer` | 0 / 0 | none (stub) |
| `/kb` | 200 | Business Knowledge Base | yes | `/kb` | 0 / 0 | none (stub) |
| `/campaigns` | 200 | Campaign Wizard | yes | `/campaigns` | 0 / 0 | none (stub) |
| `/workflows` | 200 | Workflow Builder | yes | `/workflows` | 0 / 0 | "Failed to load workflows: Missing bearer token." |
| `/analytics` | 200 | Analytics | yes | `/analytics` | 0 / 0 | 4 cards "Failed to load"; "Failed to load revenue: Missing bearer token."; "Failed to load top products: Missing bearer token." |
| `/integrations` | 200 | Integrations | yes | `/integrations` | 0 / 0 | "Failed to load integrations: Missing bearer token." |
| `/no-such-page` | 404 | 404 | **no** (correct: 404 is outside the `(app)` group) | – | 0 / – | – |

Backend access log for Pass B (rate limit raised): exactly 8 endpoints requested, each `GET` twice (the SPEC-FE-003 default `retry: 1`) → 401, each preflight `OPTIONS` → 200:
`/api/v1/ads/ctr-7d`, `/api/v1/analytics/sales`, `/api/v1/analytics/top-products`, `/api/v1/campaigns/metrics`, `/api/v1/integrations`, `/api/v1/orders/metrics`, `/api/v1/scheduled-posts/count`, `/api/v1/workflows`. Backend response confirmed: `401 {"detail":"Missing bearer token."}` with `access-control-allow-origin: http://localhost:5173`.

Result: **PASS** — every route resolves and renders with no unhandled runtime error or console error; SPEC-FE-002 AC1 (redirect), AC2 (titles/subtitles, checked in source for all 10), AC3 (sections/order/glyphs — `components/shell/sidebar.tsx:13–38`), AC4 (active item — verified per route above), AC5 (topbar inert — `components/shell/topbar.tsx`, no handlers) hold. SPEC-FE-003 AC4 (routes render after provider) and AC5 (no Authorization header while `getAuthToken()` is null — the backend answered "Missing bearer token." to every request) **PASS**.

### Authenticated — **BLOCKED**

SPEC-FE-004 (login) is not implemented: no `/login` route exists, and `frontend/lib/auth/token.ts:15` still returns `null` unconditionally (SPEC-FE-003 placeholder). There is no supported way to authenticate the frontend. Injecting a token by other means would be a workaround, which SPEC-FE-022 forbids. The live DB also has no users. Recorded as a gap; execution stops for this item.

## Scope 4 — Auth guard vs SPEC-FE-004

- **FAIL — not implemented.** Nothing redirects signed-out users: every app route rendered while unauthenticated (Scope 3). SPEC-FE-004 AC1–AC5 (lines 44–48) all fail for this reason: no login page, no token storage, no redirect, no logout.
- **Spec defect — truncated criterion:** SPEC-FE-004 AC6 (line 49) is cut off mid-sentence: "6. A 401 response from any backend call while a token is stored" — the file ends there. Its required behavior cannot be determined from the criterion itself. Not interpreted.
- **AMBIGUITY — conflicting redirect rule (not decided):** SPEC-FE-022 Scope 4 says "a successful login redirects back to the originally-requested route (or to dashboard if none was requested)". SPEC-FE-004 Functional Rule 3 and AC2 (line 45) say a successful login "redirects to /dashboard" — no return-to-original behavior. SPEC-FE-022 Scope 4 also says SPEC-FE-004's criteria are the source of truth. Moot until SPEC-FE-004 is built, but it must be resolved in SPEC-FE-004 or SPEC-FE-022 first.
- Backend note: backend login was realigned by SPEC-BE-036; the gap is frontend-only.

## Scope 5 — Required loading/error/empty states, per spec

### Specs with code — states confirmed present

| Spec | Required (spec line) | Code | Result |
|---|---|---|---|
| FE-012 Marketing cards | FR7 (l.24): each card its own loading + error; AC4 (l.40) independent | `components/marketing/summary-cards.tsx` `Card`: pending → "…", error → "—" + "Failed to load" | PASS, with **AMBIGUITY** below |
| FE-014 Reply draft panel | FR7 (errors inline without losing draft); edge cases | `components/customer/reply-draft-panel.tsx:128–134` (loading/error), `:143–156` (empty + Generate), `:137–141` (action errors) | Present, but the component is **not mounted anywhere** (see gaps) |
| FE-017 Workflows table | FR4 (l.20): loading / "No workflows yet" / inline error | `components/workflows/saved-workflows-table.tsx:37–47` | PASS (error observed live) |
| FE-019 Sales cards + chart | FR4 (fallback message); cards per FR2 | `components/analytics/sales-summary.tsx` `Card` (loading/error), `components/analytics/revenue-chart.tsx:73–83` (loading/error/fallback) | PASS (errors observed live) |
| FE-020 Top products | FR5 (l.21): loading / "No product data yet" / inline error | `components/analytics/top-products-table.tsx:44–66` | PASS, with **AMBIGUITY** below (error observed live) |
| FE-021 Integrations | Edge cases (l.25–26), AC5 (l.40) | `components/integrations/integrations-grid.tsx:82–104` | PASS, with **AMBIGUITY** below (error observed live) |

Shared-file drift check: `app/(app)/analytics/page.tsx` still renders `SalesSummaryCards` + `RevenueChart` (FE-019) with `TopProductsTable` added after them (FE-020); `lib/api/analytics.ts` / `lib/types/analytics.ts` still export every FE-019 symbol; `app/globals.css` still contains every class ported by FE-008/010/017/019/021 (FE-008's Scope classes all present). **No earlier spec's state handling was dropped.**

### Ambiguities recorded (not decided, no change made)

1. **FE-012 AC4** (l.40): "Each card's loading/error state is independent of the others." Active Campaigns and Avg. ROAS read one shared query (`summary-cards.tsx`, both `state={campaign}`), a documented choice because SPEC-BE-009 returns both numbers in one response — so those two cards load/fail together. Whether "independent" requires one request per card is not stated.
2. **FE-020 FR5** (l.21) "an inline error message if the fetch fails" and **FE-021** edge case (l.26) "The list fetch fails: show an inline error": both components keep already-loaded rows/cards when a *background refetch* fails and show no error in that case (`top-products-table.tsx:44`, `integrations-grid.tsx:83`). Whether a failed background refetch counts as "the fetch fails" is not stated. (FE-017/019 do the opposite: they replace data with the error.)
3. **FE-021 edge case** (l.25): "render an empty grid with a plain 'No integrations configured' message". The code renders the message without an `.integrations-grid` wrapper (`integrations-grid.tsx:84`). What an "empty grid" should contain visually is not stated. (Unreachable today: the backend always returns its 9 fixed providers.)

### Specs never implemented (gaps, not drift)

| Spec | Evidence | Reason |
|---|---|---|
| FE-004 | no `/login`; `lib/auth/token.ts:15` returns null | never built |
| FE-005 | `app/(app)/dashboard/page.tsx` is the FE-002 stub; no `components/dashboard/`, `lib/api/dashboard.ts` | never built. **Spec defect:** `SPEC-FE-005.md` has no Acceptance Criteria section (28 lines, ends inside Functional rules) — nothing to verify against |
| FE-006, FE-007 | same dashboard stub | never built |
| FE-008 | no `components/chat/`; `app/(app)/chat/page.tsx` is the stub. `lib/api/orchestrator.ts` / `lib/types/orchestrator.ts` exist (data layer only). AC1 CSS classes: PASS | UI never built |
| FE-009 | no plan card | never built |
| FE-010 | `lib/api/approvals.ts` / `lib/types/approvals.ts` exist (data layer only); no panel | UI never built |
| FE-011 | no `components/ecommerce/`, `lib/api/products.ts` | never built |
| FE-013 | customer page is the stub | blocked by backend: `GET /conversations` returns only `id, channel, status, assigned_user_id` (no customer name/topic/timestamp); live `conversation_status` enum is open/pending/resolved/archived, not the mockup's badge states |
| FE-014 | panel/API/types exist, not mounted | depends on FE-013 |
| FE-015 | kb page is the stub | **backend gap:** `GET`/`PATCH /api/v1/brand` return 500 and `POST /api/v1/faqs` returns 500 on the live DB (models map columns the live tables lack — SPEC-BE-012/013 not implemented); `PUT /brand` does not exist (405); FAQ schemas have no `channels` |
| FE-016 | campaigns page is the stub | never built (plan awaiting approval; environment blocks generation: `LLM_PROVIDER=mock` → 503, no products) |
| FE-018 | no canvas | **backend gap:** no `GET /api/v1/workflows/{id}` and no `POST /api/v1/workflows/{id}/test` (SPEC-BE-034 not implemented and conflicts with the live `run_status`/`actor_type` enums) |

FE-001 AC3/AC6 and FE-002 AC7 describe their own intermediate states and are superseded by later specs by design (not drift).

## Scope 6 — SPEC-FE-009/010 shared query-key invalidation

- Key constants (`frontend/lib/api/approvals.ts:26–31`): `approvalKeys.all = ["approvals"]`, `approvalKeys.pending = ["approvals","pending"]`, `approvalKeys.decisions = ["approvals","decisions"]`. The documented contract (`approvals.ts:20–25`): after any approve/reject from either surface, invalidate `approvalKeys.all`. TanStack Query matches by prefix, so that invalidates every `["approvals", …]` query. `approvals.ts:1–7` states it is the only module calling `/api/v1/approvals/*`, and the source search confirms it.
- `lib/api/orchestrator.ts` defines no approval keys and makes no approval calls (it only has `fetchMessages` / `sendMessage` on `/api/v1/orchestrator/messages`).
- Every `queryKey` / `invalidateQueries` / `setQueryData` in `app/`, `components/`, `lib/` was listed: **none references `approvalKeys`**. Neither the FE-009 plan card nor the FE-010 panel exists, so no approve/reject mutation exists to invalidate anything.
- Result: **NOT EXERCISED — the key contract is defined and intact, but it has no consumers.** This is not reported as a pass. SPEC-FE-009 AC2 and SPEC-FE-010 AC2 cannot be verified until those UIs exist.
- The backend routes the contract targets all exist (`/api/v1/approvals/pending`, `/{approval_id}/approve|reject`, `/groups/{subject_id}/approve|reject`).

## Scope 7 — Confirmed-unbacked endpoints

- Every path in `frontend/lib/api/*.ts` (20 method+path pairs) was checked against the running backend's route table: **all 20 exist**. No `fetch`/`apiFetch` call exists outside `lib/api/`.
- Not called anywhere (static search + Pass B access log): no campaign list/create/launch, no `/api/v1/content/*`, no workflow create/version/detail/test, no integrations connect/OAuth endpoint. At runtime only the 8 GET endpoints listed in Scope 3 were requested.
- Unbacked UI renders as absent or inert, per its original spec:
  - Marketing: no Active Campaigns table or Content Calendar (`app/(app)/marketing/page.tsx`), FE-012 AC5 PASS.
  - Campaign Wizard: stub title only (FE-016 not built), so nothing is fabricated.
  - Workflows: "+ New Workflow" and "Version History" have no handler (`app/(app)/workflows/page.tsx:15–20`), with the comment at `:11–13`. There is no canvas.
  - Analytics: "Explain this ⓘ" has no handler (`components/analytics/revenue-chart.tsx:68–70`), with the comment at `:66–67`.
  - Integrations: Manage, Reconnect and Connect have no handler (`components/integrations/integrations-grid.tsx:70–72`), with the comment at `:67–69`.
- Every `onClick` in the app belongs to the Analytics tab switch (`app/(app)/analytics/page.tsx:32`) or the unmounted FE-014 panel, and those FE-014 handlers call its real, existing draft endpoints.
- Result: **PASS.**

## Backend gaps found (reported only; no frontend code calling them was touched)

1. Brand settings (`/api/v1/brand`, SPEC-BE-012) returns 500 on the live DB. There is no `PUT` route.
2. FAQs (`POST /api/v1/faqs`, SPEC-BE-013) returns 500 on the live DB. The FAQ schemas have no `channels` field.
3. There's no `GET /api/v1/workflows/{id}` and no `POST /api/v1/workflows/{id}/test`. SPEC-BE-034 was never implemented, and it conflicts with the live `run_status` and `actor_type` enums and the required `workflow_version` and `correlation_id` columns.
4. `GET /api/v1/conversations` is too thin for FE-013 and FE-014: it has no customer name, topic or timestamp, and its status values don't match the mockup's badges.
5. The global `RateLimitMiddleware` (5 requests per 15 minutes) returns 429 on normal page loads and on CORS preflights, which the browser reports as a network failure. A signed-in dashboard would trip it immediately. Already listed in the root CLAUDE.md.

## Fixes

**None applied.** The audit found no mechanical regression, meaning no dropped state, stale query key or env-var typo that an original spec clearly requires restoring:
- Every failure above is either a spec that was never implemented (new work, not drift), a backend gap (Functional Rule 5), or an ambiguity (Functional Rule 2).
- The one near-candidate, wrapping FE-021's zero-integrations message in an `.integrations-grid` element, depends on the recorded ambiguity 3, so it wasn't applied.

## Decisions needed

1. **Scope 2:** should the missing environment variable fail at app startup (SPEC-FE-022), or when an API call is made (SPEC-FE-003, which the current code follows)?
2. **SPEC-FE-004:** repair criterion 6, which is cut off, and settle the post-login redirect (always `/dashboard`, or back to the page originally requested).
3. **SPEC-FE-005:** restore its missing Acceptance Criteria section.
4. **The three Scope 5 ambiguities:** FE-012 "independent" cards, FE-020/021 errors when a background refetch fails, and FE-021's "empty grid".
5. **Linting:** add a linter under a new spec, or keep the SPEC-FE-001 rule of not writing one.
