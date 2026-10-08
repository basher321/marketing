# SPEC-FE-004: Authentication (login page + token storage + route protection)

## Purpose
Implement real authentication: a login page that calls the backend's actual, already-implemented auth endpoint, storage of the resulting token that fills in SPEC-FE-003's getAuthToken() placeholder, and protection of the app shell's 10 routes so only an authenticated user can reach them.

## Scope
In scope:
- A login page (route /login) with whatever fields the real backend auth contract requires, submitting to that real endpoint via apiFetch.
- Storing the resulting token and filling in lib/auth/token.ts's getAuthToken()/setAuthToken()/clearAuthToken().
- Route protection: the app shell redirects to /login when no valid token is present; a successful login redirects to /dashboard.
- Logout via the topbar's existing avatar element (previously non-functional per SPEC-FE-002).

Explicitly NOT being built by this spec:
- 2FA (the architecture doc mentions it; if the real backend auth endpoint requires it, stop and report rather than building around it)
- OAuth authorization-code flow / third-party SSO, unless the real backend auth endpoint is actually built that way — confirm before assuming a simple credential login
- Refresh-token rotation / silent-refresh-before-expiry logic — this spec only stores whatever the login response returns
- Password reset / "forgot password" — not in the mockup, not in scope
- Any change to the 10 existing pages' content beyond gating access to them

## Contract
Whatever the backend's real, already-implemented auth endpoint contract is. Do not assume field names (e.g. "email"/"password", "access_token") — confirm the exact path, request shape, and response shape from the backend's actual code before writing any login-page code, per Functional Rule 1.

## Functional rules
1. Before writing any code, read the backend repo's actual auth endpoint implementation (app/api/v1/auth.py, its schema file, and CLAUDE.md) to determine: the exact path, exact request body fields, exact response body fields (token field name(s), any expiry info), and whether 2FA or any additional step is required. If this cannot be determined confidently — the endpoint doesn't exist yet, or its shape is ambiguous — stop and report rather than fabricating a contract.
2. Login page at /login: a form with exactly the fields the real backend contract requires — no extra fields, no invented "remember me" checkbox or anything not shown in the mockup or required by the backend. Submitting calls apiFetch against the real endpoint.
3. On success, store the token(s) exactly as the backend returns them (see Functional Rule 4) and redirect to /dashboard.
4. Token storage: use localStorage for the access token. Document this as a deliberate, simple tradeoff (XSS exposure vs. implementation simplicity) in a code comment, to be revisited if a later security-hardening spec requires httpOnly cookies instead. Update lib/auth/token.ts's getAuthToken() to read the real stored token, replacing SPEC-FE-003's always-null placeholder, and add setAuthToken()/clearAuthToken() in the same file for login/logout to use.
5. On failure (a non-2xx response from the login call), display the real error message carried by the ApiError that apiFetch throws (per SPEC-FE-003) inline on the login form — do not substitute a fabricated generic "invalid credentials" message if the backend's real error body says something more specific.
6. Route protection: in app/(app)/layout.tsx (already wrapping the QueryClientProvider from SPEC-FE-003), check for a stored token; if absent, redirect to /login before rendering the sidebar/topbar/page content. This check runs client-side only — a server-side/middleware-based check is out of scope, deferred if needed later.
7. /login is not wrapped by the app/(app) shell — no sidebar/topbar on it, since the mockup itself has no login page to copy from (it starts already-authenticated at the Dashboard).
8. Logout: clicking the topbar's existing avatar element (from SPEC-FE-002, previously non-functional) now calls clearAuthToken() and redirects to /login. Document that this repurposes the previously-decorative avatar since the mockup has no separate logout control.

## Edge cases
- A stored token that the backend later rejects (any apiFetch call returns 401): clear the stored token and redirect to /login. This is handled at the route-protection/error-boundary layer, not inside apiFetch itself — apiFetch's behavior from SPEC-FE-003 is otherwise unchanged. Document this boundary clearly in code comments.
- Empty-field submission: rely on standard HTML5 required-field validation; no custom validation logic beyond that.
- Multiple tabs open simultaneously: no cross-tab sync is built — out of scope.

## Non-functional rules
- No 2FA, OAuth code flow, or refresh-token rotation logic in this spec.
- Must not change SPEC-FE-002's 10 existing page contents beyond gating access, and must not change SPEC-FE-003's apiFetch behavior beyond what Functional Rules 6 and the 401 edge case require.
- No new dependency beyond what's already installed, unless the real backend auth contract genuinely requires one — if so, stop and report rather than guessing.

## Acceptance criteria
1. Visiting any of the 10 app routes while unauthenticated redirects to /login.
2. Submitting valid credentials against the real backend auth endpoint logs in, stores the token, and redirects to /dashboard.
3. Submitting invalid credentials shows the real error message from the backend's actual response, not a fabricated generic one.
4. After login, refreshing the browser keeps the user authenticated.
5. Clicking the topbar avatar logs the user out, redirects to /login, and a subsequent visit to any app route redirects to /login again.
6. A 401 response from any backend call while a token is stored clears the stored token and redirects to /login. *(Repaired 2026-09-29: the original criterion was truncated mid-sentence; completed from this spec's own 401 edge case.)*

## Target files
*(Added 2026-09-29 during plan review — the original spec had no Target files section.)*
- lib/auth/token.ts
- lib/types/auth.ts (new)
- lib/api/auth.ts (new)
- app/login/page.tsx (new)
- app/(app)/providers.tsx — hosts the client-side route guard and the 401 handler. Functional Rule 6 names app/(app)/layout.tsx, but that is a server component and cannot read localStorage; providers.tsx is the client component layout.tsx already wraps every (app) route in.
- components/shell/topbar.tsx
- app/globals.css — ports the mockup's .form-row rules verbatim for the login form.

## Resolved decisions (plan review, 2026-09-29)
- Only the access token is stored; the refresh token is not persisted (no refresh logic exists yet, so storing it would only widen XSS exposure).
- The 15-minute access-token lifetime is accepted; silent refresh is a follow-up spec.
- Post-login redirect is always /dashboard (Functional Rule 3).
- Backend CORS_ORIGINS gains http://localhost:3000 so `npm run dev` on its default port works.
