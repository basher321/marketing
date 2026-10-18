# SPEC-BE-101: Super admin — software-wide API keys; companies only connect their own accounts

Status: IMPLEMENTED (2026-10-10). The UI is SPEC-FE-068; the ads and Skip parts are SPEC-BE-102. DDL applied; the Super admin
(`pilotsonic-admin`) exists and pilotsonic's AI and SocialAPI keys were copied in. Verified on the live DB with dev fakes
(rolled back): AC1–AC5 pass; command eval 32/32; ruff/mypy at the baseline. **Deviation:** `POST /socialapi/key/test`
still answers (it checks the company's managed brand key, used by the "Provided by PilotSonic" card's check button)
instead of 409; save and delete are 409.

## The user's rule and decisions

- "Each company will connect only its fb or tiktok page or others socila media page only not they will provide any
  api keys. Each api keys will use for all company."
- "create an admin account for this software called Super admin."
- **Decisions (2026-10-10, AskUserQuestion):**
  - AI keys: **shared only**.
  - The software's keys are kept on **an admin screen**.
  - **Copy** pilotsonic's saved AI and SocialAPI keys in as the first software keys (its Groq key is invalid and is left
    out).
  - Companies' already-connected pasted tokens **keep working**.
  - Ads: **Zernio first** (SPEC-BE-102).
  - Super admin email: **superadmin@pilotsonic.com**.
  - **Approve** the two new tables and the whole build.

## Today

- **AI Models (SPEC-BE-053/088):** each company's own keys, in `tenants.settings.llm_providers`. Every AI feature gets
  them through `ai_model_service.resolve_chain / provider_key / image_model / video_model`.
- **SocialAPI (SPEC-BE-083):** each company pastes its own key, and every list shows all accounts under that key.
- **Integrations (SPEC-BE-052):** pasted-token forms for the Facebook Page, Instagram, TikTok, LinkedIn and every ad
  platform.
- **Server settings in `backend/.env`:** Zernio (`ZERNIO_API_KEY`) and the sign-in apps (`META_*`, `TIKTOK_CLIENT_*`,
  `LINKEDIN_CLIENT_*`, all empty).

## Requirements

- **FR1 (Super admin):**
  - **The account:** a Super admin in its own system workspace, `pilotsonic-admin` ("PilotSonic Super Admin", no
    business data). It signs in on the normal login page (Workspace `pilotsonic-admin`, superadmin@pilotsonic.com) with a
    generated password, shown once.
  - **Who is Super admin:** a row in the new table `platform_admins`. No route adds or removes rows, so nobody can promote
    themselves from inside the app.
  - **Access:** `dependencies.require_super_admin`; anyone else gets a 404 on `/platform/*`. `GET /platform/me` →
    `{super_admin}` for every signed-in user, so the UI knows whether to show the screen.
- **FR2 (the software's key store):**
  - **Table:** the new `platform_settings (key text PK, value jsonb, updated_by uuid, updated_at)`. Secrets inside a value
    are Fernet-encrypted (`*_enc`, `ENCRYPTION_KEY`), never returned (only masked) and never logged. Every change is
    audited under the Super admin's workspace.
  - **What it holds:**
    - `llm_providers`: the same shape SPEC-BE-053 stores per company (key, model, image/video model, enabled, order, last
      error / last OK).
    - `socialapi`: the master key.
    - `zernio`: the key.
    - `meta_app`, `tiktok_app`, `linkedin_app`: the sign-in apps.
  - **Fallback:** a value that isn't set falls back to `backend/.env`, so nothing that works today stops.
  - **Reading:** values are read with a short cache (30 s, cleared on save).
- **FR3 (AI, shared only):**
  - **Every AI feature** uses the software chain from `platform_settings.llm_providers`, in its order, with today's
    fallback rules. Companies' saved keys are ignored but kept in the database, so this can be undone.
    `llm_client` uses the software chain even for callers that pass no company. The `.env` `LLM_*` provider stays the
    last fallback, and with nothing set the app boots with mock / "unavailable" answers as today.
  - **Super admin routes:** `/platform/ai-models` (list / save key + model / order / delete key / test / live models)
    reuse the SPEC-BE-053 service logic, pointed at the software store.
  - **Company routes:** `GET /ai-models` returns the software's providers, with no key and no masked key. PUT / DELETE /
    order / test / models and the MCP tool routes answer 409 "AI keys are provided by PilotSonic". The company keeps its
    creative order and its slideshow voiceover and music.
  - **Messages:** errors say "PilotSonic's AI isn't set up yet (the Super admin adds the keys)", never "add a key in AI
    Models".
  - **Embeddings `auto`:** uses the software's OpenAI or Gemini key when `EMBEDDINGS_API_KEY` is empty.
- **FR4 (SocialAPI, one master key, isolated per company):**
  - **Per company, on first use:** the master key creates the company's brand and a **brand-restricted SocialAPI key**
    (`POST /v1/keys {name, brand_ids: [brand], scopes}`, every scope a restricted key may have). It's stored encrypted in
    `tenants.settings.socialapi` with `managed: true` and the key id.
  - **Isolation:** everything the company reads or writes goes through that key, so SocialAPI itself hides other brands
    (another brand's ids are a 404).
  - **Through the master key, with the company's brand only:** connect / select / assign a Page (brand admin
    operations), and account analytics (not allowed for restricted keys; the account must be in the company's list first).
  - **Company keys:** routes to save / test / delete one answer 409, and an existing pasted company key is set aside
    (`own_key_enc`).
- **FR5 (connect only):**
  - **No new pasted tokens:** `PUT /integrations/{provider}` refuses pasted credentials for facebook, instagram, tiktok,
    linkedin and every ad platform with 409: "Connect your page with the Connect button, or through Zernio / SocialAPI."
  - **Existing connections keep working,** and can be tested and disconnected.
  - **Unchanged:** Shopify, WooCommerce, WhatsApp, HubSpot and email (a company's own store, CRM or mail server).
- **FR6 (sign-in apps and Zernio):** `meta.py`, `facebook.py`, `tiktok.py`, `linkedin.py`, `meta_ads.py` and `zernio.py`
  read their app credentials / key through `platform_service` (the admin screen first, then `.env`).
- **FR7 (production):** the startup check no longer requires `LLM_PROVIDER` to be real, because the keys now come from
  the Super admin screen. `fixture` is still refused.

## DDL (additive, approved)

```sql
CREATE TABLE platform_admins (
  user_id    uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE platform_settings (
  key        text PRIMARY KEY,
  value      jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_by uuid REFERENCES users(id) ON DELETE SET NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);
```

## Acceptance criteria (live DB, rolled back; dev fakes)

- **AC1:**
  - `/platform/*` is 404 for a company owner and works for the Super admin.
  - `GET /platform/me` tells the two apart.
  - Nobody can add a Super admin through the API.
- **AC2:**
  - The Super admin saves an AI key and model.
  - A company with no keys of its own gets real answers from it (chat, image provider ready).
  - A company's own saved keys are ignored.
  - Company key routes answer 409, and `GET /ai-models` shows no key.
- **AC3:**
  - With the master SocialAPI key, two companies each get their own brand and restricted key.
  - A lists only its accounts, and B's account id is 404 for A.
  - Company key routes answer 409.
- **AC4:**
  - Pasting a Facebook / TikTok / Meta Ads token is 409.
  - An existing pasted connection still works.
- **AC5:**
  - With no keys anywhere, the app boots and the chat says AI isn't set up.
  - The command eval is 31/31; ruff and mypy are at the baseline.

## Files

- **Changed:** `config.py` (+ SPEC-BE-003), `dependencies.py`, `api/router.py`, `services/ai_model_service.py`,
  `api/v1/ai_models.py`, `ai/llm_client.py`, `ai/embeddings.py`, `ai/speech.py` and `ai/creative_providers.py` (texts),
  `services/socialapi_service.py`, `integrations/socialapi.py` (`create_key`), `services/integration_service.py`,
  `integrations/{zernio,facebook,tiktok,linkedin,meta_ads}.py` (credentials through `platform_service`),
  `integrations/dev_fakes.py` (`/keys`, restricted keys), `services/tenant_service.py` (reset keeps the managed key).
- **New (approved with the build):** `services/platform_service.py`, `api/v1/platform.py`, `schemas/platform.py`.

## Amendment A (2026-10-11): stale company brands and keys

- **Problem:**
  - tech-to-web got a brand and key under one master key (02:57 UTC).
  - That brand or key was then deleted in SocialAPI.
  - The Super admin saved another master key (03:18).
  - The saved company key was never re-checked, so every call failed with "the API key was rejected".
- **Fix (`services/socialapi_service.py`):**
  - The company config stores `master_fp`, the first 16 hex characters of the master key's SHA-256.
  - **Master key changed** (or no fingerprint on a managed config): the next `_key()` finds or creates the brand by name
    under the current master and makes a new restricted key.
  - **SocialAPI rejects the company key (401):** `_heal()` checks the brand with the master key, keeps it if it exists,
    rebuilds the key, and `_call` / `test_key` retry once. A key still rejected is recorded and returned as before; it
    never loops.
  - **No master key:** the company keeps its own key.
- **Verified:** 7/7 with SocialAPI stubbed, rolled back. Then live:
  - At the user's request, the `Default` brand was deleted in SocialAPI, which disconnected its Facebook page "Shek
    Muhammad Raihan".
  - pilotsonic's stale SocialAPI data was cleared.
  - tech-to-web was rebuilt into brand "Tech To Web (tech-to-web)", and its key test says connected.
