-- SPEC-BE-107 / 108 / 110 additive DDL (2026-10-21). Safe to re-run.
ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'awaiting_confirmation' AFTER 'pending';
ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'returned' AFTER 'delivered';
-- webhook_events.provider is integration_provider: Twilio's SMS webhooks are stored under 'twilio'.
ALTER TYPE integration_provider ADD VALUE IF NOT EXISTS 'twilio';

CREATE TABLE IF NOT EXISTS order_status_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  order_id uuid NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  from_status text,
  to_status text NOT NULL,
  actor_type text NOT NULL CHECK (actor_type IN ('user','system','customer_sms','store_sync')),
  actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  reason text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS order_status_events_order_idx ON order_status_events (tenant_id, order_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS orders_idempotency_idx ON orders (tenant_id, (metadata->>'idempotency_key'))
  WHERE metadata ? 'idempotency_key';

CREATE TABLE IF NOT EXISTS sms_messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  order_id uuid REFERENCES orders(id) ON DELETE SET NULL,
  customer_id uuid REFERENCES customers(id) ON DELETE SET NULL,
  conversation_id uuid REFERENCES conversations(id) ON DELETE SET NULL,
  direction text NOT NULL CHECK (direction IN ('outbound','inbound')),
  kind text NOT NULL CHECK (kind IN ('order_confirmation','follow_up','auto_reply','manual','inbound')),
  from_number text NOT NULL,
  to_number text NOT NULL,
  body text NOT NULL,
  provider text NOT NULL DEFAULT 'twilio',
  provider_sid text,
  status text NOT NULL,
  error_code text,
  error_message text,
  interpreted text CHECK (interpreted IN ('confirm','cancel','ambiguous','unrelated')),
  sent_by uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS sms_messages_sid_idx ON sms_messages (provider, provider_sid) WHERE provider_sid IS NOT NULL;
CREATE INDEX IF NOT EXISTS sms_messages_order_idx ON sms_messages (tenant_id, order_id, created_at);
CREATE INDEX IF NOT EXISTS sms_messages_phone_idx ON sms_messages (tenant_id, to_number, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS webhook_events_dedupe_idx ON webhook_events (provider, external_event_id)
  WHERE external_event_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS expenses (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  category text NOT NULL CHECK (category IN ('shipping','operating','other')),
  amount_cents bigint NOT NULL CHECK (amount_cents > 0),
  currency char(3) NOT NULL,
  incurred_on date NOT NULL,
  description text NOT NULL,
  vendor text,
  created_by uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);
CREATE INDEX IF NOT EXISTS expenses_tenant_day_idx ON expenses (tenant_id, incurred_on) WHERE deleted_at IS NULL;
