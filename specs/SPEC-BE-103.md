# SPEC-BE-103: Super admin — per-company access to PilotSonic's API keys

Status: IMPLEMENTED (2026-10-11). The UI is SPEC-FE-069. No DDL (one new `platform_settings` row). Verified on the live
DB, rolled back: AC1–AC9 pass (21 API checks, plus 7 service checks with the Meta and TikTok apps patched as set up).
ruff and mypy are at the baseline.

## The user's request and decisions

- "make a permission options for use of api keys for all companies that will perform by superadmin, so that super admin
  can control api keys for each company."
- Context: a company's "Accounts via SocialAPI" showed `SocialAPI: brands_limit_reached`. PilotSonic's SocialAPI plan
  holds 2 brands (`PilotSonic`, `Default`), so the first use by any other company failed when its brand was created.
- **Decisions (2026-10-11, "go ahead your recommendation"):**
  - A new company gets **everything on** by default.
  - Switching a **sign-in app** (Meta, TikTok, LinkedIn) off blocks **new connections and token refreshes**. Tokens
    already issued run out on their own. SocialAPI, Zernio and AI stop at once, because every call uses PilotSonic's key.
  - **Embedding search** (one server key, SPEC-BE-087) stays outside the switch.

## Requirements

- **FR1 Store.** `platform_settings` key `company_access` = `{tenant_id: {group: false}}`. A missing company or group is
  allowed; only an explicit `false` blocks. Switching a group back on removes its entry, and an empty company entry is
  removed. Only `/platform/*` writes it.
- **FR2 Groups.** `ai`, `socialapi`, `zernio`, `meta_app`, `tiktok_app`, `linkedin_app`
  (`platform_service.ACCESS_GROUPS`).
- **FR3 Routes (Super admin only, 404 for anyone else).**
  - `GET /platform/companies?q=&page=&page_size=` → `{items, total, page, page_size, groups}`. Each item has
    `tenant_id, name, slug, status, created_at, access{6 bools}, socialapi_brand, socialapi_error, zernio_profile`.
    `q` matches the name or slug.
  - `PUT /platform/companies/{tenant_id}/access {access: {group: bool}}` → the company's six switches. An unknown group
    is 422; an unknown company is 404. Each save is audited as `platform.company_access_saved` in the Super admin's
    workspace (company, enabled, disabled).
- **FR4 Enforcement.** `platform_service.allowed(tenant_id, group, db)` / `require()` (403 with `BLOCKED[group]`, e.g.
  "PilotSonic hasn't enabled SocialAPI for your company. Contact PilotSonic support."). A call with no company (server
  jobs, embeddings) is always allowed.
  - **ai:**
    - `ai_model_service.resolve_chain` returns `[]` and `provider_key` returns None.
    - `llm_client.complete / complete_with_usage / complete_vision` raise `LLMProviderError(BLOCKED["ai"], 403)`, with no
      `.env` or mock fallback.
    - `speech.transcribe/speak` and `generation_service.start` raise 403.
    - `creative_providers.generate` raises `AllProvidersFailed`, which also covers jobs that were already queued.
    - The Command Chat reply names the block.
  - **socialapi:** `socialapi_service._key` (every call; no brand or key is made) and `list_accounts`.
  - **zernio:** `zernio_service.profile_id` (every call) and `callback`. The chat's `zernio_ads` context is left out.
  - **meta_app:** `integration_service.meta_connect_url / meta_callback`, `social_oauth_service.connect_url / callback`
    (flow `meta`).
  - **tiktok_app / linkedin_app:** `social_oauth_service.connect_url / callback`. `_needs_refresh` is false, so neither
    `ensure_fresh` nor the `social_token_refresh` job renews these tokens.

## Acceptance criteria (live DB, rolled back)

- AC1 A non-admin gets 404 on both routes; a company owner can't change its own access. **Pass.**
- AC2 The list finds a company by slug, with all six switches on by default. **Pass.**
- AC3 A blocked company gets 403 with the message from SocialAPI accounts and connect, and from Zernio status. **Pass.**
- AC4 Meta ads connect and callback, and TikTok sign-in and callback, give 403 when the app is set up (503 "not set up"
  still comes first). A group left on is not blocked. **Pass.**
- AC5 Blocked AI: the chain is empty, the key is None, both completion calls give 403 and speech gives 403. The Command
  Chat reply says "hasn't enabled AI". **Pass.**
- AC6 Another company is unaffected. **Pass.**
- AC7 Switching everything back on removes the company's entry. **Pass.**
- AC8 422 for an unknown group, 404 for an unknown company, and one audit row per save. **Pass.**
- AC9 A token refresh is skipped while blocked and resumes when the app is switched back on. Nothing persists after the
  rollback. **Pass.**

## Files

`services/platform_service.py`, `api/v1/platform.py`, `schemas/platform.py`, `services/ai_model_service.py`,
`ai/llm_client.py`, `ai/speech.py`, `ai/creative_providers.py`, `services/generation_service.py`,
`services/orchestrator_service.py`, `services/socialapi_service.py`, `services/zernio_service.py`,
`services/integration_service.py`, `services/social_oauth_service.py`.
