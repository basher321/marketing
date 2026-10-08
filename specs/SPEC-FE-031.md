# SPEC-FE-031: Campaign Wizard — Creative Step (write, edit, AI)

Status: IMPLEMENTED (2026-09-30), plan approved by the user; verified E2E (with LLM_PROVIDER=mock: 503 notice, then written, edited and selected variants persisted). Depends on SPEC-BE-046 and SPEC-FE-030. Amends SPEC-FE-016.

Implementation note: "Write your own" and "Generate with AI" are two tabs using the existing .tabs/.tab classes; "Write your own" is the default because no LLM provider is configured.

## Purpose
Make step 3 work with or without AI. The "AI-Generated Creative Variants" card (mockup markup, gradients, "✓ Selected"/"Select") stays, now attached to the campaign draft.

## Functional rules
1. **Two ways to get variants:**
   - **"Write your own"**: 1 to 3 headline/description pairs → `POST /content/creatives/manual` with the draft's `campaign_id` and channel.
   - **"Generate with AI"**: the existing form → `POST /content/creatives` with `campaign_id`. If the backend answers 503 (no LLM configured), show: "AI generation isn't set up (no LLM provider configured). Write your own variants instead, or add an LLM API key in backend/.env." and switch to "Write your own".
2. **Edit:** each variant card has "Edit", which opens inline headline and description fields. Saving calls `PATCH /content/creatives/{id}/variants/{index}`, and the card updates from the response.
3. **Select:** the existing select endpoint. "✓ Selected" reflects the persisted `selected_variant_index`.
4. **Continue to Budget →** saves `creative_asset_id` on the draft (SPEC-BE-044). It's disabled until a variant is selected. When the draft already has a creative, it is loaded (`GET /content/creatives/{id}`) and shown.
5. Channel for the creative: the draft's first chosen channel, or instagram if none is chosen yet.

## Acceptance criteria (verified E2E)
1. With `LLM_PROVIDER=mock`: the 503 message shows. Writing 3 variants creates a manual asset linked to the campaign (DB checked). Edit and select persist.
2. Continue stores `creative_asset_id` on the draft. Going Back and returning shows the same creative and selection.

## Target files
- components/campaigns/creative-variants.tsx
- lib/api/content.ts
- lib/types/content.ts
