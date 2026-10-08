# SPEC-FE-024: Stay Logged In — Silent Token Refresh

Status: IMPLEMENTED (2026-09-29). Follow-up promised by SPEC-FE-004 ("silent refresh is a follow-up spec").

## Purpose
The access token lasts 15 minutes and SPEC-FE-004 stored only it, so every user was sent back to /login every 15 minutes. That's not acceptable for a production app.

## Contract (backend, unchanged)
`POST /api/v1/auth/refresh` with body `{refresh_token}` → 200 `{access_token, refresh_token, token_type}`; invalid or expired → 401. The refresh token lives 7 days (`JWT_REFRESH_TOKEN_EXPIRE_DAYS`), and each refresh returns a new one, so an active user stays signed in.

## Functional rules
1. `lib/auth/token.ts` also stores the refresh token (`getRefreshToken` / `setRefreshToken`). `clearAuthToken()` clears **both**. This reverses SPEC-FE-004's "access token only" decision now that refresh logic exists. It's the same localStorage/XSS tradeoff, documented in the file.
2. Login stores both tokens.
3. `apiFetch`: when a request that carried a token gets **401**, and the path is not under `/api/v1/auth/`, it:
   - calls `/auth/refresh` **once** with the stored refresh token, shared by all concurrent 401s (one in-flight refresh promise), and stores the new pair;
   - retries the original request **once** with the new access token.
   If the refresh fails or no refresh token exists, the original 401 is thrown unchanged, and SPEC-FE-004's 401 handler clears the session and goes to /login, exactly as before.
4. No refresh loop: a retried request is never refreshed again.
5. Logout clears both tokens (unchanged call site: `clearAuthToken()`).

## Non-functional
- No new dependency. `apiFetch`'s public signature is unchanged.
- The refresh call uses `fetch` directly inside `client.ts`, so it can't recurse into `apiFetch`.

## Acceptance criteria (real browser, live backend)
1. Login stores both tokens.
2. With an expired or invalid access token but a valid refresh token, navigating a data page loads its data without leaving the page, and both tokens are replaced with new ones.
3. With both tokens invalid → redirected to /login and both cleared.
4. Several concurrent 401s trigger exactly one refresh call.
5. Logout clears both tokens.

## Target files
- frontend/lib/auth/token.ts
- frontend/lib/api/client.ts
- frontend/app/login/page.tsx
