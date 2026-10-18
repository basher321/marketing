# SPEC-FE-071: Organic › Accounts shows SocialAPI accounts

Status: IMPLEMENTED (2026-10-11), backend SPEC-BE-104. `npx tsc --noEmit` is clean. **The browser E2E is pending**: no
test company with a SocialAPI Page is reachable from the running app (the backend there uses the real SocialAPI).

## Requirements

- `SocialAccount.connected_via` adds `"socialapi"`.
- **On Organic › Accounts, an account connected through SocialAPI shows:**
  - "Connected via: SocialAPI" and its SocialAPI account id, with no token, check or sync rows;
  - no Connect/Reconnect button;
  - a **Manage in Organic › SocialAPI** link;
  - the backend's problem as its error line (e.g. "Choose its Facebook Page in Organic › SocialAPI.").
- **Pasting is refused since SPEC-BE-101,** so the "Or paste: …" hints and the "Paste a token in Integrations" button
  are removed:
  - a platform that isn't connected links to **Connect through SocialAPI**;
  - where direct sign-in isn't set up, it says so instead of "paste a token".
- Directly connected accounts are unchanged ("Manage / test in Integrations").

## Files

`app/(app)/marketing/organic/accounts/page.tsx`, `lib/types/social.ts`.
