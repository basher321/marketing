# SPEC-BE-039: Login Protection — Per-Account Lockout + Failure-Only IP Limit

Status: IMPLEMENTED (2026-09-29). The user asked for the 15-minute login wall to be replaced with production-grade protection.

## Purpose
The previous login protection blocked a whole IP for 15 minutes after any 5 login attempts, successful ones included. A normal user testing the app was locked out. Production systems instead slow down **password guessing against an account**, and never punish successful logins.

## Scope
In scope: `POST /api/v1/auth/login` protection only.
Not in scope: CAPTCHA, email alerts on lockout, admin unlock UI, password reset, distributed (Redis) limiter storage.

## Functional rules
1. **Per-account lockout** (live `users.failed_login_attempts` int NOT NULL default 0, `users.locked_until` timestamptz):
   - A wrong password for an existing, non-deleted user of the tenant increments `failed_login_attempts` atomically (`UPDATE … SET n = n + 1 RETURNING n`).
   - When the count reaches `LOGIN_MAX_FAILED_ATTEMPTS` (default 5), `locked_until = now + min(2^(count − max) minutes, LOGIN_LOCKOUT_MAX_MINUTES)`. The lock is 1 min at the 5th failure, 2 at the 6th, 4 at the 7th, 8 at the 8th, then capped at 15 (default).
   - The attempt that triggers the lock gets **429** "Too many failed attempts. Try again in N seconds." (N = whole seconds until `locked_until`, rounded up).
   - While `locked_until > now`, the password is **not checked at all**, and the response is the same 429 with the remaining seconds. This prevents guessing during the lock.
   - A **successful** login resets `failed_login_attempts = 0` and `locked_until = NULL`, alongside the existing `last_login_at` write.
   - Unknown tenant or unknown email keep returning the generic 401 "Invalid credentials." (no row to count; the IP limit below covers them).
   - Known tradeoff: a locked account's 429 reveals that the account exists. This is accepted, as common practice, so the real user learns why they can't log in.
2. **IP safety net** (`RateLimitMiddleware`, `POST /api/v1/auth/login` only):
   - Only **failed** login responses (401) are recorded per client IP. A 200 is never counted.
   - Once an IP has `RATE_LIMIT_LOGIN_ATTEMPTS` failures (default 20) within `RATE_LIMIT_LOGIN_WINDOW_MINUTES` (default 5), further login requests from it get 429 "Too many failed login attempts from this network. Try again in N seconds." until the oldest failure leaves the window.
3. The `users.status = 'locked'` value (admin lock, SPEC-BE-036) is unrelated and unchanged.
4. The existing 401 messages, the 2FA refusal, and the invited/disabled/suspended rules are unchanged.

## Configuration (SPEC-BE-003 amendment)
- `RATE_LIMIT_LOGIN_ATTEMPTS` (default 20): now *failed* logins per IP per window.
- `RATE_LIMIT_LOGIN_WINDOW_MINUTES` (default 5).
- New: `LOGIN_MAX_FAILED_ATTEMPTS` (default 5), `LOGIN_LOCKOUT_MAX_MINUTES` (default 15).

## Acceptance criteria
Verified on the live DB in a rolled-back transaction with real HTTP:
1. 4 wrong passwords → 401 each; the 5th → 429 with a wait of about 60s; `locked_until` is set.
2. While locked, the **correct** password → 429 (not verified); the counter doesn't move.
3. After the lock expires, the correct password → 200, and the counter and lock are cleared.
4. Escalation: the 6th failure locks 2 min, the 7th 4 min; the cap holds at 15 min.
5. 30 successful logins in a row → all 200 (successes never count).
6. 20 failed logins from one IP (unknown emails) → the 21st request → 429; a lock on one account never affects another account.
7. Unknown email or tenant → 401 "Invalid credentials.", no counter written anywhere.

## Target files
- backend/app/models/user.py (map `failed_login_attempts`, `locked_until`)
- backend/app/services/auth_service.py
- backend/app/config.py
- backend/app/core/rate_limiter.py
- backend/app/middleware/rate_limit_middleware.py
- backend/.env (values)
- specs/SPEC-BE-003.md (amendment note)
