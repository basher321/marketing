# SPEC-BE-048: Knowledge Base — Policies API, full FAQ management, policies in AI grounding

Status: IMPLEMENTED (2026-09-30), plan approved by the user; verified on live Postgres (rolled-back txn), including grounding (enabled + in-effect policies only; disabled FAQs excluded).

## Purpose
Back the Knowledge Base tabs (SPEC-FE-033). A KB in marketing and support tools (Intercom, Zendesk, HubSpot) is where the business writes down what the AI may say: policies, FAQs, delivery terms and product facts. The live `policies` table exists, but it has no API and the AI never reads it. FAQs can only be listed and added.

## Scope
In scope:
- `policies` CRUD.
- FAQ edit, delete and enable/disable.
- Enabled policies added to the AI's reply grounding.

Not in scope: file or PDF upload, embeddings or vector search (none exist live), and policy versioning.

## Live tables (authoritative)
`policies`: policy_type varchar, title, body, structured_rules jsonb, enabled, effective_from, effective_until.
`faqs`: question, answer, channels channel_type[], enabled (plus defaults).

## Contract
- `GET /api/v1/policies` → `{count, items:[PolicyRead]}`. Order: policy_type, then title.
- `POST /api/v1/policies` (manager+) → 201.
- `PATCH /api/v1/policies/{id}` (manager+) → 200.
- `DELETE /api/v1/policies/{id}` (manager+) → 204.

```
PolicyRead = { id, policy_type, title, body, enabled, effective_from, effective_until, updated_at }
Create/Update: policy_type in (returns, refunds, exchanges, warranty, shipping, payment,
  privacy, terms, other); title 1-255; body 1-20000; enabled (default true);
  effective_from / effective_until optional (until > from)
```
- `PATCH /api/v1/faqs/{id}` (manager+): `{question?, answer?, channels?, enabled?}` → 200 FAQItem. It now also returns `enabled`.
- `DELETE /api/v1/faqs/{id}` (manager+) → 204.
- `GET /api/v1/faqs` is unchanged, plus an `answer` and `enabled` per item so the tab can show and edit them.

## Functional rules
1. Everything is tenant-scoped. Another tenant's row returns 404.
2. **Grounding:** `ai/retrieval.retrieve_grounding` also searches enabled policies that are in effect today (title + body), labelled `policy`. Reply drafts can then cite "Return policy". The existing kb_document and FAQ sources are unchanged.
3. Every write is audited: `policy.create`/`update`/`delete`, `faq.update`/`delete`.

## Acceptance criteria
1. Policy CRUD works with validation (422) and roles (403 for viewer), and the rows persist exactly.
2. FAQ edit, delete and toggle persist. A disabled FAQ is excluded from grounding (already the rule).
3. A reply-grounding call for "return" finds an enabled return policy and skips a disabled or expired one.

## Target files
- backend/app/models/policy.py, schemas/policy.py, services/policy_service.py, api/v1/policies.py (new domain), and api/router.py (registration)
- backend/app/schemas/faq.py, services/faq_service.py, api/v1/faqs.py
- backend/app/ai/retrieval.py
