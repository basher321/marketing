# SPEC-BE-007: Customer Service Inbox — Open Conversations List (+ Customer model realignment)

Status: APPROVED (2026-09-29) — open decisions resolved per recommendations: handoff marker in conversations.metadata; `new` and `replied` returned; most recent customer message first; /customers realigned and kept.

## Purpose
Back the Customer Service page's "Open Conversations (N)" table with real data: per conversation, the customer's name, channel, topic, how long the customer has been waiting, and an inbox status matching the mockup's badges ("Draft ready", "Auto-replied", "Escalated"). SPEC-FE-013 already targets this spec, which was referenced (by SPEC-BE-008, SPEC-FE-013, and comments in `conversation_service.py`) but never written.

Verified on the live DB (2026-09-29):
- `GET /api/v1/conversations` returns only `{id, channel, status, assigned_user_id}` — no customer, topic, waiting time or inbox status.
- `GET/POST /api/v1/customers` return 500: the `Customer` model maps `full_name`/`extra_metadata`/JSON `tags`, but the live `customers` table has `first_name`, `last_name`, `metadata` (jsonb), `tags` (text[]), `deleted_at`.
- No column records a handoff: SPEC-BE-026's handoff writes only an audit row, so "Escalated" cannot be derived reliably.

## Scope
In scope:
- `GET /api/v1/conversations`: the inbox list described below (replaces the current thin response).
- A durable handoff marker written by the existing SPEC-BE-026 handoff action (Functional rule 6).
- Realign the `Customer` model to the live `customers` table, and make the existing `GET/POST /api/v1/customers` work against it (Open decision 4).

Explicitly NOT being built by this spec:
- Message ingestion from channels (webhooks stay stubs), so `topic` and customer names are only as populated as the data is.
- Automatic (unattended) AI replies. "Auto-replied" is derivable (rule 4) but no code path produces it yet.
- Resolving/archiving conversations, assignment UI, pagination, search/filtering, customer update/delete.
- Any change to draft generation, edit or send (SPEC-BE-026/028), beyond the handoff marker.

## Contract
`GET /api/v1/conversations` (any authenticated role) → 200
```
{ "count": int,                       # == len(items): the "Open Conversations (N)" heading
  "items": [ {
      "id": str,
      "customer_name": str | null,     # rule 3
      "channel": str,                  # live channel_type value (facebook, instagram, whatsapp, messenger, email, sms, web, tiktok)
      "topic": str | null,             # conversations.topic, as stored
      "waiting_since": datetime | null,# UTC; the customer's latest message time (rule 5)
      "inbox_status": "escalated" | "draft_ready" | "new" | "auto_replied" | "replied",
      "status": str                    # the raw live conversation_status (open | pending)
  } ] }
```
`GET /api/v1/customers` → 200 `[{id, first_name, last_name, email, phone, created_at}]`; `POST /api/v1/customers` body `{first_name?, last_name?, email?, phone?}` → 201 same shape (Open decision 4).

## Functional rules
1. **Which conversations:** the caller's tenant only (explicit `tenant_id` filter), with live `status` in (`open`, `pending`). `resolved` and `archived` are not in the inbox.
2. **Order:** most recent customer message first (`waiting_since` descending, NULLs last, then `created_at` descending, then `id`).
3. **customer_name:** `first_name + " " + last_name`, trimmed, from the linked `customers` row (same tenant, not soft-deleted). If that is empty, fall back to the customer's email, then phone. `null` if there's no linked customer or nothing to show. The mockup's "Sarah A." abbreviation is a frontend formatting concern.
4. **inbox_status** is derived per conversation, first matching rule wins:
   1. `escalated`: the conversation has a handoff marker (rule 6) and no reply was sent after it.
   2. `draft_ready`: the conversation has a pending AI draft (SPEC-BE-026's definition: a `messages` row with direction `outbound`, sender_type `ai`, sent_at NULL).
   3. `new`: the customer's latest message is newer than the latest sent reply (or no reply was ever sent). The customer is waiting and nothing is drafted.
   4. `auto_replied`: the latest sent reply is from the AI (sender_type `ai`) with no human approval (`approved_by` NULL).
   5. `replied`: otherwise. The latest sent reply was sent or approved by a human.

   Here, a "sent reply" is an outbound message with `sent_at` set and sender_type `agent` or `ai`. `new` and `replied` have no badge in the mockup (see Open decision 2).
5. **waiting_since:** the latest inbound `customer` message's `created_at` for the conversation (from `messages`, the source of truth). The `conversations.last_customer_message_at` column is not relied on, because nothing maintains it yet. `null` if the customer never wrote. Returned in UTC; the frontend computes "2m"/"1h".
6. **Handoff marker:** SPEC-BE-026's `POST /conversations/{id}/handoff` additionally sets `conversations.metadata.handed_off_at` (ISO-8601 UTC) and `metadata.handed_off_by` (user id). Its existing audit row and response are unchanged, and it still does not change `conversations.status`. A later sent reply (`sent_at` > `handed_off_at`) ends the escalation (rule 4.1).
7. **Efficiency:** the list is computed with a fixed number of queries, not one query per conversation.
8. **Customer model:** map the live columns (`first_name`, `last_name`, `email` (citext), `phone`, `tags` (text[]), `metadata` (jsonb), `deleted_at`), and remove `full_name` and the JSON-typed `tags`/`extra_metadata` mappings. `GET /customers` excludes soft-deleted customers and filters by tenant. `POST /customers` creates one customer for the caller's tenant.

## Edge cases
- A conversation whose `customer_id` points to another tenant's customer (should not exist) shows `customer_name: null`. The join also filters on `tenant_id`.
- A conversation with no messages: `waiting_since: null`, `inbox_status: "new"` (no reply ever sent).
- Several pending drafts: still one `draft_ready` row per conversation.
- A handoff followed by a customer message and no reply: still `escalated`.
- A soft-deleted customer: the name falls back to `null`.

## Non-functional rules
- Plain service functions with explicit `db` + `tenant_id`, type hints, structlog; thin routes with `response_model` and explicit `status_code`.
- Timestamps normalized to UTC.
- The mapping rules above (4, 5, 6) are documented as code comments.
- No new files; no schema (DDL) changes; the handoff marker uses the existing `metadata` jsonb column.
- Must not change SPEC-BE-021 metrics or SPEC-BE-026/028 draft behavior, apart from rule 6.

## Acceptance criteria
Verified on the live DB in a rolled-back transaction, with real register/login tokens, seeding customers, conversations and messages via SQL:
1. The list returns only this tenant's `open`/`pending` conversations (resolved/archived excluded), `count == len(items)`, in rule 2 order.
2. `customer_name` follows rule 3, including the email/phone fallbacks and `null` when unlinked.
3. Each `inbox_status` value is produced by a conversation seeded for it (escalated, draft_ready, new, auto_replied, replied), including "a reply after handoff ends escalated".
4. `waiting_since` equals the latest customer message time in UTC.
5. Handoff through the real endpoint sets the metadata marker and still writes exactly one audit row, and the conversation then lists as `escalated`.
6. A second tenant's conversations and customers never appear.
7. `GET /customers` returns 200 with the live columns (no soft-deleted rows); `POST /customers` creates a row → 201.
8. The existing draft endpoints (GET/PATCH draft, send, generate) and `/conversations/cs-metrics` still return the same results.
9. After rollback, row counts equal their pre-run values.

## Assumptions (verified against the live DB, 2026-09-29)
- `conversations`: `customer_id` uuid (nullable), `channel` channel_type, `status` conversation_status (open, pending, resolved, archived), `topic` varchar (nullable), `metadata` jsonb NOT NULL, `last_customer_message_at` / `last_agent_message_at` timestamptz.
- `messages`: `direction` (inbound/outbound), `sender_type` (customer, agent, ai, system), `sent_at`, `approved_by`, `created_at`.
- `customers`: `first_name`, `last_name`, `email` citext, `phone`, `tags` text[], `metadata` jsonb, `deleted_at`.
- There is no draft table and no escalation column.
- *(Found during implementation, 2026-09-29)* `customers` has CHECK `customer_contact_required` (email IS NOT NULL OR phone IS NOT NULL) and UNIQUE `(tenant_id, email)`. `POST /customers` therefore returns 422 when both are missing and 409 on a duplicate email, never a database 500.

## Open decisions (to settle in the plan step)
1. **Handoff marker:** store it in `conversations.metadata` (recommended: explicit, cheap to read, no DDL), or derive escalation from `audit_log` rows (no write change, but it reads a partitioned audit table on every list call).
2. **The two statuses the mockup doesn't show:** return `new` and `replied` so every conversation has a truthful status (recommended; SPEC-FE-013 then maps them to a neutral badge), or hide conversations in those states from the inbox (then the count wouldn't match the real number of open conversations).
3. **Order:** most recent customer message first (recommended, the usual inbox convention), or longest-waiting first.
4. **`/customers` routes:** realign and keep `GET/POST /customers` (recommended: cheap once the model is fixed, and orders/CRM will need customers), or remove them because the mockup has no customers screen.

## Target files
- backend/app/models/customer.py
- backend/app/schemas/customer.py
- backend/app/services/customer_service.py
- backend/app/api/v1/customers.py
- backend/app/models/conversation.py
- backend/app/schemas/conversation.py
- backend/app/services/conversation_service.py
- backend/app/api/v1/conversations.py
