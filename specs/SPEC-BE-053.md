# SPEC-BE-053: AI Models — per-company LLM keys with automatic fallback

Status: IMPLEMENTED (2026-09-30), plan approved by the user; verified on live Postgres (rolled-back txn) with mocked provider HTTP, including a real route (creative generation: Claude 429 → GPT answered).

Implementation notes (deviation from rule 2 and 3):
- The tenant ContextVar is **not** visible inside FastAPI endpoints (probed 2026-09-30: None in both sync and async routes). So `complete_with_usage`/`complete` take keyword-only `db` + `tenant_id`, and the 4 AI callers (ai/prompts/content_generator, intent_parser, planner, reply_drafter) pass them. Their "no provider" errors now say "Add one in Integrations › AI Models". The legacy `POST /content/generate` has no tenant and keeps the .env path.
- `last_error`/`last_ok_at` from live calls are written in their own short transaction (`record_outcome`), so the caller's session is never committed early.
- If every company model fails, `complete()` (legacy, text-only) falls back to the .env provider and then mock, as before, while `complete_with_usage` raises an LLMProviderError naming each failure.

## Amendment (2026-10-02): retired default models

Status: IMPLEMENTED (2026-10-02). Verified in a rolled-back transaction with mocked provider HTTP: the new Gemini and Groq defaults are listed; a 404 gives the retired-model hint and a 200 gives ok; a saved model isn't rewritten.

**Problem.** Two default models in the table below have been retired by their providers. Every Gemini and Groq setup that keeps the default fails with a 404 on Test and on every live call. Checked on 2026-10-02 against dev-shop's saved keys:
- Groq: `GET /openai/v1/models` no longer lists `llama-3.3-70b-versatile`. `openai/gpt-oss-120b` answers.
- Gemini: the API says "models/gemini-2.0-flash is no longer available". `gemini-2.5-flash` and `gemini-3.8-flash` answer (3.8 returned one 503 "high demand" before succeeding).
- OpenAI: `gpt-4o-mini` has no announced API shutdown (OpenAI deprecations page), so it stays. Anthropic `claude-sonnet-5-5` is current.

**Rules.**
1. New defaults: Gemini → `gemini-2.5-flash` (generally available and answered on the first try); Groq → `openai/gpt-oss-120b`. OpenAI and Anthropic are unchanged.
2. A saved model is never rewritten. Companies that saved a retired name (such as dev-shop) change it in the UI. Only a provider with no saved model picks up the new default.
3. When a provider answers HTTP 404, the error that `test_provider` returns and records gets the hint " — the model may be retired; change the Model field." appended, so the user knows what to fix.

**Acceptance criteria.**
1. `GET /ai-models` shows the new `default_model` values for Gemini and Groq.
2. With a mocked 404 from the provider, Test returns `ok: false` and an error ending in the hint. A mocked 200 returns `ok: true`.
3. A tenant's saved `model` is unchanged after the deploy.

**Target files.** backend/app/ai/providers.py (defaults), backend/app/services/ai_model_service.py (404 hint), and the Providers table below.

## Purpose
Let each company add several LLM providers in the app (Integrations › AI Models), in a priority order. When one fails (error, timeout, quota), the next one answers automatically. Today there is one provider, and it comes from `backend/.env`.

## Providers
| Provider | Default model (editable) | API (via httpx, no new SDK) |
|---|---|---|
| Anthropic Claude | claude-sonnet-5-5 | POST api.anthropic.com/v1/messages |
| OpenAI GPT | gpt-4o-mini | POST api.openai.com/v1/chat/completions |
| Google Gemini | gemini-2.5-flash (was gemini-2.0-flash, retired) | Gemini OpenAI-compatible endpoint (generativelanguage.googleapis.com/v1beta/openai/chat/completions) |
| Groq | openai/gpt-oss-120b (was llama-3.3-70b-versatile, retired) | POST api.groq.com/openai/v1/chat/completions |

**Cursor** is not included. Cursor is a code editor, not a model provider, and it has no public API for other apps to call. Its models come from the providers above.

## Contract
- `GET /api/v1/ai-models` → `{ providers: [{provider, label, enabled, model, priority, key_masked|null, last_error, last_ok_at}], env_fallback: {provider, configured: bool} }`
- `PUT /api/v1/ai-models/{provider}` (manager+): `{api_key? (empty = keep), model?, enabled?}`
- `PUT /api/v1/ai-models/order` (manager+): `{order:[provider,…]}`
- `POST /api/v1/ai-models/{provider}/test` (manager+): a tiny real completion ("Reply with OK") → `{ok, latency_ms, model, error?}`
- `DELETE /api/v1/ai-models/{provider}` (manager+): removes the key.

## Functional rules
1. **Storage:** `tenants.settings.llm_providers` holds `{provider: {key_enc, model, enabled, priority, last_error, last_ok_at}}`. Keys are Fernet-encrypted and never returned. (The `integration_provider` DB enum has no LLM values, so the `integrations` table isn't used; no DDL is needed.)
2. **Fallback chain in `llm_client`** (`complete_with_usage` and `complete`):
   - It resolves the calling tenant from the existing tenant ContextVar and tries its **enabled** providers in priority order.
   - On error, timeout (30 s) or HTTP 429/5xx it moves to the next provider and records `last_error`.
   - If the tenant has none, it uses today's `.env` provider (unchanged behavior).
   - If nothing is available, the existing mock/503 behavior applies.
   - The `llm_call` log span records `provider`, `model`, `attempts:[{provider, error}]`.
3. Each provider adapter maps usage tokens to the existing `LLMCompletion` (input_tokens, output_tokens). Existing callers (creative generation, planner, reply drafts) need no change.
4. Writes are audited (`ai_model.update`/`order`/`delete`/`test`), with no key material in the metadata.

## Acceptance criteria
1. With a local stub server standing in for the providers: provider A returns 500 → B answers. The result says provider B, and A's `last_error` is set.
2. With no tenant keys, the `.env` path is unchanged (the existing tests still pass). Keys are encrypted at rest and masked in GET. Viewer gets 403.
3. A real test call runs only if you provide a real key.

## Target files
- backend/app/ai/llm_client.py, backend/app/ai/providers.py (new: 4 httpx adapters)
- backend/app/schemas/ai_model.py, services/ai_model_service.py, api/v1/ai_models.py (new), and api/router.py (registration)

## Amendment (2026-10-02): no built-in models; the model list comes from the provider

Status: APPROVED (2026-10-02, user: "make it flexible for all model"; decision 4 = suggest, never auto-switch). Companion amendments: SPEC-BE-070 (image models), SPEC-FE-037 (the card).

**Why:** the code had a fixed default model per provider, used silently whenever the Model field was empty. Providers retire models without notice (gemini-2.0-flash, llama-3.3-70b-versatile, then gemini-2.5-flash "no longer available to new users" on 2026-10-02), so every default goes stale. Image models (`gpt-image-1`, `gemini-2.5-flash-image`) were constants the user couldn't change at all.

### Rules
1. **No default model in code.** `ProviderSpec.default_model` is removed. A provider is used (chain, test, enabled) only when the company chose a model. `GET /ai-models` returns `model: null` when none is chosen; `default_model` is removed from the response.
2. **Live model list.** `GET /api/v1/ai-models/{provider}/models` (manager+) calls the provider's own list endpoint with the saved key and returns `{ok, error, chat:[{id,label}], image:[{id,label}], suggested:{chat, image}}`:
   - OpenAI `GET /v1/models`, Anthropic `GET /v1/models`, Gemini `GET /v1beta/models`, Groq `GET /openai/v1/models`.
   - A provider error is returned in `error` (200), so the card can show it; no key saved → 409.
   - It's a read: no audit row, nothing stored.
3. **Chat vs image** (documented in `ai/providers.py`): Gemini reports `supportedGenerationMethods`; a model is chat if it supports `generateContent` and is not an image, embedding, TTS/audio/live or AQA model, and image if its name contains `image` and it supports `generateContent`. OpenAI and Groq don't report a type, so names decide: `gpt-image*` / `dall-e*` are image; embeddings, whisper/transcribe, tts/audio/realtime, moderation/guard, sora, legacy davinci/babbage are left out; the rest is chat. Anthropic models are all chat. Only OpenAI and Gemini have image models.
4. **Suggestion, never a silent choice.** `suggested` is the newest stable model matching a per-provider preference (Gemini `flash`, OpenAI `mini`, Anthropic `sonnet`, Groq `gpt-oss`; preview/experimental/lite skipped when a stable one exists). The UI pre-fills it; the user saves it. A listed model can still be refused by the provider (for example "not available to new users"), which is why Save & test exists.
5. **Enabling:** `enabled: true` needs a key **and** a model (422 "Choose a model before enabling."). A provider turns on by itself the first time it has both, unless it was switched off explicitly.
6. **Test:** no model → 409 "Choose a model first." On a 404, the result also carries `suggestions` (up to 5 chat models from the live list) and `suggested`, so the card can offer **Switch to X** (which saves, then tests). Nothing switches automatically.
7. `image_model` is a new optional field per provider (OpenAI and Gemini), set through the same `PUT /ai-models/{provider}`. Changing it is audited like `model`.
8. **Existing data:** companies keep their saved models. On 2026-10-02 only dev-shop has saved AI models, and both have a model set, so nothing stops working. A company with a key but no model would drop out of the chain until a model is chosen; the card says "Choose a model".

### Acceptance criteria (rolled-back transaction on live Postgres; provider HTTP mocked except where stated)
1. GET lists `model: null` for a provider without a chosen model, and no `default_model`.
2. `/models` sorts mocked OpenAI / Gemini / Groq / Anthropic list answers into chat and image per rule 3, with the suggestion per rule 4; a provider error comes back in `error`; no key → 409; viewer → 403.
3. Enable without a model → 422; saving key + model turns the provider on; `resolve_chain` skips a provider without a model.
4. Test without a model → 409; a mocked 404 returns the suggestions.
5. Image generation uses the saved `image_model`; without one, the image provider isn't available and readiness says why.
6. Real read-only check with dev-shop's saved Gemini and Groq keys: `/models` returns real lists (no completion call, no cost).
7. ruff / mypy add no new errors.

### Target files
`backend/app/ai/providers.py`, `backend/app/ai/creative_providers.py`, `backend/app/services/ai_model_service.py`, `backend/app/services/ai_campaign_service.py` (image readiness), `backend/app/schemas/ai_model.py`, `backend/app/api/v1/ai_models.py`. No new files, no DDL.
