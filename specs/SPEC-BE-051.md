# SPEC-BE-051: Organization Settings — profile, branding images, data reset

Status: IMPLEMENTED (2026-09-30), plan approved by the user; verified on live Postgres (rolled-back txn), including a full reset of dev-shop inside that transaction (restored by the rollback) and isolation of a second tenant.

## Purpose
Back the new Organization Settings page (SPEC-FE-036): company profile, branding (logo, banner, company head's photo), and a per-company data reset. Users and roles use the existing owner-only user API (SPEC-BE-037), unchanged. API and LLM keys live on the Integrations page (SPEC-BE-052/053).

## Contract
`GET /api/v1/tenants/me`: the existing response, plus:
```
{ ..., country_code, currency, timezone, default_language,
  branding: { logo_url: str|null, banner_url: str|null,
              head: { name: str|null, title: str|null, photo_url: str|null } } }
```
- `PATCH /api/v1/tenants/me` (owner or manager): `{ name?, country_code?, currency?, timezone?, default_language? }` → 200.
- `PUT /api/v1/tenants/me/branding/{slot}` (owner or manager), with slot `logo|banner|head_photo`, a multipart `file` → 200 `branding`.
- `DELETE /api/v1/tenants/me/branding/{slot}` (owner or manager) → 200 `branding`.
- `PATCH /api/v1/tenants/me/branding` (owner or manager): `{ head_name?, head_title? }` → 200 `branding`.
- `POST /api/v1/tenants/me/reset` (**owner only**): `{ confirm_slug, password }` → 200 `{ deleted: {table: count}, reset_at }`.

## Functional rules
1. **Images:** PNG, JPEG or WebP, at most **1 MB**. The type is checked from the file's magic bytes, not from what the client claims (422 otherwise). They are stored as data URLs in `tenants.metadata.branding`. This needs no file storage or new folder, and it stays tenant-scoped and survives restarts. `GET /tenants/me` returns them as `*_url` (the data URL). The sidebar shows the logo.
2. **Profile validation:** timezone must be a valid IANA zone (`zoneinfo`), currency a 3-letter code, country 2 letters, and language a 2–5 character code.
3. **Reset:**
   - Checks: `confirm_slug` must equal the tenant slug and `password` must match the owner's password; either mismatch returns 422 (403 always means "not the owner", so the UI can tell them apart). A wrong password counts toward the login lockout rules.
   - **It deletes all of this company's business data** in one transaction: orders, order items, customers, conversations, messages, products (+ variants, categories, inventory, movements, locations), pricing rules, shipping zones and rates, campaigns (+ ad sets, ads), audiences, content assets and templates, scheduled posts, workflows (+ runs, action executions), FAQs, macros, policies, KB documents, brand settings, analytics events and rollups, approvals, notifications, orchestrator plans and messages, abandoned carts, and webhook events.
   - **It keeps** the company itself, users, roles, integrations and connected keys (SPEC-BE-052/053), API keys, settings and branding, and the audit log.
   - It writes an audit row `tenant.reset` with the per-table counts.
   - Only the caller's tenant is touched: every DELETE has a `tenant_id` filter.
4. Every other write is audited (`tenant.update`, `tenant.branding_update`).

## Acceptance criteria
1. Profile and branding updates persist. A bad image (wrong type, over 1 MB, or a fake extension) is rejected. Viewer gets 403.
2. Reset as owner with the right slug and password → every listed table is empty **for that tenant only**, and a second tenant's data is untouched. A wrong slug or password → nothing deleted. A manager → 403.

## Target files
- backend/app/models/tenant.py, schemas/tenant.py, services/tenant_service.py, api/v1/tenants.py
