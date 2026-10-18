# SPEC-FE-070: One login per tab + safe token refresh across tabs (with a SPEC-BE-071 F7 amendment)

Status: IMPLEMENTED (2026-10-11).
- **Checks:** `tsc` is clean, and ruff/mypy are at the baseline.
- **Backend:** verified on the live DB, rolled back (8/8).
- **Browser E2E:** headless Chrome over the DevTools protocol against the running app, 9/9. It used 4 throwaway
  `e2e-fe070-*` companies, which were deleted afterwards.

## The problem

"we cant login to this software for multple user and multiple login"

1. **Several users in one browser.** Both tokens lived under two localStorage keys shared by every tab. A second user
   signing in replaced the first, and signing out in one tab signed out every tab.
2. **The same user in several tabs.** When the 15-minute access token ran out, each tab refreshed with the same refresh
   token. The loser presented an already-rotated token, which the backend treats as theft (SPEC-BE-071 F7), so it revoked
   **every** session of that user, other devices included. This happened on 2026-10-10 for the Super admin: 2 sessions
   were revoked in the same second.

**Decision (2026-10-11, "go ahead and recommend"):** one login per tab, plus both refresh fixes.

## Requirements

- **FR1 Storage (`lib/auth/token.ts`).**
  - **Pairs per user:** each user's pair is stored once, in localStorage `ai-orchestrator.session.<user id>`. The user
    id is the JWT `sub`; it only picks the slot, and the backend verifies the token.
  - **Which user a tab is:** sessionStorage `ai-orchestrator.tab_user`. It survives a reload and is copied when a tab is
    duplicated.
  - **New tabs:** a new tab pins `ai-orchestrator.last_user`, the latest sign-in in this browser.
  - **Signing in** (login or sign-up, via `setAuthToken` with another user's token) makes this tab that user and makes
    them the latest login.
  - **Sign-out** removes only this tab's user's pair.
  - **Old keys:** the pre-change keys `ai-orchestrator.access_token` / `refresh_token` are moved into a session on first
    read, so nobody is signed out by the update.
  - **Unchanged:** the accessor names, and every caller.
- **FR2 Refresh across tabs (`lib/api/client.ts`).**
  - The refresh runs under the Web Lock `ai-orchestrator.refresh.<user id>`.
  - Inside the lock, a stored access token other than the one that got the 401 means another tab already refreshed, and
    that token is used.
  - Without Web Locks, after a refused refresh, the tab adopts a pair another tab stored meanwhile.
- **FR3 Backend grace (`services/auth_service.refresh`).** A token **rotated** (`replaced_by` set) at most
  `REUSE_GRACE` = 30 s ago is refused with 401 and revokes nothing. These stay as before:
  - reuse after the window revokes the whole family;
  - so does reuse of a logged-out token (`replaced_by` null).

## Acceptance criteria

**Backend (live DB, rolled back): 8/8 pass.**
- The race winner refreshes, and the loser gets 401 within 30 s.
- The winner's new token and the user's other device keep working.
- Reuse after the window is 401 and revokes the newest token too.
- A logged-out token reused at once still revokes everything.
- Nothing persists after the rollback.

**Browser (headless Chrome, running app): 9/9 pass.**
1. An old single-key login is migrated, and the tab loads as A.
2. B signs in in tab 2, and tab 1 still sends A's token after a reload.
3. Tab 2 is still B after a reload.
4. A brand-new tab starts as the latest login (B).
5. A signs in again in tab 4, so tabs 1 and 4 are both A.
6. With A's access token made invalid, tabs 1 and 4 reload at the same moment. Both stay on /dashboard, with exactly
   **one** `POST /auth/refresh` between them.
7. B's tab is unaffected.
8. A clicks Log out in tab 4. A's pair is removed, and B's tab stays signed in.

## Files

`frontend/lib/auth/token.ts`, `frontend/lib/api/client.ts`, `backend/app/services/auth_service.py`.
