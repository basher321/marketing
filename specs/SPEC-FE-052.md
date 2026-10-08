# SPEC-FE-052: Organic — Connect with OAuth, token status, and "What's working"

Status: IMPLEMENTED (code, 2026-10-03). `npx tsc --noEmit` and `next build` are clean (the new route `/marketing/organic/accounts/callback/[flow]` builds). **Pending:** E2E acceptance 1–5 (needs the live DB). Requested by the user (items 12 and 13). Backend: SPEC-BE-080 (OAuth connect, token status) and SPEC-BE-081 (insights). Builds on SPEC-FE-050.

## Changes
### 1. Connected Accounts (`/marketing/organic/accounts`)
Each platform card gets:
- **Connect with Facebook / TikTok / LinkedIn** (Instagram's card says "Connect with Facebook" too: Instagram comes with its Page). It calls `GET /social/oauth/{flow}/connect` and sends the browser to `login_url`. It's shown only when `oauth_available`; otherwise the card says "Sign-in isn't set up on this server; paste a token in Integrations." **Reconnect** replaces Connect when the status is `expired`/`error` or `token_status` is `expired`/`expiring_soon`.
- **Status details:**
  - connected via (Sign-in / Pasted token);
  - account ID;
  - granted permissions (collapsed list);
  - token status (Valid / Expires soon / Expired / Doesn't expire / Unknown), with `token_expires_at` and "reconnect by" when known;
  - last checked;
  - last results sync;
  - the last error.
- "Manage / test in Integrations" and "Use my Meta connection" stay.

### 2. OAuth callback page (new route `/marketing/organic/accounts/callback/[flow]`)
- Reads `code`, `state` (or the platform's `error` / `error_description`) and posts them once to `POST /social/oauth/{flow}/callback`.
- **meta / linkedin:** shows the returned choices (Page with avatar and linked Instagram, or company pages). For meta, a checkbox "Also connect Instagram @handle" is checked by default when the Page has one. **Use this** → `POST /social/oauth/{flow}/select` → back to Accounts, with the accounts query invalidated.
- **tiktok:** the callback saves directly → back to Accounts.
- Errors show the backend's message with a "Back to Connected Accounts" link. A denied sign-in shows the platform's reason. Tokens never reach the browser.

### 3. "What's working" (Organic dashboard and Organic Analytics)
- A card fed by `GET /organic/insights?days=60`: the `lines` as a list, best hours per platform (local time), best format, and the top posts with links.
- With `has_data=false`, it shows the reason.
- On Organic Analytics the card follows the page's range selector (30d → `days=30`, 90d → 90; 7d uses 30, since the backend minimum is 30).
- The content editor shows "Written with your recent results in mind" when an AI content has `performance_used`.

## Acceptance (E2E against the running backend and the live DB, `META_FAKE_TRANSPORT=true`)
1. With the server app credentials set (fake values), each card shows its Connect button; Connect navigates to the platform URL returned by the backend (checked by intercepting the navigation).
2. Opening `/marketing/organic/accounts/callback/meta?code=ok&state=<state from connect>` lists the fake Page with its Instagram account; Use this → the Accounts page shows Facebook and Instagram connected via Sign-in, with account IDs, permissions and "Doesn't expire".
3. LinkedIn via the callback → company page choice → connected, token expiry shown. TikTok → connected directly, "reconnect by" shown.
4. A reused state shows the backend's error; `?error=access_denied` shows the denial.
5. Dashboard: with no results the card shows the reason; with seeded results (SPEC-BE-081 seed) it shows the Instagram lines and best hours.
6. `npx tsc --noEmit` and `next build` are clean.

## Target files
- `frontend/app/(app)/marketing/organic/accounts/page.tsx`
- New `frontend/app/(app)/marketing/organic/accounts/callback/[flow]/page.tsx`
- `frontend/app/(app)/marketing/organic/page.tsx` and `frontend/app/(app)/marketing/organic/analytics/page.tsx` (insights card)
- `frontend/components/organic/content-editor.tsx` (the `performance_used` note)
- New `frontend/components/organic/insights-card.tsx`
- `frontend/lib/api/social.ts`, `frontend/lib/types/social.ts`, `frontend/lib/api/organic.ts`, `frontend/lib/types/organic.ts`

This touches more files than the per-spec rule (one page + 3 files) because it spans two backend specs. It's listed here so the deviation is explicit.

## Out of scope
Several accounts per platform, revoking at the platform, X / YouTube / Pinterest.
