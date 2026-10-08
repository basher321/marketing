# SPEC-FE-036: Organization Settings page

Status: IMPLEMENTED (2026-09-30), plan approved by the user; verified E2E in headless Edge (dev-shop profile, logo and test user reverted afterwards; reset run on throwaway sign-up tenants, which were deleted). Depends on SPEC-BE-051 and the existing user API (SPEC-BE-037).

Implementation notes: the topbar's existing (previously inert) ◈ Settings button now links to /settings instead of adding an avatar menu. The user API is owner-only, so a successful user list is how the page knows the viewer is the owner (it then shows the Data tab); the backend enforces every rule. The wrong-password case returns 422 "Incorrect password." (SPEC-BE-051) so it isn't confused with the 403 "not the owner".

## Purpose
A new `/settings` page for company admins. A "Settings" link is added to the sidebar's last section and to the avatar menu.

## Functional rules (tabs)
1. **Company:** name, country, currency, timezone (searchable list), and language, with Save.
2. **Branding:**
   - Upload, preview and remove the logo (square) and banner (wide). They are client-side checked for type and size (≤ 1 MB) before upload.
   - The company head's photo, name and title.
   - The logo then appears in the sidebar brand area.
3. **Users & Roles:**
   - A table of users (name, email, role, status, last login).
   - "+ Add user": email, first and last name, role (Owner, Manager (company admin), Operator, Analyst, Viewer), and a temporary password (generate/show).
   - Per row: change role, deactivate/activate, delete (with confirmation).
   - A roles legend explains what each role can do (from the RBAC levels).
   - The backend is owner-only. A non-owner sees the list read-only, with a note.
4. **Data (danger zone):**
   - "Reset company data" explains exactly what is deleted and what is kept (the SPEC-BE-051 lists).
   - It needs the user to type the workspace slug and enter their password.
   - Result: counts per table, and the caches are invalidated.
   - Shown only to the owner.
5. **API & AI keys:** a pointer card linking to Integrations, where every key lives (per your instruction).

## Acceptance criteria (verified E2E)
Profile and branding changes persist (DB checked) and the logo shows in the sidebar. A user is created, has their role changed and is deleted. Reset is verified on a **throwaway tenant** made through Signup, never on dev-shop.

## Target files
- app/(app)/settings/page.tsx (new route)
- components/settings/company-form.tsx, branding-form.tsx, users-roles.tsx, danger-zone.tsx (new)
- components/shell/sidebar.tsx (Settings link + logo), components/shell/topbar.tsx (avatar menu entry)
- lib/api/tenant.ts, lib/types/tenant.ts (new)
