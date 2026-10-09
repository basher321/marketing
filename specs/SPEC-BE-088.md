# SPEC-BE-088: AI Models: OpenRouter and Ollama, one fallback order of six

Status: IMPLEMENTED (2026-10-09). Requested by the user: "add all model when any will active then
it will work claude openai genai groq openrouter ollama anyone and make this sequence".

## Context

Command Chat answered "the AI service is unavailable" for company `pilotsonic`, because both of
its saved AI Models were unusable:
- **Gemini:** HTTP 429, quota exceeded.
- **Groq:** the key is saved, but Groq answers HTTP 401 "Invalid API Key", and no model or enabled
  flag is set.

The working Claude key in `backend/.env` (`LLM_API_KEY`) was not used, because a company with its
own AI Models uses only those (SPEC-BE-053).

## Changes

1. **Providers** (`ai/providers.py`): `PROVIDERS` adds two entries, and the tuple order is the
   default fallback order (Claude → OpenAI → Gemini (GenAI) → Groq → OpenRouter → Ollama):
   - **OpenRouter** (`openrouter.ai/api/v1`, OpenAI-compatible, Bearer key);
   - **Ollama (local)** at `OLLAMA_BASE_URL` (new setting, default `http://localhost:11434/v1`,
     OpenAI-compatible, `needs_key=False`).
2. **Keyless provider** (`services/ai_model_service.py`): `_usable_key()` returns the saved key,
   `""` for a provider that takes none, or `None` when a needed key is missing. Enable, test, the
   model list and `resolve_chain` use it.
3. **Schemas** (`schemas/ai_model.py`): `ProviderName` gains `openrouter` and `ollama`;
   `AIModelOrder` accepts up to 6; `AIModelProvider.needs_key` is new.
4. **Frontend** (`components/integrations/ai-models.tsx`, `lib/types/integrations.ts`): the Ollama
   card needs no key ("No key needed for a local Ollama", "Download Ollama ↗"). The other cards
   are unchanged; all cards come from the backend list.
5. **pilotsonic setup:** done on the user's instruction through the same service the AI Models
   page uses, with the audit actor = the company's owner.
   - The `.env` Claude key was saved encrypted as Anthropic Claude, with `claude-sonnet-5-5`,
     enabled.
   - The order was set to the six above.
   - The Test button's check passed (1.7 s).

## Verification (2026-10-09)

- **Live chat:** "give me product list" through `send_message_and_plan` for pilotsonic (rolled
  back) gives a 1-step plan (`inspect_products`, which runs at once), answered by Claude.
  `succeeded`: 0 products, because pilotsonic has no products.
- **Running backend:** `/openapi.json` lists all six providers (the `--reload` server picked it up).
- **Ollama:** not installed on this machine (nothing answers on port 11434). It stays off until it
  is installed and a model is pulled.
- **Regressions:** SPEC-BE-085/087 suites pass (31/31, 18/18, 18/18, 20/20).
- **Lint and types:** `ruff` / `mypy` at their baselines, and `npx tsc --noEmit` is clean.

## Not done

- **pilotsonic's Groq key** stays saved but invalid (401): paste a new key on the Groq card.
- **OpenAI / OpenRouter** have no keys yet.

## Amendment (2026-10-09): every AI text feature uses the same chain

Requested by the user: "LLM model will be sequential failover claude openai genai groq and others
so that system can do its work … only video and image creation will be differ but not now. so make
this sequence for all AI".

- **Audit:** every AI text call goes through `llm_client` with `db` + `tenant_id`, so it uses the
  company's chain: Command Chat, AI reply drafts, the Campaign Wizard creative, the directive
  parser and planner, and Create with AI's plan/copy/review (`creative_providers` kind `llm`).
- **Fixed:** `POST /content/generate` (`content_service.generate_content`) called the AI without
  the company, so it used only the `.env` model (or the mock). It now takes `db` + `tenant_id`.
- **Unchanged by request:** image and video generation keep their own order (OpenAI → Gemini
  images, Veo → Sora video).
- **Not on the chain, by nature:** embeddings (SPEC-BE-087) use one platform key, because stored
  vectors must all come from one model; Claude and Groq have no embeddings API. The RAGAS judge
  (eval only) uses the company's first usable model, Claude included since this date.
- **Verified** in a rolled-back transaction, with the provider calls swapped for fakes: a fresh
  company's default order is Claude → OpenAI → Gemini → Groq → OpenRouter → Ollama. With Claude
  (500), OpenAI (429) and Gemini (bad key) failing, `/content/generate`, Command Chat and the
  reply drafter each tried them in that order and got Groq's answer. With all six failing, chat
  tried all six and answered "unavailable".


## Amendment (2026-10-09): OpenAI's newer models need `max_completion_tokens`

The user reported: "Test failed: HTTP 400: Unsupported parameter: 'max_tokens' is not supported with this
model. Use 'max_completion_tokens' instead." This was pilotsonic's `gpt-5.4-mini`.

- **Change:** `ai/providers.call` sends `max_completion_tokens` to OpenAI. Every OpenAI chat model accepts
  it, and GPT-5 and the o-series require it. Gemini, Groq, OpenRouter and Ollama keep `max_tokens`. If one
  of them answers 400 naming `max_completion_tokens` (an OpenAI model through OpenRouter, for example), the
  call is retried once with the new name, before the existing temperature retry.
- **Verified:** a real call to `gpt-5.4-mini` with pilotsonic's key returned "OK", both with the 5-token
  test limit and with `temperature=0`; nothing was saved. Stub eval 31/31; ruff and mypy are clean on the
  file.
- **Not changed:** `llm_client._complete_openai` (the `.env` SDK path, `LLM_PROVIDER=mock` here) still
  sends `max_tokens`.
