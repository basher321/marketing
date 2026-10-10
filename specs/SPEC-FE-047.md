# SPEC-FE-047: Frontend production hardening from the SQA review

Status: IMPLEMENTED and verified 2026-10-02 (approved by the user). See **Execution log** at the end. Backend counterpart: SPEC-BE-071.

## Findings
| # | Severity | Finding (evidence) |
|---|---|---|
| G1 | High | The frontend sends no security headers (no CSP, X-Frame-Options, HSTS, nosniff or Referrer-Policy), and announces `X-Powered-By: Next.js`. |
| G2 | Blocker (npm audit) | postcss ≤ 8.5.22 (high: XSS in stringify, source-map file disclosure), pulled in through `next`. |
| G3 | High | Logout only clears local storage; the refresh token stays valid on the server. SPEC-BE-071 adds revocation, and the client must send the token. |
| G4 | Medium | The production build (`next build`) can't be verified while `next dev` uses `.next`. |
| G5 | Low | The header search box has no accessible label (1 unlabeled field on every page). |

## Changes
1. **G1 + G4 `next.config.mjs`**
   - `poweredByHeader: false`.
   - `headers()` for all routes:
     - `X-Frame-Options: DENY`;
     - `X-Content-Type-Options: nosniff`;
     - `Referrer-Policy: strict-origin-when-cross-origin`;
     - `Permissions-Policy: camera=(), microphone=(self), geolocation=()` (microphone for this site only since SPEC-FE-062 Amendment A; it was `microphone=()`).
   - **Production only:**
     - `Strict-Transport-Security: max-age=31536000; includeSubDomains`;
     - a `Content-Security-Policy` allowing self, the API origin from `NEXT_PUBLIC_API_BASE_URL`, `data:`/`blob:` images and media, inline styles (used by the shell) and Next's inline scripts; `frame-ancestors 'none'`.
   - **Dev** keeps no CSP, because Next dev needs `eval`.
   - `distDir` can be overridden with `NEXT_BUILD_DIR`, so a production build can be checked without touching the dev server's `.next` (default unchanged).
2. **G2 `package.json`:**
   - `next` updated to the latest 15.5 patch;
   - an `overrides` entry forces `postcss` ≥ 8.5.23;
   - `npm audit --omit=dev` must report 0 high/critical.
3. **G3 `lib/auth/token.ts` + `components/shell/topbar.tsx`:** logout calls `POST /auth/logout` with the refresh token (best effort; local tokens are cleared whatever the answer), then goes to `/login`.
4. **G5 `components/shell/topbar.tsx`:** `aria-label="Search"` on the header search box (still inert, as documented).

## Acceptance
1. `npx tsc --noEmit` passes.
2. `NEXT_BUILD_DIR=.next-prodcheck npm run build` succeeds, and the check directory is deleted afterwards.
3. The production server from that build sends the security headers and CSP with no `X-Powered-By`; dev sends the basic headers.
4. The browser smoke of all 22 pages still passes in dev, with no console errors.
5. Logout revokes: after logout, the old refresh token gets 401 from `/auth/refresh`.
6. 0 unlabeled fields from the shell.
7. `npm audit --omit=dev` reports 0 high/critical.

## Files
`frontend/next.config.mjs`, `frontend/package.json` (+ `package-lock.json`), `frontend/lib/auth/token.ts`, `frontend/components/shell/topbar.tsx`.

## Execution log (2026-10-02)

### Files changed
- `frontend/next.config.mjs`: G1/G4 as specified.
- `frontend/package.json` + `package-lock.json`:
  - next ^15.5.26 → ^15.5.27;
  - `"overrides": {"postcss": "$postcss"}`, so next's nested postcss 8.4.31 → 8.5.28.
- `frontend/components/shell/topbar.tsx`: G3 and G5.
  - Logout calls `POST /api/v1/auth/logout` with the refresh token through `apiFetch` (best effort), then clears the tokens.
  - The search box gets `aria-label="Search"`.
- `frontend/app/signup/page.tsx`, `frontend/app/reset-password/page.tsx`: the password hint now reads "At least 10 characters, with an uppercase letter, a lowercase letter and a digit; not a common password." This matches SPEC-BE-071 F11; both pages were added to the scope here.

### Deviations
- **`lib/auth/token.ts` is unchanged.** The logout call lives in `topbar.tsx`, because putting it in `token.ts` would create a circular import with `lib/api/client.ts`. The existing silent refresh already stores the rotated pair, with one refresh at a time.
- **Build-check side effect:** `next build` with `NEXT_BUILD_DIR` rewrote `tsconfig.json` and `next-env.d.ts` to point at the check directory. Both were restored byte-for-byte from backups, and `.next-prodcheck` was deleted. Their timestamps changed; their content didn't.

### Results
1. `npx tsc --noEmit` passes.
2. The production build in `.next-prodcheck` passed, and the directory was deleted.
3. Headers:
   - **Production** (`next start` from that build): X-Frame-Options, nosniff, Referrer-Policy, Permissions-Policy, HSTS and the CSP; no `X-Powered-By`.
   - **Dev:** the 4 basic headers; no CSP or HSTS; no `X-Powered-By`.
4. A headless Edge E2E against the live backend and DB passed 25 of 25 checks, using a temporary tenant that was deleted afterwards:
   - the 4 public pages and the 14 app pages render with no console errors;
   - the sign-up hint text is shown;
   - login works through the UI.
5. Logout clears local storage, and the old refresh token then gets 401 from `/auth/refresh`, so it's revoked server-side.
6. There are 0 unlabeled fields: the shell search box is labelled, and the dashboard has none.
7. `npm audit --omit=dev` reports 0 vulnerabilities. The moderate one was also cleared by next 15.5.27.

**Note:** `npm install` replaced `next` while the dev server was running, and that server exited. A dev server was started again on :3000 for the checks.
