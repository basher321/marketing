# SPEC-BE-037: Accounts — Registration, Tenant Read, and User Management on the Live Database

Status: APPROVED (2026-09-29) — open decisions resolved per recommendations: subdomain = slug; live role_type vocabulary (custom rejected); new users active; per-tenant Owner role created on demand; no register rate limit; max_users not enforced.

## Purpose
Make it possible to create an account and manage a tenant's users against the real Postgres database. SPEC-BE-036 fixed login and token auth but explicitly left registration, user CRUD, and tenant provisioning out of scope. Verified on the live DB (rolled-back transaction, 2026-09-29):
- `POST /api/v1/auth/register` → 500: `null value in column "subdomain" of relation "tenants"`. It also builds `User(hashed_password=, full_name=, role=)`, none of which exist.
- `GET /api/v1/tenants/me` → 500: `TenantRead` requires `is_active`/`plan`, which the model no longer has.
- `GET /api/v1/users` → 500 (`UserRead` requires `full_name`/`is_active`); `POST /api/v1/users` → 500 (`'hashed_password' is an invalid keyword argument for User`).
- A self-registered user would be created with the DB default `status = 'invited'`, which login rejects.

So today there is no way to obtain an account at all, which blocks SPEC-FE-004 (login) and every frontend screen.

Two security defects in the current code are also fixed here:
- `register` joins an **existing** tenant (as `viewer`) when the submitted `tenant_slug` already exists, so anyone who knows a slug can add themselves to that organization.
- `/users` routes only require authentication: any role, including `viewer`, can create, update, or delete users.

## Scope
In scope:
- `POST /auth/register`: create a new tenant + its first (owner) user + the owner role assignment, atomically, and return tokens.
- `GET /tenants/me`: return the caller's tenant using live columns.
- `GET/POST /users`, `GET/PATCH/DELETE /users/{user_id}`: tenant-scoped user management using live columns and `user_roles` → `roles`.
- Audit log entries for every mutation in this scope.

Explicitly NOT being built by this spec:
- Email verification, invitations (invite emails, `invited` → `active` acceptance flow), password reset, 2FA.
- Refresh-token storage/rotation/revocation (`refresh_tokens` stays unused).
- Rate limiting of `/auth/register` (the limiter only covers login; see Open decision 5).
- Tenant update/settings endpoints, subscription tiers, `max_users` enforcement (see Open decision 6).
- The `Permission` / `RolePermission` models (misaligned with the live tables; unused by this flow).
- Any frontend work (SPEC-FE-004 consumes this).

## Contract
**`POST /api/v1/auth/register`** (unauthenticated) → 201 `{access_token, refresh_token, token_type: "bearer"}` (unchanged shape).
Request:
```
{ "tenant_name": str (1–255), "tenant_slug": str, "email": EmailStr, "password": str,
  "first_name": str | null (≤100), "last_name": str | null (≤100) }
```
Errors: slug already taken → 409; weak password → 422 with the policy messages; invalid slug → 422.

**`GET /api/v1/tenants/me`** (any authenticated role) → 200
```
{ "id", "name", "slug", "subdomain", "status", "currency", "timezone", "created_at" }
```

**`/api/v1/users`** — `UserRead`:
```
{ "id", "email", "first_name", "last_name", "role", "status", "last_login_at", "created_at" }
```
- `GET /users` (any authenticated role) → 200 list; `GET /users/{id}` → 200 or 404.
- `POST /users` (owner only) body `{ email, password, first_name?, last_name?, role }` → 201 `UserRead`; duplicate email in the tenant → 409.
- `PATCH /users/{id}` (owner only) body `{ first_name?, last_name?, role?, status? }` → 200 `UserRead`.
- `DELETE /users/{id}` (owner only) → 204 (soft delete).
- Insufficient role → 403; another tenant's user → 404 (never 403, so existence isn't leaked).

`role` in requests and responses is the live `role_type` value (see Open decision 2). `status` in PATCH accepts only `active` or `disabled`.

## Functional rules
1. **Registration always creates a new tenant.** If `tenant_slug` (after normalization) already exists, including soft-deleted tenants, return 409 "Tenant slug '<slug>' is already in use." Never join an existing tenant.
2. **Slug normalization:** `slugify(tenant_slug)` must be non-empty, ≤100 characters, and match the live `slug_format`/`subdomain_format` check `^[a-z0-9-]+$`; otherwise 422. `subdomain` = the normalized slug (Open decision 1).
3. **Tenant row:** `name`, `slug`, `subdomain`; every other column takes its DB default (`status = 'trial'`, which SPEC-BE-036 allows to log in; `currency = 'USD'`; `timezone = 'UTC'`).
4. **First user:** `email`, `password_hash = hash_password(password)`, `first_name`, `last_name`, `status = 'active'` (Open decision 3), `email_verified = false`.
5. **Owner role:** create a tenant-scoped `roles` row `(tenant_id, name = 'Owner', type = 'owner', is_system = false)` and a `user_roles` row `(user_id, role_id, tenant_id, assigned_by = NULL)` (Open decision 4).
6. **Atomicity:** tenant, user, role, user_role, and audit rows are written in one transaction. Any failure (including a unique-violation race on slug/subdomain/email) rolls back all of them. A race on the slug maps to the same 409 as rule 1, not a 500.
7. **Password policy:** the existing `validate_password_strength` applies to register and `POST /users`; a violation is 422 with all messages joined, before any DB write.
8. **User listing/reading** excludes soft-deleted users (`deleted_at IS NOT NULL`), filters by the caller's `tenant_id`, and resolves each user's role from `user_roles` → `roles` within that tenant: the highest `role_type` by the SPEC-BE-036 hierarchy, or `viewer` if none.
9. **Create user (owner only):** email unique per tenant; `users.email` is citext, so the DB decides case-insensitively and a unique violation maps to 409. `status = 'active'`. The role is assigned by reusing the tenant's `roles` row of that `type`, or creating it (`name` = capitalized type) if the tenant has none.
10. **Update user (owner only):**
    - Names are updated as given.
    - `role` replaces the user's role assignments in this tenant with the one given.
    - `status` may be set to `active` or `disabled`.
    - A disabled user's existing tokens stop working on the next request (SPEC-BE-036 `get_current_user` requires `status = 'active'`).
11. **Delete user (owner only):** soft delete — set `deleted_at = now()` and `status = 'disabled'`; no hard delete. Role rows remain for audit history.
12. **Last-owner guard:** a PATCH or DELETE that would leave the tenant with zero active, non-deleted users holding the `owner` role → 409 "A tenant must keep at least one active owner." This includes an owner demoting, disabling, or deleting themself.
13. **Audit:** one `audit_log` row per mutation via `core/audit.write_audit_log`, with `actor_user_id` set to the caller (NULL for self-registration). Actions: `tenant.registered`, `user.created`, `user.updated` (metadata lists the changed field names only, never values of secrets), `user.deleted`. Never include passwords or hashes.
14. **Tokens** on register are issued exactly as login does (`_issue_tokens`), so they carry the new tenant and authenticate immediately.

## Edge cases
- Email differing only in case from an existing user of the same tenant → 409 (citext unique `(tenant_id, email)`).
- The same email registering a second, different tenant → allowed (schema permits; `tenant_slug` disambiguates at login).
- `tenant_slug` like `"My Shop!"` → normalized to `my-shop`; `"!!!"` → empty after normalization → 422.
- PATCH with an empty body → 200, no change, no audit row.
- PATCH/DELETE on an already soft-deleted user → 404.
- An owner deleting themself while another active owner exists → allowed (204); their tokens stop working.
- `role: "custom"` → 422. There is no permission model for custom roles yet; they would silently map to viewer.

## Non-functional rules
- Plain service functions taking `db` and explicit `tenant_id`, type hints, structlog, no print; routes thin with `response_model` and explicit `status_code`.
- Timestamps in responses normalized to UTC.
- `password_hash` never appears in a response schema, log line, or audit metadata.
- No new files, folders, or dependencies; no schema (DDL) changes.
- Must not change login/refresh behavior or any other endpoint.

## Acceptance criteria
All verified on the live Postgres DB inside a rolled-back transaction, through real HTTP (TestClient) with **no auth override**. Tokens come from the real register/login endpoints.
1. `POST /auth/register` returns 201 with tokens. The DB then holds exactly one new tenant (`subdomain = slug`, `status = 'trial'`), one `active` user with a bcrypt `password_hash`, one `Owner` role of type `owner`, one `user_roles` row, and one `tenant.registered` audit row. The same credentials log in via `POST /auth/login`.
2. Registering an existing slug returns 409 and writes nothing, and the existing tenant gains no user. A weak password returns 422 and writes nothing, as does an unusable slug.
3. With the register token: `GET /tenants/me` returns 200 with the contract fields, and `GET /users` returns 200 listing the owner with `role = "owner"`, `status = "active"`, and no `password_hash` field.
4. As owner, `POST /users` creates a manager and a viewer (201). Each can log in, and `GET /users` resolves their roles correctly. A duplicate email (different case) returns 409.
5. As the viewer, and as the manager: `POST`, `PATCH` and `DELETE` on `/users` return 403, while `GET /users` returns 200.
6. As owner:
   - `PATCH` changes a user's role and the next `GET` reflects it.
   - `PATCH status=disabled` makes that user's existing token return 401.
   - `DELETE` returns 204, and the user no longer appears in `GET /users`.
   - Each of these writes one audit row.
7. Demoting, disabling, or deleting the only owner returns 409, and nothing changes.
8. A second tenant's user ID via `GET`, `PATCH` or `DELETE` `/users/{id}` returns 404, and the second tenant's data is untouched.
9. After rollback: tenant, user, role, user_role and audit row counts equal their pre-run values.

## Assumptions (verified against the live DB, 2026-09-29)
- `tenants`: `subdomain` NOT NULL; UNIQUE `slug` and UNIQUE `subdomain`; CHECK `slug_format` and `subdomain_format` = `^[a-z0-9-]+$`; defaults `status 'trial'`, `subscription_tier 'free'`, `currency 'USD'`, `timezone 'UTC'`, `id uuid_generate_v4()`. An `updated_at` trigger exists.
- `users`: UNIQUE `(tenant_id, email)` (email is citext); `status` enum `user_status` = active, invited, disabled, locked; FK `tenant_id` → tenants ON DELETE CASCADE.
- `roles`: UNIQUE `(tenant_id, name)`; `type` enum `role_type` = owner, manager, operator, analyst, viewer, custom; `tenant_id` nullable (system roles), currently 0 rows.
- `user_roles`: PK `(user_id, role_id)`, `tenant_id` NOT NULL, `assigned_by` FK → users (nullable).
- `core/audit.write_audit_log` writes to the live `audit_log` table and commits the session. The `AuditLog` model is aligned with the live table (verified).
- The live DB currently has 0 tenants and 0 users.

## Open decisions (to settle in the plan step)
1. **Subdomain:** set `subdomain = slug` (recommended), or accept a separate `subdomain` field in the register request.
2. **Role vocabulary in the users API:** live `role_type` values `owner | manager | operator | analyst | viewer` (recommended — the stored truth; `custom` rejected), or the app's RBAC names (`owner | admin | manager | agent | viewer`, which have no 1:1 live mapping for `admin`).
3. **Status of self-registered and owner-created users:** `active` immediately (recommended — no email/invite flow exists, and `invited` users can't log in), or `invited`, which blocks login until an invite spec exists.
4. **Owner role storage:** a tenant-scoped `Owner` role per tenant, created on demand (recommended — self-contained, no global seed), or shared system roles (`tenant_id` NULL) seeded once. The latter needs a separate data-seeding decision, and `UNIQUE (tenant_id, name)` doesn't prevent duplicate NULL-tenant rows.
5. **Register rate limiting:** leave unlimited for now (recommended, tracked as a follow-up), or extend `RateLimitMiddleware` to `POST /auth/register` in this spec. The latter adds a target file.
6. **`max_users`:** ignore the tenant's `max_users` (default 5) for now (recommended — no tier logic exists yet), or enforce it on `POST /users` with a 409.

## Target files
- backend/app/schemas/auth.py
- backend/app/schemas/tenant.py
- backend/app/schemas/user.py
- backend/app/services/auth_service.py
- backend/app/services/tenant_service.py
- backend/app/services/user_service.py
- backend/app/api/v1/users.py
