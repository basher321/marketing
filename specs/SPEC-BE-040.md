# SPEC-BE-040 / SPEC-FE-025: Password Reset + Show/Hide Password

Status: IMPLEMENTED (2026-09-29), at the user's request ("password reset and option to see password toggling eye").

## Purpose
Users who forget their password have no way back in; only a database edit helps. Password fields also can't be revealed, so typos (e.g. a pasted trailing space) go unnoticed.

## Backend contract
- `POST /api/v1/auth/password-reset/request` body `{email, tenant_slug}` → **202** `{"message": "If an account exists for that email, a reset link has been sent."}`.
  - The response is identical whether or not the account exists (no account enumeration).
- `POST /api/v1/auth/password-reset/confirm` body `{token, new_password}` → **200** `{"message": "Your password has been reset. You can now sign in."}`.
  - Invalid, expired or used token → **400** "This reset link is invalid or has expired."
  - Weak password → **422**, with the same policy as registration.

## Backend rules
1. A token is issued only for an existing, non-deleted, `active` user of an `active`/`trial` tenant. Otherwise nothing happens, and the same 202 is returned.
2. **Token:** 32 random bytes (`secrets.token_urlsafe`). Only its **SHA-256 hash** is stored in `password_reset_tokens` (`token_hash` UNIQUE), and the raw token exists only in the link. It expires after **30 minutes** and is single-use (`used_at`).
3. **One active token per user:** a new request marks the user's earlier unused tokens as used.
   - Anti-spam: if the user got a token less than **60 seconds** ago, no new token or email is created, and the same 202 is returned.
4. **Link:** `{FRONTEND_BASE_URL}/reset-password?token=<raw>`. `FRONTEND_BASE_URL` is a new setting, default `http://localhost:3000`.
5. **Email:** sent with `utils/email_sender.send_email`.
   - When SMTP is **not configured** (empty host, or placeholder user/password `changeme`), the email, including the link, is written to the backend console at WARNING level. This is dev mode, and the only place the raw token appears.
   - A send failure is logged, never shown to the requester (still 202).
6. **Confirm** runs in one transaction:
   - The token row is locked (`FOR UPDATE`); it must be unused, unexpired, and belong to a non-deleted user.
   - The user gets the new bcrypt `password_hash`, and `failed_login_attempts = 0`, `locked_until = NULL` (a reset unlocks a SPEC-BE-039 lock).
   - The token is marked used, along with any other unused tokens of the user.
   - One `audit_log` row: `user.password_reset`, with the actor = the user.
7. Both endpoints are unauthenticated. User status is not changed: a disabled user's password can change, but login still refuses them.

## Frontend
- **Show/hide eye** (`components/auth/password-input.tsx`, new) is used on every password field (login, reset).
  - It's a real `<button type="button">` with `aria-label` "Show password" / "Hide password" and `aria-pressed`, switching the input between `password` and `text`.
  - Inline SVG eye icon, no dependency.
- **Login page:** a "Forgot password?" link → `/forgot-password`.
- **`/forgot-password`:** Organization + Email → request → shows the backend's generic message. Links back to sign in.
- **`/reset-password?token=…`:** New password + Confirm password, with a client-side match check. Submit → confirm → success message with a "Sign in" link. The backend's real errors are shown, including the password-policy messages from a 422.
- These pages sit outside the app shell and the route guard (like `/login`).

## Acceptance criteria
1. Request for an existing user → 202, 1 token row (hashed, 30-minute expiry), link printed in dev mode. For an unknown email or tenant → the same 202 and no row.
2. A second request within 60s → no new row. After 60s → a new row, and the old token becomes unusable.
3. Confirm with a valid token → 200; login with the new password works and the old one fails. Reusing the token → 400; an expired token → 400; a weak password → 422 with the policy text.
4. Confirm clears a lockout. One audit row.
5. Browser: the eye reveals and hides each password field. Forgot → link (from the console) → reset page → new password → sign in works.

## Target files
- backend/app/api/v1/auth.py, backend/app/schemas/auth.py, backend/app/services/auth_service.py, backend/app/config.py, backend/app/utils/email_sender.py, backend/.env, specs/SPEC-BE-003.md (amendment)
- frontend/components/auth/password-input.tsx (new), frontend/app/login/page.tsx, frontend/app/forgot-password/page.tsx (new), frontend/app/reset-password/page.tsx (new), frontend/lib/api/auth.ts, frontend/lib/types/auth.ts
