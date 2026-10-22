-- Run once as the database OWNER (Neon SQL Editor, role neondb_owner), right after
-- 2026-10-21_orders_sms_expenses.sql: the app connects as app_user, which doesn't own the
-- schema, so it can't create these objects and needs rights on the new tables. Safe to re-run.
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE order_status_events, sms_messages, expenses TO app_user;
