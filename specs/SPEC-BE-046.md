# SPEC-BE-046: Campaign Wizard — Write / Edit Creative Variants

Status: IMPLEMENTED (2026-09-30), plan approved by the user; verified on live Postgres (rolled-back txn).

## Purpose
Make the **Creative** step usable without AI, and let users edit AI variants, as the mockup text says ("Pick one or edit before continuing"). Today the only way to get variants is `POST /content/creatives`, which returns **503 "No LLM provider is configured"** because `backend/.env` has `LLM_PROVIDER=mock`. Every ad manager lets you write your own ad copy; AI generation is an add-on.

## Scope
In scope: create a creative from user-written variants, and edit one variant's text.

Not in scope: image or video upload, and AI moderation of hand-written copy (no provider is configured). AI generation itself is unchanged: with a real `LLM_PROVIDER`/`LLM_API_KEY` in `backend/.env` it works as SPEC-BE-029/030 describe.

## Contract
`POST /api/v1/content/creatives/manual` (manager+) → 201 `CreativeAssetRead` (the existing schema)
`{ channel, campaign_id?, title?, variants: [{ headline (1-120), description (0-500) }] (1-5) }`
The first variant is selected automatically (`selected_variant_index = 0`).

`PATCH /api/v1/content/creatives/{asset_id}/variants/{index}` (manager+) → 200 `CreativeAssetRead`
`{ headline?, description? }` with the same limits. An index out of range gives 404. Another tenant's asset gives 404.

## Functional rules
1. **Manual creatives:** the row gets `format = "ad_text"` (same as generated ones), `status = draft`, `generated_by_model = NULL`, and `metadata.source = "manual"`. `campaign_id`, when given, must be the tenant's campaign (422 otherwise), the same check the generate endpoint does.
2. **Editing** replaces only that variant's text in the `variants` jsonb. It records `metadata.edited_indexes` (so a human-edited AI variant stays traceable) and keeps the selection unchanged.
3. Both actions write an audit row (`content.creative_manual`, `content.variant_edit`).
4. Text is trimmed. Blank headlines are rejected (422).

## Acceptance criteria
1. A manual creative persists with the given variants, variant 0 selected, source "manual", and an audit row. Viewer gets 403. Bad input gets 422.
2. Editing changes exactly one variant, records it in `edited_indexes`, and writes an audit row. A bad index or another tenant's asset gives 404.
3. `POST /content/creatives` and `/select` behave exactly as before.

## Target files
- backend/app/schemas/content.py
- backend/app/services/content_service.py
- backend/app/api/v1/content.py
