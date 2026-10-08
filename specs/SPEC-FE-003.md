# SPEC-FE-003: API Client Foundation (fetch wrapper + TanStack Query provider)

## Purpose
Establish the single, shared way every subsequent frontend spec talks to the backend — a typed fetch wrapper pointed at the backend's base URL, and the TanStack Query provider wired into the app shell — so no later spec invents its own ad hoc fetch call or its own QueryClient instance.

## Scope
In scope:
- lib/api/client.ts: a typed apiFetch function that prepends the backend base URL, attaches an auth header when available, parses JSON, and throws a typed error on failure.
- A QueryClientProvider wrapping the app shell built in SPEC-FE-002, with explicit, documented default options.
- .env.local.example declaring the one env var this needs.
- A placeholder auth-token accessor that real login wiring will fill in later.

Explicitly NOT being built by this spec:
- Any specific data-fetching hook (use-products, use-orders, etc.) — those are added per-domain by later specs per SPEC-FE-002's CLAUDE.md convention
- Real login/authentication or real token acquisition/storage — left as a documented seam for the next dedicated auth/login spec
- Any pagination/list-response envelope type — each domain's real response shape is typed only once that domain's actual backend response is inspected by the spec wiring it

## Contract
Not a page-facing HTTP contract of its own — this is the shared client infrastructure other specs' contracts will be built on top of.
- `apiFetch<T>(path: string, init?: RequestInit): Promise<T>` — resolves with the parsed JSON body on a 2xx response (or `undefined` for a 204), rejects with a typed `ApiError` otherwise.

## Functional rules
1. lib/api/client.ts exports `apiFetch<T>(path, init?)`. Base URL is read from `process.env.NEXT_PUBLIC_API_BASE_URL` at call time. If it is unset, throw a clear error immediately naming the missing env var — do not fall back to a hardcoded default host.
2. Every request sets `Content-Type: application/json` and `Accept: application/json`; a plain object body is `JSON.stringify`'d. If the caller passes a `FormData` body, leave it and the headers untouched (no Content-Type override).
3. Attach `Authorization: Bearer <token>` only when `getAuthToken()` (new module lib/auth/token.ts) returns a non-null value. When it returns null, send no Authorization header at all.
4. `getAuthToken()` in lib/auth/token.ts is, for this spec only, a documented placeholder that always returns null. Add a prominent code comment stating that real token acquisition/storage is implemented by the upcoming auth/login spec, and that no call site of apiFetch should special-case "no token" behavior itself — they all just call apiFetch normally.
5. On a non-2xx response: attempt to parse the body as JSON, falling back to raw text if it isn't valid JSON, and throw a typed `ApiError` (defined in lib/types/common.ts: `{ status: number, message: string, body: unknown }`) rather than letting a raw Response or generic fetch rejection reach the caller.
6. On a 2xx response with an empty body (204), return `undefined` rather than attempting to parse JSON.
7. Create the `QueryClient` once, guarding correctly against React strict-mode double-invocation and server/client instantiation per TanStack Query's own Next.js App Router guidance, with explicit `defaultOptions: { queries: { staleTime: 30_000, retry: 1 } }`. Document in a code comment that these two numbers are a starting default any later spec may override per-query.
8. Wire the provider into app/(app)/layout.tsx from SPEC-FE-002 (directly, or via a new client component such as providers.tsx imported there) without changing any other behavior SPEC-FE-002 already established — sidebar, topbar, and all 10 routes must keep working identically.
9. .env.local.example contains exactly one line: `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` — an example/documentation value only, not an assertion about any real environment's actual backend URL.

## Edge cases
- apiFetch called before NEXT_PUBLIC_API_BASE_URL is set: throws immediately with a clear message naming the missing env var, without attempting any network request.
- Backend returns a non-JSON error body (e.g. an HTML error page from a proxy): ApiError.body is the raw text, ApiError.message falls back to the HTTP status text.
- Network failure (fetch itself rejects — DNS failure, connection refused): re-thrown as an ApiError with status 0 and the underlying error's message, so every caller can rely on catching exactly one error type.

## Non-functional rules
- No specific data-fetching hook is created by this spec.
- No new dependency beyond what SPEC-FE-001 already installed (TanStack Query is already present).
- Must not change SPEC-FE-002's sidebar, topbar, or route behavior in any visible way.

## Acceptance criteria
1. apiFetch throws a clear, named error immediately if NEXT_PUBLIC_API_BASE_URL is unset (verify by temporarily unsetting it).
2. A successful call to a real, already-running backend GET endpoint round-trips through apiFetch and returns typed JSON.
3. A call to a nonexistent path rejects with an ApiError carrying the real status code and parsed body, not a generic fetch exception.
4. The app renders identically to SPEC-FE-002's state (all 10 routes, sidebar, topbar) after the QueryClientProvider is wired in.
5. No Authorization header is sent while getAuthToken() returns null (verify in the browser network tab).
6. .env.local.example exists with exactly the one documented line.

## Assumptions
- The backend's actual local base URL/port is whatever the separate backend repo runs on; NEXT_PUBLIC_API_BASE_URL is left as a per-environment example value, not asserted as fact.
- Real token acquisition/storage (httpOnly cookie vs. localStorage vs. in-memory store) is an open decision left to the dedicated auth/login spec that comes next.
- No pagination/list-response envelope shape is assumed generically here.

## Target files
Extends SPEC-FE-001/002's project with new foundational files — an authorized exception since these are cross-cutting infra files, not yet a per-domain feature:
- lib/api/client.ts
- lib/auth/token.ts
- lib/types/common.ts
- app/(app)/layout.tsx (extended only to add the QueryClientProvider, without altering SPEC-FE-002's existing sidebar/topbar/routing logic)
- .env.local.example
