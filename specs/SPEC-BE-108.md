# SPEC-BE-108: Order confirmation SMS through Twilio — send, delivery status, customer replies

Status: IMPLEMENTED (2026-10-22). 61/61 rolled-back checks with BE-107 (dev fakes for Twilio). Extra DDL found during the work: `ALTER TYPE integration_provider ADD VALUE 'twilio'` (webhook_events.provider is that enum). Not yet run against a real Twilio account: the Super admin must save the account SID/token and assign a number. Depends on SPEC-BE-107. UI in SPEC-FE-073.

## Decisions (user, 2026-10-21)

- Provider: **Twilio**. One PilotSonic Twilio account, set by the Super admin. Each company gets its own
  sending number, assigned by the Super admin (a shared number can't tell which company a reply is for).
- Auto-send: a **per-company setting** (`auto_confirm`), on by default once the company has a number;
  otherwise staff press "Send confirmation SMS".

## Requirements Twilio imposes (documented for the operator)

- A Twilio account with a phone number that can **send and receive SMS**. Twilio has no Bangladesh numbers;
  replies from a BD customer to a foreign number cost the customer international SMS. An alphanumeric sender
  ID can't receive replies at all. In that case staff confirm by phone and set the status by hand (still
  supported).
- Twilio must reach `https://api.pilotsonic.com/api/v1/webhooks/twilio/{inbound|status}` (public https).

## Additive DDL

```sql
CREATE TABLE sms_messages (
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
  status text NOT NULL,      -- queued, sent, delivered, undelivered, failed, received
  error_code text,
  error_message text,
  interpreted text CHECK (interpreted IN ('confirm','cancel','ambiguous','unrelated')),
  sent_by uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX sms_messages_sid_idx ON sms_messages (provider, provider_sid) WHERE provider_sid IS NOT NULL;
CREATE INDEX sms_messages_order_idx ON sms_messages (tenant_id, order_id, created_at);
CREATE INDEX sms_messages_phone_idx ON sms_messages (tenant_id, to_number, created_at);
ALTER TYPE integration_provider ADD VALUE IF NOT EXISTS 'twilio';  -- webhook_events.provider
CREATE UNIQUE INDEX webhook_events_dedupe_idx ON webhook_events (provider, external_event_id)
  WHERE external_event_id IS NOT NULL;
```

## Requirements

- **FR1 Super admin config.** `platform_settings` group `twilio` = `{account_sid, auth_token (secret,
  Fernet), default_country?}` with the usual test button (`GET /Accounts/{sid}.json`). New access group `sms`
  (SPEC-BE-103). `PUT /platform/companies/{id}/sms-number {number}` assigns a number (E.164, must be one of the
  account's `IncomingPhoneNumbers`; one company per number, 409 otherwise). `GET` lists the account's numbers.
- **FR2 Company settings.** `tenants.settings.sms` = `{number (read-only), auto_confirm: bool, language:
  'en'|'bn'|'auto', template?}`. `GET/PUT /tenants/me/sms` (manager+). `status`: `not_configured` (no Twilio
  account), `no_number`, `blocked` (SPEC-BE-103), `ready`. The template may use `{shop}`, `{order_number}`,
  `{total}`, `{items}`; the default English text is
  "{shop}: order #{order_number}, {total}. Reply YES {order_number} to confirm or NO {order_number} to cancel."
  plus a Bengali default (`'auto'` = the brand's `primary_language`). Max 3 SMS segments, checked on save.
- **FR3 Phone numbers.** New dependency `phonenumbers` (SPEC-BE-001 updated). `utils/phone.normalize(raw,
  country)` → E.164 or None, with the company's country as the default region.
- **FR4 Send.** `sms_service.send_confirmation(db, tenant_id, order_id, actor, kind)`:
  - Order must be `pending` or `awaiting_confirmation` (409), the customer must have a valid phone (422
    "This customer has no mobile number"), SMS status must be `ready` (409 with the reason), at most 3
    confirmation/follow-up SMS per order and one per 10 minutes (429 with the wait).
  - `POST /2010-04-01/Accounts/{sid}/Messages.json` with `StatusCallback`. Accepted → an `sms_messages` row
    (queued) and, from `pending`, the order moves to `awaiting_confirmation` (SPEC-BE-107 event, actor
    system/user). Twilio error → a `failed` row with Twilio's message; the order stays `pending`; the API
    returns 502 with the message.
  - `POST /orders/{id}/confirmation-sms` (agent+) = send or follow-up.
  - Auto: after `POST /orders` when `auto_confirm` and status `ready` and the customer has a phone. A failure
    never fails order creation; the order shows the failed SMS.
- **FR5 Webhooks** (`api/v1/webhooks.py`, no auth, the 404 catch-all stays for other providers):
  - `X-Twilio-Signature` verified (HMAC-SHA1 over the public URL + sorted form fields, the stored auth token,
    `hmac.compare_digest`). Invalid → 403, stored in `webhook_events` with `signature_valid=false`.
  - Every valid event is stored in `webhook_events` with `external_event_id` = `MessageSid` (inbound) or
    `MessageSid:MessageStatus` (status). A duplicate → 200 and nothing else happens.
  - `status`: updates the row's status/error (never moves backwards: delivered beats sent beats queued).
  - Answers `200 text/xml <Response/>`.
- **FR6 Replies** (`inbound`):
  - Company = the `To` number's owner (unknown → stored, ignored). Customer = `From` matched by E.164 phone.
  - Interpretation (case-insensitive, trimmed): confirm = `yes, y, confirm, ok, 1, হ্যাঁ, হা, জি`; cancel =
    `no, n, cancel, 2, না, বাতিল`. An order number in the text picks that order.
  - Candidate orders = this customer's `awaiting_confirmation` orders that had a confirmation SMS to this
    phone. Exactly one (or the named one) + a clear keyword → `confirmed`/`cancelled` (actor
    `customer_sms`, the SMS id in the event metadata) and a short thank-you auto-reply.
  - Several candidates and no number, or no keyword → `ambiguous`: nothing changes, an auto-reply asks
    "Please reply YES <number> or NO <number>" (once per 10 minutes), and a staff `notifications` row.
  - No candidate → `unrelated`.
  - `STOP`/`UNSUBSCRIBE` (Twilio handles the opt-out) → `customers.consent.sms = false`; no more SMS to that
    customer (409 "opted out").
  - Every inbound SMS is also appended to the customer's `sms` conversation (created if needed) so it shows in
    the inbox (SPEC-BE-112).
- **FR7 `confirmation` on the order** (SPEC-BE-107 FR4): `{state: not_sent | waiting | confirmed | cancelled,
  last_sms: {status, at, error?}, sms_count, replies[]}`. Waiting orders with no reply stay waiting; staff can
  follow up (FR4) or set the status by hand.
- **FR8 Dev fakes.** `dev_fakes` answers `api.twilio.com` (`SMS_CALLS`, `SMS_FAIL`); the account sid
  `AC_bad` gives 401.

## Acceptance criteria (live DB, rolled back, dev fakes)

1. With auto-confirm on, creating an order sends one SMS and moves it to awaiting_confirmation; with it off or
   no number, nothing is sent and the order stays pending.
2. A status callback updates the SMS; the same callback twice changes nothing; an unsigned one is 403.
3. "YES" from the customer confirms their only waiting order; "না" cancels it; "yes" with two waiting orders
   changes nothing and asks which one; "YES 1002" confirms 1002 only.
4. A reply from another company's customer never touches this company's orders.
5. Throttle: a 4th SMS or one within 10 minutes is refused; an opted-out customer gets none.
6. A Twilio error leaves the order pending with the error shown.

## Files

New: `integrations/twilio_sms.py`, `services/sms_service.py`, `models/sms.py`, `schemas/sms.py`,
`utils/phone.py`. Changed: `api/v1/webhooks.py`, `api/v1/orders.py`, `api/v1/tenants.py`,
`api/v1/platform.py`, `services/platform_service.py`, `services/order_service.py`,
`integrations/dev_fakes.py`, `requirements.txt`, `specs/SPEC-BE-001.md`.
