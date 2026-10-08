# SPEC-BE-036: Auth Fix — Align User/Tenant Models With the Live Database (login, token auth, RBAC)

Status: APPROVED (2026-09-26) — open decisions resolved per recommendations: role mapping as recommended; must_change_password users may log in; dev account deferred (ask separately).

## Purpose
Make login and every authenticated endpoint work against the real Postgres database. Today the `User` and `Tenant` ORM models map columns the live `users`/`tenants` tables do not have, so `POST /api/v1/auth/login` fails with `column tenants.is_active does not exist` (500), and `dependencies.get_current_user` would fail on `column users.hashed_password does not exist` — which blocks every authenticated route for the frontend (SPEC-FE-004 onward).

## Scope
In scope:
- Realign `app/models/user.py`'s `User` and `app/models/tenant.py`'s `Tenant` to the live tables (verified via information_schema, see Assumptions).
- Login (`POST /auth/login`) and refresh (`POST /auth/refresh`) in `app/services/auth_service.py` using the live columns.
- `dependencies.get_current_user` and `require_permission` resolving the user, their tenant, and their role from the live `users` + `user_roles` + `roles` tables.

Explicitly NOT being built by this spec:
- Registration (`POST /auth/register`), user CRUD (`services/user_service.py`), and tenant provisioning (`services/tenant_service.create_tenant`) — they also use the misaligned fields and remain broken until a follow-up spec; this spec keeps them importable but does not make them work.
- 2FA (the live `users.two_factor_enabled` / `two_factor_secret` columns exist but no flow uses them yet) — see Functional Rule 5.
- Refresh-token storage/rotation/revocation (the live `refresh_tokens` table stays unused).
- Account lockout logic (`failed_login_attempts`, `locked_until`) beyond honoring an already-set `status = 'locked'`.
- Password reset.

## Contract
Unchanged request/response shapes (the frontend depends on them):
- `POST /api/v1/auth/login` — body `{email, password, tenant_slug}` → 200 `{access_token, refresh_token, token_type: "bearer"}`; bad credentials → 401 `{"error": "Invalid credentials."}`.
- `POST /api/v1/auth/refresh` — body `{refresh_token}` → 200 same token shape; invalid/expired → 401.
- Every protected route: `Authorization: Bearer <access_token>` → the caller's user with `tenant_id` and an app-level `role`; missing/invalid token → 401; insufficient role → 403.

## Functional rules
1. `User` maps the live `users` columns actually needed: `id`, `tenant_id`, `email` (citext), `password_hash`, `first_name`, `last_name`, `status` (live `user_status` enum: active, invited, disabled, locked), `email_verified`, `two_factor_enabled`, `last_login_at`, `deleted_at`, `created_at`, `updated_at`. Remove the non-existent `hashed_password`, `full_name`, `role`, `is_active`, `is_email_verified` mappings. Keep Python attribute names where a live equivalent exists only if a caller needs it (document any alias as a code comment).
2. `Tenant` maps the live `tenants` columns actually needed: `id`, `name`, `slug`, `subdomain`, `status` (live `tenant_status` enum: active, suspended, trial, cancelled), `currency`, `timezone`, `deleted_at`, `created_at`, `updated_at`. Remove the non-existent `is_active`/`plan` mappings.
3. Login: find the tenant by `slug` with `deleted_at IS NULL`; find the user by `(tenant_id, email)` with `deleted_at IS NULL`; verify the password against `password_hash` with the existing bcrypt `verify_password`. Any mismatch (no tenant, no user, wrong password) → the same 401 "Invalid credentials." (no user enumeration). Only `status = 'active'` users may log in; `invited`/`disabled`/`locked` → 401 with a distinct, documented message. Tenant `status` in (`active`, `trial`) may log in; `suspended`/`cancelled` → 401 with a documented message. On success, set `users.last_login_at = now()` (the only write).
4. Role resolution: a user's app role comes from `user_roles` → `roles.type` (live `role_type` enum: owner, manager, operator, analyst, viewer, custom), mapped onto the app's RBAC hierarchy in `core/permissions.py` (owner > admin > manager > agent > viewer) by a single documented mapping — see Open decision 1. A user with several roles gets the highest; a user with no role row gets `viewer` (least privilege). Every query filters by the user's own `tenant_id` (`user_roles.tenant_id`), so a role from another tenant is never applied.
5. If a user has `two_factor_enabled = true`, login must not silently skip 2FA: reject with 401 and a documented "two-factor authentication is not supported yet" message, rather than issuing tokens (stop condition kept honest until a 2FA spec exists).
6. `get_current_user` decodes the access token (unchanged `core/security.py`), loads the user by `id` with `deleted_at IS NULL` and `status = 'active'`, attaches `tenant_id` and the resolved app `role`, sets the tenant ContextVar, and otherwise returns 401 exactly as today.
7. Tokens are unchanged: `create_access_token(user.id, user.tenant_id)` / `create_refresh_token(...)`, same claims and lifetimes.
8. No write to any table other than `users.last_login_at` on successful login. Never log or return `password_hash`.

## Edge cases
- Email case: `users.email` is citext, so lookups are case-insensitive by the database itself; do not lower-case in Python in a way that diverges from it.
- Soft-deleted tenant or user (`deleted_at` set): treated as not found (401 "Invalid credentials.").
- Same email in two tenants: allowed by the schema; `tenant_slug` disambiguates.
- A token whose user was later disabled/locked/deleted: 401 on the next request.

## Non-functional rules
- Plain functions, explicit `db` + `tenant_id`, type hints, structlog, no print.
- Must not change any other endpoint's behavior; the SPEC-BE-005…035 services that take `current_user.tenant_id`/`current_user.role` keep working unchanged.
- No new files or folders; no new dependency.

## Acceptance criteria
1. With a real tenant + active owner user seeded in the live DB (inside a rolled-back transaction), `POST /api/v1/auth/login` with correct credentials returns 200 and a token pair; `last_login_at` is updated.
2. Wrong password, unknown email, and unknown tenant slug each return the identical 401 "Invalid credentials."; invited/disabled/locked users and suspended/cancelled tenants return their documented 401s; a 2FA-enabled user gets the documented 401, never tokens.
3. The returned access token authenticates a real protected endpoint (e.g. `GET /api/v1/orchestrator/messages`) with the right `tenant_id`, and `require_permission("manager")` passes for an owner/manager and returns 403 for a viewer — using the Open decision 1 mapping.
4. `POST /api/v1/auth/refresh` with the refresh token returns a new pair; an access token passed as a refresh token is rejected.
5. A role row belonging to another tenant is never applied (verified with two tenants).
6. No row other than `users.last_login_at` changes; no `password_hash` appears in any response or log.

## Assumptions (verified against the live DB via information_schema)
- `users`: id, tenant_id, email (citext), password_hash, first_name, last_name, phone, avatar_url, status (user_status), email_verified, email_verified_at, two_factor_enabled, two_factor_secret, last_login_at, last_login_ip, failed_login_attempts, locked_until, password_changed_at, must_change_password, preferences, created_at, updated_at, deleted_at.
- `tenants`: id, name, slug, subdomain (NOT NULL), status (tenant_status), subscription_tier, subscription_expires_at, country_code, currency, timezone, default_language, max_users, max_products, llm_daily_cap_cents, ad_daily_cap_cents, settings, metadata, created_at, updated_at, deleted_at.
- `roles` (id, tenant_id nullable, name, type role_type, description, is_system, …; UNIQUE (tenant_id, name)) and `user_roles` (user_id, role_id, tenant_id, assigned_by, assigned_at). Both are currently empty.

## Open decisions (to settle in the plan step)
1. **Role mapping** from live `role_type` to the app hierarchy. Recommended: owner→owner, manager→manager, operator→agent, analyst→viewer, viewer→viewer, custom→viewer. The app's `admin` level has no live equivalent (nobody maps to it).
2. **`must_change_password = true`**: allow login (recommended, surfaced later by a password spec) or reject.
3. **Dev account**: after this spec is verified, create one real tenant + owner user in the live DB for manual/frontend testing (an explicit, approved write outside the rolled-back verification), or keep all verification rolled back.

## Target files
- backend/app/models/user.py
- backend/app/models/tenant.py
- backend/app/services/auth_service.py
- backend/app/dependencies.py
