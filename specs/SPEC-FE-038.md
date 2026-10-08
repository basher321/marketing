# SPEC-FE-038: Login (ERP design) + free Sign-up for new organizations

Status: IMPLEMENTED (2026-09-30), plan approved by the user; verified E2E in headless Edge (screenshots checked against the ERP design; the throwaway sign-up tenant was deleted afterwards).

Implementation notes: /login and /forgot-password use the ERP's circular card. /signup and /reset-password use the same soft-UI styles on a rounded card (`.neu-card`), because 7 fields don't fit inside a circle. The shared shell and styles are in components/auth/auth-shell.tsx. password-input.tsx needed no change (it already accepts a className). Backend: the existing `POST /auth/register` and `/auth/login` (SPEC-BE-036/037/039), unchanged.

## Purpose
1. **`/login`:** restyled to match `D:\erp\frontend\src\app\login\page.tsx`.
   - The neumorphic ("soft UI") circular card, with floating-label pill inputs (Workspace, Email, Password) and a soft "Sign In" button.
   - A check-mark "Success!" animation before redirecting to the dashboard.
   - "New company? **Create workspace**" link below.
   - The styles are copied from that file (`.neu-*`, scoped to the page).
2. **`/signup`** (new), in the same design:
   - Fields: company name; workspace slug (auto-suggested from the name, editable, shown as the login workspace); owner first and last name; email; password + confirm.
   - A strength hint using the backend's rules, then "Create workspace" → `POST /auth/register`. On success the tokens are stored and the user goes to the dashboard as the new owner, with the same success animation.
   - "Already have a workspace? **Sign in**".

## Kept (nothing removed)
- The password show/hide eye (SPEC-FE-025) is placed inside the neu input.
- "Forgot password?" link.
- Lockout and rate-limit messages (429) and error text.
- The same auth logic, token storage and redirects.
- `/forgot-password` and `/reset-password` get the same visual style for consistency.

## Acceptance criteria (verified E2E)
- Sign up a throwaway company: it logs in and lands on the dashboard, and the tenant and owner exist in the DB (removed afterwards).
- Login works, and wrong credentials show the backend message.
- The eye toggle and the forgot-password link still work.

## Target files
- app/login/page.tsx, app/signup/page.tsx (new), app/forgot-password/page.tsx, app/reset-password/page.tsx
- components/auth/auth-shell.tsx (new: the shared neumorphic shell and styles), components/auth/password-input.tsx (neu variant)
- lib/api/auth.ts (register call)
