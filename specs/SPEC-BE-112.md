# SPEC-BE-112: Unified inbox — channel picker, threads, replies, WhatsApp Cloud API

Status: IMPLEMENTED (2026-10-22). 44/44 rolled-back checks with dev fakes (SocialAPI, WhatsApp Cloud, Twilio). Not yet run against Meta: needs PilotSonic's Meta app with WhatsApp + Embedded Signup configured (Super admin › WhatsApp app). The old `integrations/whatsapp.py` stub was removed. UI in SPEC-FE-076 (Command Chat → Inbox tab).

## Decisions (user, 2026-10-21)

- Messenger and Instagram DMs come from **SocialAPI** (SPEC-BE-083, read live, already built).
- **WhatsApp Business** is added directly through the **WhatsApp Cloud API** (Meta).
- **SMS** threads come from SPEC-BE-108 (Twilio).
- Website/email conversations already stored in `conversations` stay as they are.

## What WhatsApp needs (documented for the operator)

- PilotSonic's Meta app with the WhatsApp product, set up as a Tech Provider, with **Embedded Signup**
  configured (a configuration id). Business verification and app review for `whatsapp_business_messaging`
  and `whatsapp_business_management` are required before other companies can connect.
- Webhook URL `https://api.pilotsonic.com/api/v1/webhooks/whatsapp` with a verify token, subscribed to
  `messages`.
- Free-form replies only within 24 hours of the customer's last message; after that Meta requires an
  approved template (templates are not in this spec: such a reply is refused with that reason).
- Until the Super admin fills these in, WhatsApp shows "Not set up by PilotSonic yet" and no connect button.

## Requirements

- **FR1 `GET /inbox/channels`** → the channels this company can use now: `[{key, platform (messenger |
  instagram | whatsapp | sms | web | email), source (socialapi | whatsapp_cloud | twilio | local), account_id,
  name, status (connected | needs_attention), can_send_media}]`. Only configured, connected, allowed
  (SPEC-BE-103) channels appear. Multiple accounts per platform are separate entries.
- **FR2 `GET /inbox/conversations`** `?channel=<key>|all&q&status=open|pending|resolved&unread=true&assignee=me
  &cursor` → `{items[{key, channel, conversation_id, customer {name, handle, phone?, avatar?},
  last_message {preview, at, direction}, unread, status, assignee, is_sample}], next_cursor}`.
  - Local sources (whatsapp, sms, web, email) read `conversations` + `messages`.
  - SocialAPI channels call `socialapi_service` (live). `all` merges local + SocialAPI by last message time;
    a SocialAPI error marks that channel `needs_attention` and still returns the rest.
  - `is_sample`: `conversations.metadata.sample = true` (demo data) is labelled; real synced rows never are.
- **FR3 `GET /inbox/conversations/{key}/messages`** → messages oldest first with direction, sender, body,
  attachments, `sent_at`, `delivery` (pending | sent | delivered | read | failed + error), AI-draft flag.
  Opening marks inbound messages read (`messages.read_at`).
- **FR4 `POST /inbox/conversations/{key}/messages`** `{body, media_ids?}` (agent+): sends through the right
  channel (SocialAPI, WhatsApp Cloud, Twilio), stores outbound local messages with the provider id and
  `delivery`. Media only where `can_send_media`. WhatsApp outside 24 h → 409 with the reason. The existing
  AI-draft routes (SPEC-BE-007) keep working for local conversations.
- **FR5 `PATCH /inbox/conversations/{key}`** `{status?, assignee_id?, tags?}` (agent+; local only — SocialAPI
  conversations can't be assigned, 409). Assignee must be a user of the company.
- **FR6 Customer panel.** Local conversations link `customer_id` → SPEC-BE-109 summary. SocialAPI threads show
  the participant and a "Link to customer" action (`POST /inbox/conversations/{key}/link {customer_id}`,
  stored in `tenants.settings.socialapi.links`) — no guessing by name.
- **FR7 WhatsApp connect.** `GET /integrations/whatsapp/connect` (Embedded Signup url with signed state) →
  `POST /integrations/whatsapp/callback {code, waba_id, phone_number_id}` → token exchange, `POST
  /{waba_id}/subscribed_apps`, encrypted storage in `integrations` (provider `whatsapp`), status shown with
  token expiry. Disconnect deletes the row. Super admin group `whatsapp_app` = `{config_id, verify_token}`
  (app id/secret reused from `meta_app`).
- **FR8 WhatsApp webhook.** `GET /webhooks/whatsapp` answers the verify challenge. `POST` checks
  `X-Hub-Signature-256` with the Meta app secret (403 otherwise), dedupes by message id / status id in
  `webhook_events`, routes by `phone_number_id` → company, upserts the customer by phone, appends to the
  company's open `whatsapp` conversation (new if none), and updates delivery statuses.
- **FR9 Dev fakes.** `dev_fakes` answers WhatsApp Cloud (`graph.facebook.com/*/messages`).

## Acceptance criteria (live DB, rolled back, dev fakes)

1. A company with SocialAPI Messenger + WhatsApp + Twilio lists 3 channels; without Twilio, 2.
2. A signed WhatsApp webhook creates the customer, conversation and message once (twice = once); an unsigned
   one is 403; a status update marks the message delivered.
3. A reply goes out on the right channel and is stored; after 24 h WhatsApp is 409.
4. `all` merges and sorts; a SocialAPI failure leaves the local items and flags the channel.
5. Another company's conversation key is 404; sample conversations are flagged.

## Files

New: `api/v1/inbox.py`, `services/inbox_service.py`, `schemas/inbox.py`, `integrations/whatsapp_cloud.py`
(the stub `integrations/whatsapp.py` is replaced by it and removed). Changed: `api/v1/webhooks.py`,
`api/v1/integrations.py`, `services/platform_service.py`, `services/socialapi_service.py`,
`integrations/dev_fakes.py`, `api/router.py`.
