# SPEC-FE-059: Show the real reason for a 403, not "Your role can't do this"

Status: IMPLEMENTED (2026-10-09), approved by the user: "Your role can't do this; ask a manager or the
owner. create problem this type of role, so fix it".
- **AC1/AC2:** `isRoleDenied` was checked at runtime against 7 cases, all passing: the role check with
  both backend shapes (`{"detail"}` from HTTPException, `{"error"}` from AppError), the owner-only rule,
  a SocialAPI refusal, an expired media link, a 404 and a plain Error.
- **AC3:** `tsc` and `next build` are clean.
- **Deviation:** the check reads `err.message`, which `apiFetch` fills from `error` or `detail`, instead of
  `body.detail`. AppError responses use `{"error": …}`, so a detail-only check would miss Command Chat's
  role refusal.

## Context

- **The user is the owner:** pilotsonic has one account, `abc@gmail.com`, and its role is owner.
- **Why the role message shows anyway:** 13 frontend error helpers turn *every* HTTP 403 into a role
  message, because the client doesn't know the user's role. The backend's role refusal is only one
  kind of 403:
  - **The role check** (`dependencies.require_permission`, `core/permissions.require_role`,
    `orchestrator_service`): detail "Insufficient permissions." / "Insufficient permissions for this
    action.". This is the only true "your role can't" case.
  - **Specific rules,** e.g. "Only the owner can reset company data." and "Only the owner can approve a
    campaign launch.". Their own text is clearer.
  - **Refusals passed through from other services:** SocialAPI (its 402/403, e.g. plan limits),
    Zernio (402/403), and an invalid or expired media link. Showing "your role" for these is wrong and
    hides the real problem.

## Requirements

- **FR1:** `lib/types/common.ts` gets `isRoleDenied(err)`. It is true only for an `ApiError` with status
  403 whose message starts with "Insufficient permissions".
- **FR2:** every helper that maps 403 to a role message uses `isRoleDenied` instead of `status === 403`.
  Any other 403 shows the backend's own message (`err.message`), as for other errors.
- **FR3:** the role messages themselves and every non-403 path are unchanged. No backend change.

## Acceptance criteria

- **AC1:** a 403 with detail "Insufficient permissions." still shows the role message.
- **AC2:** a 403 with any other detail (SocialAPI, Zernio, "Only the owner can …") shows that detail.
- **AC3:** `npx tsc --noEmit` and the production build pass.

## Target files

`lib/types/common.ts`, plus the 13 helpers:
- `components/organic/shared.tsx`;
- `components/campaigns/builder/tree.tsx`, `components/campaigns/platform-builder/tree.tsx`,
  `components/campaigns/wizard.tsx`;
- `components/ecommerce/{inventory-table,pricing-rules,shipping-setup-wizard,shipping-status-bar,shipping-zones}.tsx`;
- `components/integrations/connect-panel.tsx`, `components/kb/faq-list.tsx`,
  `components/marketing/campaigns-table.tsx`, `components/settings/users-roles.tsx`,
  `components/workflows/workflow-editor.tsx`.

This is a cross-cutting fix, so it goes past the usual file limit.
