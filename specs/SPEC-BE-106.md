# SPEC-BE-106: Database schema baseline

Status: IMPLEMENTED (2026-10-21). Documentation of the existing schema; no DDL change.
- `specs/schema/live-schema.sql` was dumped (`pg_dump --schema-only --no-owner --no-privileges --schema=public`) from
  the local PostgreSQL 16.15 database. Production (Neon) was copied from it on 2026-10-19, and no DDL ran after that.
- 65 tables, 25 enum types.

## The problem

- The schema was created outside Alembic, and the specs only carry the **additive** DDL of later features
  (SPEC-BE-055, 058, 074–077, 087, 096–099, 101…). Nobody could build a new database from the specs alone.
- Several ORM models don't match the live tables (CLAUDE.md, "Live database vs ORM models"), so
  `Base.metadata.create_all()` would not reproduce it either.

## Requirements

1. `specs/schema/live-schema.sql` is the source of truth for a new database: run it with `psql -v
   ON_ERROR_STOP=1 -f` against an empty database, as a role that may create extensions.
2. **Server:** PostgreSQL 13 or newer (one generated column needs 12+; `gen_random_uuid()` defaults; 16+
   recommended). Extensions, created at the top of the file: `uuid-ossp`, `pgcrypto`, `pg_trgm`, `citext`. pgvector
   is not used (SPEC-BE-087 stores `real[]`).
3. **The app's login** is a separate least-privilege role (not superuser, not BYPASSRLS; SPEC-BE-071 F4 refuses
   either in production) that owns or is granted the tables. RLS policies `tenant_isolation_*` exist on 9 tables; the
   app doesn't set `app.current_tenant_id`, so RLS must be disabled on them for a non-superuser login (production's
   choice), or the app filters by `tenant_id` itself (it always does).
4. **No data** is in the file. A new install starts with `POST /auth/register` (first company and owner), then a
   `platform_admins` row by hand for the super admin (SPEC-BE-101), then the software-wide keys in `/admin`.
5. When a spec adds DDL, it is applied to every database (local, Neon) **and** the dump is refreshed, so this file
   stays current. Enum values are added with `ALTER TYPE … ADD VALUE` outside a transaction block.

## Tables (65)

abandoned_carts, action_executions, ad_groups, ads, ai_campaign_runs, analytics_daily_rollups, analytics_events
(+ `_default` partition), api_keys, approval_queue, audiences, audit_log (+ `_default`), brand_settings, campaigns,
content_assets, content_templates, conversations, customers, email_verification_tokens, faqs, generation_jobs,
integrations, inventory, inventory_locations, inventory_movements, kb_documents, knowledge_embeddings, macros,
media_assets, messages, notifications, orchestrator_chats, orchestrator_files, orchestrator_messages,
orchestrator_plans, orchestrator_projects, order_items, orders, organic_contents, password_reset_tokens,
permissions, platform_admins, platform_settings, policies, pricing_rules, product_categories, product_variants,
products, rate_limit_buckets, refresh_tokens, role_permissions, roles, scheduled_posts, shipping_policies,
shipping_zones, system_logs (+ `_default`), tenants, usage_metrics, user_roles, users, webhook_events,
workflow_runs, workflows.

## Acceptance criteria
1. On an empty PostgreSQL 16 database, the file runs with `ON_ERROR_STOP=1` without errors and creates 65 tables and
   25 enum types in `public`.
2. The backend starts against that database, `/health` → ok, and `POST /auth/register` + `/auth/login` work.
3. `information_schema.columns` of the new database equals the production database's (table, column, type,
   nullability, default).

## Files
- `specs/schema/live-schema.sql`
