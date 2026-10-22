# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

AI Orchestrator: a multi-tenant marketing automation platform. FastAPI backend
(e-commerce catalog/orders, customer conversations, campaigns, workflow
automation, and an AI orchestrator chat that turns natural-language requests
into approvable action plans), paired with a Next.js dashboard in `frontend/`.

**This file covers the backend.** The frontend (Next.js 15 + React 19 +
TypeScript, in `frontend/`) has its own authoritative guide,
`frontend/CLAUDE.md`. Read that before touching frontend code. There is no
`backend/migrations/`, no `backend/scripts/`, no `backend/tests/` (only
`backend/evals/`, the golden sets of SPEC-BE-085/086), no
`requirements-dev.txt`, and no backend `.env.example` (only a real
`backend/.env`). The frontend's env template is `frontend/.env.local.example`.
Verify with a directory listing before relying on any other path.

`ai_orchestrator_frontend(1).html` in the repo root is a static HTML mockup of
the dashboard. It is the reference the backend specs build toward ("matching
exactly what the HTML shows") — check it when a spec cites a card, table, or
column.

This is a **runnable skeleton**, not a finished product. Core plumbing (config,
security, multi-tenancy helpers, RBAC, the LLM client, the workflow engine, the
APScheduler lifecycle) is real. Domain work is being filled in one spec at a
time (see "Spec-driven workflow" below), and several ORM models do **not**
match the live Postgres schema (see "Live database vs ORM models") — read that
section before trusting any model.

**What's real vs. stubbed:**

- Implemented via specs (each is deliberately narrow — only what the HTML
  mockup shows; list/create/update/delete routes that used to exist in these
  domains were removed):
  - Inventory (SPEC-BE-005): `GET /inventory`, `GET /inventory/low-stock`,
    `POST /inventory/{inventory_id}/adjust` (manager+, writes an
    `inventory_movements` row + audit entry).
  - Products (SPEC-BE-008): `GET /products` only (sku, title, price, channels,
    status). Product CRUD was removed.
  - Scheduled posts (SPEC-BE-010): `GET /scheduled-posts/count` only (status
    `pending` or `scheduled`).
  - Ads (SPEC-BE-011): `GET /ads/ctr-7d` only — a documented placeholder that
    returns `0.0`, because no click/impression data exists anywhere in the
    schema yet. Never replace it with an estimate.
  - Brand settings (SPEC-BE-012): `GET /brand` (documented defaults before the
    first save), `PUT /brand` (manager+, upsert on `tenant_id`). Tone/style are
    `voice_config->'tone'/'style'` (0-100), the same keys
    `ai/retrieval.get_brand_voice()` reads.
  - FAQs (SPEC-BE-013): `GET /faqs` → `{count, items:[{id, question,
    channels}]}`, `POST /faqs` (manager+). `channels = []` means all channels.
  - Customer Service inbox (SPEC-BE-007): `GET /conversations` → `{count,
    items}` for `open`/`pending` conversations, with customer name, channel,
    topic, `waiting_since` and a derived `inbox_status` (escalated, draft_ready,
    new, auto_replied, replied). Handoff also records
    `conversations.metadata.handed_off_at`. `GET/POST /customers` match the live
    table (email or phone required; email unique per tenant).
  - Dashboard/Marketing backends (2026-09-29): `GET /campaigns/ad-spend-24h`
    (SPEC-BE-019, `analytics_events` metric `spend_cents`), `GET
    /analytics/activity` (SPEC-BE-022, audit_log + pending AI drafts + published
    posts, last 24h), `GET /campaigns` + `GET /scheduled-posts/calendar`
    (SPEC-BE-038), products list now carries `stock`/`low_stock`
    (SPEC-BE-008 amendment).
  - Workflows (SPEC-BE-034): `GET /workflows/{id}` and dry-run `POST
    /workflows/{id}/test`; live-enum deviations are listed in the spec's
    implementation notes.
  - E-Commerce tabs (2026-09-30), laid out after common e-commerce admin
    practice, since the mockup has only the tab labels: `GET /orders`
    (SPEC-BE-041, paginated, `status`/`q` filters); `GET /inventory` rows now
    carry sku, product title, variant label, location name, committed and
    low_stock (SPEC-BE-005 amendment; adjust works on the live DB); `GET/POST
    /pricing/rules` + `PATCH /pricing/rules/{id}` (SPEC-BE-042); `GET/POST
    /shipping/zones`, `POST /shipping/zones/{id}/rates`, `PATCH
    /shipping/rates/{id}` (SPEC-BE-043; the prefix was `/shipping-policies`).
    Writes are manager+ and audited. Applying pricing rules or shipping rates
    to orders is not built.
  - Campaign Wizard (2026-09-30), following the standard ad-manager flow:
    drafts `POST/GET/PATCH /campaigns`, `GET /campaigns/drafts` (SPEC-BE-044;
    wizard choices live in `campaigns.metadata.wizard`, daily cap =
    total ÷ calendar days in the tenant timezone); `GET/POST /audiences`
    (SPEC-BE-045); hand-written or edited creatives `POST
    /content/creatives/manual`, `PATCH /content/creatives/{id}/variants/{i}`
    (SPEC-BE-046, these work with `LLM_PROVIDER=mock`); `POST
    /campaigns/{id}/launch|pause|resume` (SPEC-BE-047). Launch reuses SPEC-BE-032's
    spend rule: when daily spend is over `tenants.ad_daily_cap_cents`, a
    non-owner's launch becomes a `campaign` approval item. Only an owner can
    approve one, and approving launches it. An owner's own launch counts as the
    approval. Launch creates `ad_groups`/`ads` rows; since SPEC-BE-054 a campaign
    with a facebook/instagram/messenger channel is also **published to Meta**
    (see below). Other channels are still internal-only.
  - Meta connect + publishing (SPEC-BE-054, 2026-10-01):
    - **Connect:** `GET /integrations/meta/connect` → `POST /integrations/meta/callback` → `POST /integrations/meta/select`. This is Facebook Login for Business with a business-integration system-user token, stored encrypted, with a single-use signed `state`.
    - **Launch:** an owner's launch, or an owner's approval, creates the Meta campaign → ad set → creative → ad (campaign PAUSED until all four exist, then ACTIVE). Any failure deletes them, rolls back, and returns 502.
    - **Pause/resume** sync to Meta first.
    - **Code:** the Meta client and the mapping rules (objectives, offset-1 currencies, targeting) live in `integrations/meta_ads.py`. Tests swap `meta_ads.client_factory` and `verify.client_factory` for `httpx.MockTransport`.
    - **Config:** needs `META_APP_ID` / `META_APP_SECRET` / `META_LOGIN_CONFIG_ID` (503 without them) and `META_GRAPH_VERSION` (v25.0; v26 breaking changes reportedly from 2026-10-27).
    - **Launch rules:** a Meta-channel launch needs a real connection (409) and a `destination_url` (422).
    - **Logging:** the `httpx` logger is set to WARNING because its INFO line would leak query-string tokens.
    - Ad images/video and results import were added by SPEC-BE-055/056 (below).
  - **Orchestrator v2 (2026-10-01): SPEC-BE-055/056/058/059/060 + SPEC-FE-039–042.** Implemented and verified on the live DB (2026-10-01). The additive DDL from SPEC-BE-055 and SPEC-BE-058 is applied. Known gaps are listed in each spec's Status line.
    - **Command Chat (BE-059):**
      - One LLM call drafts actions from `ai/command_actions.py`'s registry (all modules, strict params per action). A missing field produces a fixed-template question, and the draft is kept for the next message.
      - Approval policy:
        - read and draft steps run at once;
        - change steps need a manager+ approval, but not from the requester (the owner's own command auto-approves);
        - spend steps always need an explicit owner approval.
      - Approved steps run in the background through `scheduler_service.run_soon` (inline when the scheduler is off or `INLINE_JOBS`).
      - Per-step status/result/error live in `orchestrator_plans.actions`, and a summary reply is posted at the end.
      - Plan steps are `approval_queue` subject_type `action`, with a payload carrying module and risk.
    - **Workflows (BE-060):**
      - The chat writes the same `WorkflowSave` JSON as the visual builder, plus a check of the trigger's context fields.
      - Enabled workflows now run live: `inventory_low` (from inventory adjust, when stock crosses the threshold), `ad_threshold_crossed` (after a Meta import), `schedule_cron` (a 1-minute job) and manual `POST /workflows/{id}/run`.
      - `notify_owner` and `create_task` write `notifications` rows. Money and price actions inside a workflow only queue approvals.
    - **Shipping (BE-058):** detect/sync from Shopify (GraphQL `deliveryProfiles`, static token or client-credentials 24h token) and WooCommerce (REST). Also:
      - a guided setup, with a `/setup/validate` dry run;
      - validation before activation;
      - two-way edits, store first; what the API can't write is read-only with a 409;
      - a 6-hour re-sync job, with status in `integrations.metadata.shipping_sync`.
    - **Meta builder (BE-055):**
      - Campaign → 1..10 ad sets → 1..10 ads (`services/meta_builder_service.py`, `api/v1/meta.py`).
      - Six objectives (`leads`/`app_promotion` are new enum values; Sales = `conversions`).
      - Media upload, Meta `validate_only` and `generatepreviews`, publish active/paused/scheduled with an all-or-nothing rollback, and per-level pause/resume.
    - **Results (BE-056):** daily Meta insights go into `analytics_events` (`source='meta'`), re-importing the last 3 days. It runs as a 3-hour job, or on demand with a 5-minute throttle. CTR, ROAS and conversions in Analytics, Marketing and the campaign list come from it, and are null when nothing was imported.
    - **Dev-only fakes** (refused when `APP_ENV=production`):
      - `META_FAKE_TRANSPORT=true` (`integrations/dev_fakes.py`) answers Meta, Shopify and WooCommerce calls from fixtures.
      - `LLM_PROVIDER=fixture` + `LLM_FIXTURE_FILE` gives deterministic chat plans.
  - Counts and metrics: `GET /orders/metrics` (SPEC-BE-006: total, 24h, 7d and
    7d delta) and `GET /campaigns/metrics` (SPEC-BE-009: active campaigns and
    ROAS, which is null with no revenue data).
  - Knowledge Base (SPEC-BE-048, 2026-09-30): `GET/POST /policies`, `PATCH/DELETE
    /policies/{id}`, plus FAQ edit, delete and enable/disable. Enabled,
    in-effect policies and enabled FAQs feed the AI reply grounding
    (`ai/retrieval.py`).
  - Workflows (SPEC-BE-049, 2026-09-30): create, edit, enable/disable, version
    history and restore. **Saving an edit inserts a new row** (version + 1,
    `previous_version_id` = the old row). The old row is disabled but kept, so
    its runs still point at the exact version that ran. Lists show only the
    current row of each chain, and a superseded version returns 409 on edit.
  - Analytics reports (SPEC-BE-050, 2026-10-01): `GET /analytics/ads`,
    `/analytics/engagement` and `/analytics/customer-service`, each taking
    `?range=7d|30d|90d`. They bucket by day in `tenants.timezone`, zero-fill
    missing days, and return null (never an estimate) for metrics with no
    source data, such as CTR, ROAS, likes and reach. First response and AI/agent
    reply counts use only **sent** messages (`sent_at`), so pending AI drafts are
    excluded.
  - Organization settings (SPEC-BE-051, 2026-09-30): `PATCH /tenants/me`
    (profile), branding images under `/tenants/me/branding/{logo|banner|head_photo}`
    (PNG, JPEG or WebP up to 1 MB, checked by magic bytes, stored as data URLs in
    `tenants.metadata.branding`), and the owner-only `POST /tenants/me/reset`.
    Reset needs the slug and the owner's password. It deletes all of the
    company's business data, but keeps the company, users, roles,
    integrations, keys, branding and the audit log.
  - Integrations (SPEC-BE-052, 2026-09-30): `GET /integrations/catalog` (drives
    the forms), `PUT /integrations/{provider}` (save and test),
    `POST …/test` and `DELETE` (manager+). Users paste their own tokens; there
    is no OAuth redirect. Credentials are Fernet-encrypted (`ENCRYPTION_KEY`)
    in `integrations.credentials_ref` and never returned, only masked. Test
    calls are real `httpx` requests in `integrations/verify.py`, with a
    server-side request forgery (SSRF) guard.
  - AI Models (SPEC-BE-053, 2026-09-30): `GET/PUT/DELETE /ai-models/{provider}`,
    `PUT /ai-models/order` and `POST /ai-models/{provider}/test` cover
    per-company Claude, GPT and Gemini keys in priority order. They are stored
    encrypted in `tenants.settings.llm_providers` (see the LLM paragraph under
    "Backend architecture").
- Also implemented (pre-spec): config, security (JWT/passwords), tenant
  context/middleware, RBAC, Pydantic schemas, middleware, validators, utils,
  the workflow engine, the LLM client, and auth/tenants/users/orchestrator routes.
  Auth, tenants and users were realigned with the live DB by SPEC-BE-036
  (login/token/RBAC) and SPEC-BE-037 (register, `/tenants/me`, owner-only user
  management).
- **Multi-platform Ad Manager (2026-10-02): SPEC-BE-062…068 + SPEC-FE-043…045.**
  - **Flow:** "+ New campaign" → `/marketing/paid/ad-manager` (8 cards: Meta, TikTok, Google Ads, YouTube, LinkedIn, X, Snapchat, Pinterest) → `/marketing/paid/new?platform=` → `/marketing/paid/<id>/edit` (Campaign → Ad set → Ad → **Review** stepper since SPEC-FE-049; the old `/campaigns/*` URLs redirect). The edit page asks `GET /ads/campaigns/{id}` first; a 404 means a Meta campaign, which opens the unchanged Meta builder.
  - **Backend:** `api/v1/ads_builder.py` + `services/ads_builder_service.py` (registry `PLATFORMS`, tree, validate, publish, approval, pause/resume, results import). Drafts are `campaigns.metadata.platform` + `platform_campaign`; groups and ads use `ad_groups`/`ads` metadata. The Meta builder returns 404 for these campaigns.
  - **Adapters:** `integrations/{tiktok,google,linkedin,x,snapchat,pinterest}_ads.py` (YouTube = `google_ads.py`, Demand Gen video). The contract and shared helpers (`client_factory`, `Rollback`, `AD_RESULT_SOURCES`) live in `integrations/base_adapter.py`. Every publish is all-or-nothing.
  - **Results:** daily campaign-level rows in `analytics_events` (`source` = platform, YouTube = `google`). Analytics, CTR 7d and campaign ROAS read every source in `AD_RESULT_SOURCES`.
  - **Testing:** `dev_fakes` answers all six platforms (`CALLS`, `FAIL`, `FAIL_SKIP` for tests).
  - **Additive DDL applied:** `channel_type` += google, linkedin, x, snapchat, pinterest; `integration_provider` += linkedin_ads, x_ads, snapchat_ads, pinterest_ads.
  - **Not yet run against the real platforms:** each needs the user's approved API access.
- **AI Ad Autopilot (2026-10-02): SPEC-BE-069/070 + SPEC-FE-046.**
  - **Flow:** "Create with AI" (`/marketing/paid/ai/new`) → a run (`ai_campaign_runs`, `services/ai_campaign_service.py`) goes through context → plan → targeting → copy → visuals → safety → drafts in the normal builders, then **always stops for review**.
  - **Publishing:** the user decided never to auto-publish. `POST /ai-campaigns/{id}/publish` is the only way live: it refuses safety errors, needs warnings acknowledged, and applies the spend-cap approval.
  - **Providers:** `ai/creative_providers.py` (LLM chain, OpenAI and Gemini images with the saved AI Model keys, product photos, MCP creative tools through `integrations/mcp_client.py`). Prompts and output contracts are in `ai/prompts/ad_planner.py`.
  - **Tests:** swap `ai_campaign_service.creative_generate` and `landing_check`. `dev_fakes` also answers Gemini images and `example.com` pages.
  - **Command Chat:** the `create_ai_campaign` action (risk `draft`).
- AI Models (SPEC-BE-053 amendment, 2026-10-02): default models are gemini-2.5-flash and openai/gpt-oss-120b; a 404 test says the model may be retired; the card's "Save & test" saves first.
- AI Models providers (SPEC-BE-088, 2026-10-09): six providers.
  - **Default fallback order** (= the `ai/providers.PROVIDERS` order): Claude → OpenAI → Gemini → Groq → OpenRouter → Ollama.
  - **Ollama** is local (`OLLAMA_BASE_URL`), `needs_key=False`.
  - **Company models only:** a company with its own AI Models never falls back to the `.env` `LLM_*` key.
  - **pilotsonic (2026-10-09):** Claude `claude-sonnet-5-5` first, Gemini second. Its Groq key is invalid (401).
  - **Every AI text feature uses this chain** (amendment): `/content/generate` was the last one calling without `db`/`tenant_id`. Image/video generation keeps its own order; embeddings stay one platform key.
- AI replies in the customer's language (SPEC-BE-089, 2026-10-09): `reply_drafter` answers in the language and script of the customer's latest message (`primary_language` only when unclear). The fixed hand-over replies are Bengali when that message is mainly Bengali script (`is_bengali`), English otherwise. Command Chat, ad and organic copy still use `primary_language`.
- Command Chat → Zernio (SPEC-BE-090, 2026-10-09): with a Zernio Facebook ads account connected, a Facebook/Instagram campaign request is `publish_zernio_campaign` (risk spend = owner approval; paused unless the user says run/publish/launch; the ad account must be the only one or named; `ExecContext.request_id` = plan + step is Zernio's Idempotency-Key). The context carries `zernio_ads`; without Zernio the chat still drafts in the direct Meta builder, which is unchanged.
- Chat ad media (SPEC-BE-091 + SPEC-FE-056, 2026-10-09): the planner context has `media_library` (20 items, names matching the message first), so "use the Eid banner" resolves; when the question waits for `media id`, the chat shows "Choose from media library" (kind filter, name search, paging), and a pick answers `Use the image "<name>" (<id>)`.
- Command Chat media chains (SPEC-BE-092 → SPEC-BE-093 + SPEC-FE-057, 2026-10-09):
  - **Images:** Nano Banana (`gemini_image`), then OpenAI images. **Videos:** Google Flow, then an OpenAI
    slideshow. Google Flow has no API, so this is Veo 3.1 (`gemini_video`) through the Gemini key.
  - **Slideshow:** `openai_slideshow` has 2–6 OpenAI images with zoom and crossfades, made into an MP4 by the
    bundled ffmpeg (`imageio-ffmpeg`). OpenAI shut down the Sora API on 2026-09-24, so Sora is not in the
    chain.
  - **Pinned chain:** the chain is pinned in `request.providers` (`generation_service._providers`), and
    any failure moves to the next provider: at start, while polling, or a 429. Regenerate/edit inherit
    it. Without any provider set up, the step fails 409 with a fixed text.
  - **Chat-only:** `cp.CHAT_ONLY` keeps the slideshow out of the creative order and the Organic pages,
    which keep their own order. The summary names who made it and why an earlier one failed;
    `ResultItem.media {id, kind}` drives the inline preview (fresh URL from `GET /media/{id}`).
  - **Models** are the company's own choices in AI Models. Claude has no image/video, so text follows the
    company priority order (pilotsonic: Claude → Gemini → OpenAI).
- Sound for AI slideshow videos (SPEC-BE-094 + SPEC-FE-060, 2026-10-10):
  - **The media library accepts audio** (MP3/M4A/WAV, 20 MB). The DDL is applied: `media_assets.kind` adds
    'audio'.
  - **Audio stays out of posts and ads:** it is listed only with `?kind=audio`, and `media_rows` refuses it
    unless `kinds=("audio",)`.
  - **Settings:** `tenants.settings.creative.video_audio` {voiceover, voice, music_media_id, music_volume},
    via `GET/PUT /ai-models/video-audio`.
  - **The slideshow adds** an AI voiceover (the text chain writes the script in `primary_language`, and
    OpenAI `gpt-4o-mini-tts` reads it) and/or the company's music.
  - **Mixing** is two ffmpeg runs (audio WAV, then a mux). A failure never fails the video;
    `CreativeResult.notes` → the job notes.
- Command Chat voice + generative UI (SPEC-BE-095 + SPEC-FE-061/062, 2026-10-10):
  - **Listen:** `POST /orchestrator/voice/transcribe` (multipart `audio`, at most 1.9 MB, detected by magic bytes) →
    `{text, language, provider}`. It uses the company's own keys: OpenAI (text from `gpt-4o-mini-transcribe`; the language
    from the script, else `whisper-1`, asked at the same time) → Groq `whisper-large-v3` → Gemini. Code is in
    `ai/speech.py`; the audio is never stored. `whisper-1` alone wrote Bengali in Devanagari (Amendment A).
  - **Send:** the transcript is reviewed in the composer, then `POST /orchestrator/messages {body, voice: {language}}`.
    It is planned exactly like typed text, with `parsed_intent.voice` on the user message (`ChatMessage.voice` /
    `voice_language`).
  - **Speak:** `POST /orchestrator/messages/{id}/speech {language}` → JSON base64 audio. Non-English replies are
    translated by the text chain and cached in `parsed_intent.voice_text`. Voices: OpenAI `gpt-4o-mini-tts` → Gemini
    TTS (WAV). The stored reply text never changes.
  - **Errors:** no key → 409, all providers failed → 503. `dev_fakes` answers OpenAI/Groq/Gemini speech
    (`VOICE_TRANSCRIPT`).
  - **Language (Amendment C):**
    - **Choosing it:** the script decides when it's a fifth or more of the letters; Whisper's guess must fit the
      transcript; English-looking Latin text is English. Hints (brand language, the timezone country's national
      languages, the browser's, English) steer the transcriber's prompt.
    - **Reply language:** "reply in X" / "Xতে বলো" / "X में बोलो" → `ChatMessage.reply_language`, which the chat speaks in
      instead of the spoken language.
- Files → job lists → automation (SPEC-BE-096/097/098 + SPEC-FE-064/065, 2026-10-10). Verified with dev fakes, real AI
  (pilotsonic) and a browser E2E. DDL applied: `orchestrator_files`; `plan_status` += draft/submitted/paused/cancelled;
  `orchestrator_plans` += mode, start_at, concurrency, submitted_at, paused_at, progress_at, items, template.
  - **Files** (`services/file_extract_service.py`): `POST /orchestrator/files` (100 MB). PDF (pypdf; scanned pages read by
    the vision model), DOCX, XLSX, CSV/TXT/JSON, images (→ media library) and ZIP (bomb, size, count, nesting and path
    guards). Messages take `file_ids`.
  - **Vision:** `providers.call(..., images=)` and `llm_client.complete_vision` (Claude/OpenAI/Gemini/OpenRouter, company
    models only).
  - **Job lists** (`services/job_board_service.py`): files, or a command of ≥ 5 steps, make a **draft** that runs nothing.
    - **How it's built:** items + one AI-written template (`{{item.x}}`, `$n` per item) → expanded jobs, checked by the
      schema and the guard (evidence includes the files). Invalid jobs are `needs_input`; hand-made jobs skip the guard.
    - **Editing:** jobs, items, the schedule, or by chat (while a draft is open).
    - **Submit:** applies the approval policy.
    - **Running:** in order, parallel (1-5) or scheduled (`run_at`, company time); a 429 re-queues the job a minute later;
      `workers/tasks/plan_tasks.py` checks every minute.
    - **In the chat:** progress, failure and summary messages; chat actions `job_list_status`, `retry_failed_jobs`,
      `pause|resume|cancel_job_list`.
  - **Products** (`product_service.create_ai_listing` / `publish_product`, `integrations/store_products.py`,
    `ai/prompts/product_listing.py`):
    - `create_product_listing` writes a draft product from photos and/or details. The price is the user's only, the SKU
      is `new_sku`, and any number the input doesn't have is removed.
    - `publish_product` (change; takes `product` = `$n.product_id` / id / SKU) → the catalogue active + web channel, and
      Shopify/WooCommerce when connected (all-or-nothing; re-publishing updates).
  - **Creative:** `generate_photo` / `generate_video` take audience, background, mood and text_overlay; video also takes
    music_media_id, voiceover and voiceover_text (this video only).
  - **Dev fakes:** OpenAI/Groq/Gemini speech, Shopify/Woo products (`STORE_CALLS` / `STORE_FAIL`).
- Command Chat history + Projects (SPEC-BE-099 + SPEC-FE-066, 2026-10-10). Verified on the live DB (38 rolled-back checks)
  and by a browser E2E with real AI. DDL applied: `orchestrator_chats`, `orchestrator_projects`,
  `orchestrator_files.project_id`; old messages were backfilled into one "Earlier chat" per user.
  - **Chat id:** `orchestrator_messages.session_id` (a live column, unused before). Code is in `services/chat_service.py`.
  - **Private:** chats and projects belong to their creator; anyone else's id is 404. Pending Approvals stays company-wide.
  - **Sending:** `POST /orchestrator/messages` with `chat_id` continues that chat. Without it, the user's latest chat
    continues (old clients, the eval), and `new_chat: true` or a `project_id` starts a new one. The pending
    clarification and the open draft job list are per chat. Plan summaries and progress lines reach the plan's chat
    through `chat_of_correlation`.
  - **Titles:** the first words at once, then an AI title in the background (`title_source` auto → ai). A renamed or
    backfilled chat is `manual` and is never retitled.
  - **Projects:** instructions (≤ 4,000 chars) and up to 20 files (SPEC-BE-096 uploads) go into the planner context as
    `project`, and the files' values count as evidence (SPEC-BE-085). One system-prompt line says the project is
    background, not a request.
  - **Reset** (`POST /tenants/me/reset`) deletes chats and projects.
- Step outcomes and fixes (SPEC-BE-100 + SPEC-FE-067, 2026-10-10). Verified: 18 rolled-back checks, plus a browser E2E.
  - **Readable errors:** a run-time `ValidationError` is recorded as its message (`ca.validation_text`), never
    "Unexpected error (ValidationError)".
  - **How to fix:** each failed step stores `fix {text, href, link_label}` from `ca.fix_for` (a rule table: social
    account → `/marketing/organic/accounts`, ads/store/AI key → `/integrations`, rate limit, permissions, invalid
    values…). It's in `PlanAction.fix`, the summary's `ResultItem.fix` and the failure chat line.
  - **Chat lines:** a job list of up to 50 jobs (`EACH_JOB_LINES`) posts a line per finished job, with "(n of N)";
    bigger lists keep the 5-minute progress line.
  - **Editing after approval:** a failed read/draft step, or a queued read/draft job of a submitted list, can be edited
    (then Retry). change/spend steps can't, because the approval covered their values.
  - `create_ai_campaign` with `visuals: "products"` needs SKUs at check time (needs_input / a question).
- **Super admin + software-wide keys (2026-10-10): SPEC-BE-101/102 + SPEC-FE-068.** Verified on the live DB with dev fakes
  (rolled back); the FE browser E2E is still pending. DDL applied: `platform_admins`, `platform_settings`.
  - **Super admin:** workspace `pilotsonic-admin`, superadmin@pilotsonic.com. A row in `platform_admins` (no route writes
    it); `dependencies.require_super_admin` → 404 for everyone else. Routes `/platform/*` (`api/v1/platform.py`), screen
    `/admin`; `GET /platform/me` → `{super_admin}`.
  - **Key store:** `services/platform_service.py` over `platform_settings` (`llm_providers`, `socialapi`, `zernio`,
    `meta_app`, `tiktok_app`, `linkedin_app`); secrets Fernet `*_enc`; unset values fall back to `.env`; 30 s cache
    (`clear_cache()` on save). Without `db`, reads use their own connection, so rolled-back checks must patch `_read`.
  - **AI is shared only:** every AI feature uses the software chain; companies' own keys are ignored (kept in the DB).
    Company `/ai-models` key routes answer 409 (`ai_model_service.PROVIDED`). No model anywhere → the chat says
    "PilotSonic's AI isn't set up yet".
  - **SocialAPI:** one master key; each company gets its own brand + brand-restricted key on first use
    (`tenants.settings.socialapi.managed`), so SocialAPI isolates companies. Company key save/delete are 409.
    Since 2026-10-11 the config stores `master_fp` (a short SHA-256 of the master key). A new master key, or a company
    key SocialAPI rejects (brand or key deleted in its dashboard), rebuilds the brand and key once (`_heal`, then a
    retry); brands are found by name first, so there are no duplicates.
  - **Connect only:** pasted tokens for social and ad platforms are 409 (`integration_service.CONNECT_ONLY`); existing
    connections keep working. Store, CRM and email forms are unchanged.
  - **Ads in Command Chat (BE-102):** Zernio first (`publish_zernio_campaign`); `create_ai_campaign` only for
    `direct_ad_platforms`; neither → the `ad_connection` question. Skip a job: `POST
    /orchestrator/plans/{id}/actions/{i}/skip` (`orchestrator_service.skip_action`).
- **Organic posts through SocialAPI (2026-10-11): SPEC-BE-104 + SPEC-FE-071.** Verified with dev fakes on the live DB
  (12 rolled-back checks); the FE browser E2E is pending.
  - **Which account:** when a platform (facebook/instagram/tiktok/linkedin) has no usable direct connection, the
    company's SocialAPI account for it is the platform's account (`connected_via: "socialapi"`). It comes from
    `socialapi_service.organic_accounts`: cached 60 s, never creates a brand, and any error means "none".
  - **Direct first:** a direct connection always wins.
  - **Publishing:** `connection()` returns `via`; `social_base.adapter(platform, via)` → `integrations/socialapi_publisher.py`.
    It uploads the media bytes, then `POST /posts` with `publish_now`.
  - **Storage:** `external_post_id` = the SocialAPI post id; `scheduled_posts.metadata.via` drives the results import.
  - **Not ready yet:** a Facebook login with no Page chosen; Instagram stories via SocialAPI are refused.
- **Per-company key access (2026-10-11): SPEC-BE-103 + SPEC-FE-069.** Verified on the live DB (28 rolled-back checks);
  the FE browser E2E is pending. No DDL.
  - **Store:** `platform_settings` row `company_access` = `{tenant_id: {group: false}}`. A missing entry means allowed,
    so everything is on by default. Groups: ai, socialapi, zernio, meta_app, tiktok_app, linkedin_app.
  - **Routes:** `GET /platform/companies`, `PUT /platform/companies/{id}/access` (audited). Screen: the Companies section
    on `/admin`.
  - **Enforcement:** `platform_service.allowed/require` (403 + `BLOCKED[group]`) at the company entry points:
    - **ai:** `resolve_chain`/`provider_key`, plus `llm_client`, which has no `.env`/mock fallback when blocked;
    - **socialapi:** `socialapi_service._key`;
    - **zernio:** `zernio_service.profile_id`;
    - **sign-in apps:** the connect/callback functions, and `_needs_refresh`, so existing tokens just run out.
  - **No company = allowed:** jobs and embeddings.
- Worldwide company settings (SPEC-BE-072 + SPEC-FE-048, 2026-10-02):
  - `utils/locale_data.py` (Babel/CLDR + pytz) serves every country, currency, language and timezone through `GET /tenants/locale-options`. `PATCH /tenants/me` validates against it.
  - Sign-up takes the browser's timezone/country as hints: old zone names are mapped, unusable values dropped, and the currency follows the country.
  - Money storage stays `amount × 100` in `*_cents` for every currency (JPY ¥1,500 = 150000).
  - Use `locale_data.format_money()` for money in text, never `/ 100:,.2f`.
- Shipping (SPEC-BE-061, 2026-10-02): zones may share a country when their regions differ. The guided setup saves regions and blocks only on the new zones' own issues.
- **Marketing restructure (2026-10-03): SPEC-FE-049/050 + SPEC-BE-074…078.** The code is written, and lint/type/build checks plus 96 no-DB checks pass. **Live-DB verification and the additive DDL are still pending** (Postgres was unreachable). See each spec's Status line and Implementation notes.
  - **Navigation:** "Campaigns" left the sidebar. Marketing has Paid Marketing (`/marketing/paid`, the former `/campaigns`) and Organic Marketing (`/marketing/organic`).
  - **DDL to apply** (in order; the SQL is in the specs):
    - `media_assets` (SPEC-BE-074);
    - `generation_jobs` (SPEC-BE-077);
    - `organic_contents` (SPEC-BE-076);
    - `ALTER TYPE integration_provider ADD VALUE 'linkedin'` (SPEC-BE-075);
    - and check that the `scheduled_posts` columns now mapped exist.
  - **Media library (BE-074):** `services/media_service.py`, `integrations/storage.py` (local disk by default, or S3 SigV4 over httpx). Signed URLs are `/api/v1/media/f/{token}` (no auth, HMAC with `SECRET_KEY`). Instagram needs `PUBLIC_BASE_URL` to be public https, or S3. Pillow crops images to platform ratios; videos are never transcoded.
  - **Social publishing (BE-075):** `integrations/{facebook,instagram,tiktok,linkedin}.py`, each a module with `check / publish / poll / metrics`, sharing `integrations/social_base.py` (`SocialError.transient/auth`). Accounts are the pasted-token integrations (`GET /social/accounts`). TikTok API posts stay private until TikTok audits the app.
  - **Organic content (BE-076):** a master `organic_contents` row, platform versions as `content_assets` (`format='organic_post'`), and schedules in `scheduled_posts`.
    - Rules and AI prompts: `ai/prompts/organic_adapter.py`. AI content must be approved before scheduling.
    - The `publish_tasks` job runs **every minute** (`organic_service.run_due`, SKIP LOCKED, 3 retries, never double-posts).
  - **Generation (BE-077):** `services/generation_service.py`. Video providers are Veo and Sora (creative kind `video`, a per-company `video_model` in AI Models) plus MCP. A requested duration maps to the nearest supported one (Veo 4/6/8 s, Sora 4/8/12 s), and the job says so. `generation_tasks` resumes jobs every minute.
  - **Command Chat (BE-078):** organic actions (`create_organic_posts`, `create_organic_post`, `generate_photo/video`, `regenerate_organic_copy`, `schedule_organic_posts`…). The planner gets `today_local` and the company's recent organic items. `schedule_post` is now an alias of `schedule_organic_posts`.
  - **Organic analytics:** `GET /analytics/organic`, rows `source='organic_<platform>'` (never in `AD_RESULT_SOURCES`), imported every 6 h.
  - **dev_fakes** also answer Graph organic, TikTok Content Posting, LinkedIn organizations, Veo, Sora and OpenAI images.
- **Marketing gaps closed (2026-10-03): SPEC-BE-079/080/081 + SPEC-FE-051/052.** Code written; lint/type/build and no-DB checks pass. **Live-DB verification is pending** (Postgres isn't installed or running on this machine). No DDL is needed.
  - **Paid lists (BE-079):** `GET /paid/ad-sets`, `GET /paid/ads` (every builder; filters, paging, `range`), and `POST /paid/{ad-sets|ads}/{id}/pause|resume`, which dispatch to the Meta or multi-platform builder. Results: Meta per ad; other platforms report per campaign, so `results_level="campaign"` and null results.
  - **Social sign-in (BE-080):** `GET /social/oauth/{meta|tiktok|linkedin}/connect` → frontend `/marketing/organic/accounts/callback/{flow}` → `POST …/callback` → `POST …/select` (meta/linkedin). Code is in `services/social_oauth_service.py`, plus `login_url/exchange_code/refresh` in `integrations/{facebook,tiktok,linkedin}.py`.
    - **Storage:** tokens go through `integration_service.save_oauth_credentials` (the same fields + `secrets_enc` shape, plus `settings.oauth`; `integrations.expires_at` = the refresh token's expiry).
    - **Refresh:** `social_account_service.connection()` refreshes first (own session, row lock), and the `social_token_refresh` job runs every 30 minutes.
    - **Config:** `TIKTOK_CLIENT_KEY/SECRET`, `LINKEDIN_CLIENT_ID/SECRET`, optional `META_SOCIAL_LOGIN_CONFIG_ID` (503 without them).
    - **Status:** `/social/accounts` items carry `connected_via`, `account_id`, `scopes`, `token_status`, expiries, `last_checked_at`, `last_synced_at`.
  - **Insights (BE-081):** `GET /organic/insights?days=30|60|90`, computed from imported results (≥ 3 posts per platform, ≥ 2 per hour/format). `performance_context()` adds a `<performance>` block to the AI copy, adapt and regenerate prompts (`organic_contents.metadata.performance_used`). Command Chat `organic_insights` (read). Nothing changes automatically.
- **SocialAPI.ai (2026-10-07): SPEC-BE-083 + SPEC-FE-054.** Verified on the live DB (66 rolled-back checks).
  - **What it is:** a third-party API (https://social-api.ai) for organic posting, analytics and the inbox on 13 platforms. It has **no paid ads**. It is another option *next to* the direct integrations, which are unchanged.
  - **Self-contained:**
    - `integrations/socialapi.py` (client), `services/socialapi_service.py`, routes `/socialapi/*`.
    - Posts live in SocialAPI, not in `organic_contents` / `scheduled_posts`.
    - The inbox (DMs, comments, Google reviews) is read live, not copied into `conversations`.
  - **Key:** `tenants.settings.socialapi` (Fernet `key_enc`, `brand_id`, `last_ok_at` / `last_error`). No DDL.
  - **Connect:** SocialAPI's managed OAuth returns to `/marketing/organic/socialapi/callback` with a signed state. A Facebook Page or Google location needs a choice (`select`).
  - **Media:** comes from our media library, uploaded to SocialAPI on send.
  - **AI draft:** reuses `reply_drafter`.
  - **Dev fakes:** `dev_fakes` answers `api.social-api.ai` (key `sapi_key_bad` = 401).
- **Zernio paid ads (2026-10-08): SPEC-BE-084 + SPEC-FE-055.** Verified with dev fakes on the live DB (25 rolled-back checks). Not yet run against the real zernio.com.
  - **What it is:** one paid-ads API (https://zernio.com) for Facebook, Instagram, TikTok, LinkedIn, Pinterest, X and Google Ads. It sits next to the existing builders, which are unchanged.
  - **One server key for every company:** `ZERNIO_API_KEY` in `backend/.env`; while it is empty, `/zernio/*` answers 503.
    - Each company gets its own Zernio profile (`tenants.settings.zernio.profile_id`, created on first use).
    - Every id is checked against that profile; a foreign or unknown id is 404.
  - **Code:** `integrations/zernio.py` (client, error mapping, the `PLATFORMS` rules the UI reads), `services/zernio_service.py`, routes `/zernio/*`. No DDL.
  - **Storage:** campaigns are read live (`GET /ads/tree`), never copied into `campaigns`.
  - **Rules:**
    - Any manager+ may publish live and resume (the user's choice; no owner step, no spend-cap approval).
    - Money goes to Zernio in whole currency units, not cents.
  - **Connect:**
    - Zernio's hosted sign-in, in a new tab, back to `/marketing/paid/zernio/callback?zs=<single-use nonce>`. It is a nonce, not a JWT, because of X's redirect length limit.
    - X connects its posting account first, then its ads account.
  - **Media:** public URLs from the media library (needs `PUBLIC_BASE_URL` https or S3). Meta images can fall back to a base64 upload.
  - **Dev fakes:** `dev_fakes` answers `zernio.com`; the key `zernio_bad` gives 401.
- **AI does exactly what was asked (2026-10-09): SPEC-BE-085.** Verified on the live DB (31/31 golden cases in stub mode, plus 18 rolled-back checks). Not yet measured against a real AI model.
  - **Command Chat guard (`ai/command_guard.py`):** it runs on the model's raw actions before `validate_actions`.
    - **Evidence** is only what the user typed: the message, plus the open clarification chain when the model says `new_request: false`. It is stored as `parsed_intent.evidence`.
    - **Provenance:** numbers, countries, URLs, dates, times, genders and timezones must appear in the evidence. Ids must appear in the planner context, and SKUs must exist (rewritten to the stored case).
      - A removed required value becomes the fixed-template question.
      - A removed optional value falls back to its default, and the reply lists it.
    - **Scope:** a non-read step whose request words aren't in the evidence is dropped as `not_requested`. Its dependents are dropped as `depends_on_dropped`.
    - Free text (names, briefs, captions), `objective` and `rule_type` are not checked.
  - **Planner:**
    - `temperature=0`; a 400 that names temperature is retried without it (`providers.call` / `llm_client`). Other callers send no temperature.
    - One retry when the answer is unparseable or structurally broken (`ca.structural_problems`).
    - `today` is company-local.
    - Products, campaigns and workflows the user names come first in the context.
    - `parsed_intent` keeps `dropped` / `left_out`; the API reply shape is unchanged.
  - **Create with AI:**
    - `ad_planner.check_plan` enforces an explicitly stated age range, gender target and countries.
    - The safety stage flags copy amounts that aren't a product price, compare-at price, saving or brief number (error), and free shipping the brief doesn't mention (warning).
  - **Eval:** `backend/evals/run_command_eval.py` + `command_chat_cases.json` (see Commands).
- **RAGAS for AI replies (2026-10-09): SPEC-BE-086.**
  - **What it measures:** `backend/evals/run_reply_eval.py` + `reply_cases.json` measure `retrieve_grounding` (hit rate, free) and, with `--ragas`, the real `generate_reply_draft` output: faithfulness, context recall, context precision with reference, and factual correctness.
  - **Judge:** the company's first OpenAI-compatible model.
  - **Environment:** RAGAS lives only in `backend/.venv-eval` (`evals/requirements-eval.txt`, git-ignored). Installing it into `.venv` would change `pydantic-settings`, `rich` and `websockets`.
  - **Privacy and certificates:** telemetry is off (`RAGAS_DO_NOT_TRACK`), and `truststore` uses the OS certificate store.
  - **First result:** retrieval found the right source for 8/13 answerable questions. Paraphrases and Bengali miss because the search is keyword-only. The RAGAS scores are not measured yet: the Gemini key ran out of quota (429).
- **Embedding search for AI replies (2026-10-09): SPEC-BE-087.** Built and verified with dev fakes on the live DB (18 rolled-back checks). The DDL is applied. **Off until a key is set.**
  - **Storage:** `knowledge_embeddings` (`real[]` unit vectors, 768 dims, tenant-scoped). There is no pgvector and no ChromaDB: cosine is computed in Python over the tenant's rows.
  - **Code:**
    - `ai/embeddings.py`: OpenAI `/v1/embeddings` or Gemini `batchEmbedContents`, with a swappable `client_factory`.
    - `services/knowledge_index_service.py`: units = enabled FAQs, in-effect policies and KB chunks. `refresh` embeds new or changed units (SHA-256, at most 50 per call) and deletes rows whose source is gone, inside a savepoint. The FAQ, policy and KB write paths are untouched.
  - **Retrieval:** `retrieve_grounding` = full-text (`_fulltext`, unchanged), plus semantic hits, merged by reciprocal rank fusion. With embeddings off, or on any `EmbeddingError` / DB error, the result is exactly the full-text one.
    - A semantic hit needs cosine ≥ `EMBEDDINGS_MIN_SIMILARITY`, default 0.70. That was measured for gemini-embedding-001 and is model-specific: re-measure with `run_reply_eval.py --similarities`.
    - Live result with Gemini: 11/13 vs 8/13 keyword-only, with the unanswerable questions unchanged.
  - **Settings:** `EMBEDDINGS_PROVIDER`, `EMBEDDINGS_API_KEY` (one platform key), `EMBEDDINGS_MODEL`, `EMBEDDINGS_DIMENSIONS` and `EMBEDDINGS_BASE_URL`.
    - **Providers:** `auto` (default) | none | openai | gemini | voyage | mistral | cohere | openai_compatible.
    - **`auto`:** recognises `AIza` / `pa-` / `sk-` keys, and tries `LLM_API_KEY` when the key is empty.
    - **No embeddings API:** Claude (`sk-ant-`) and Groq (`gsk_`) keys leave it off, with a logged reason. Mistral and Cohere need the explicit provider.
  - **Dev fakes:** `dev_fakes` answers every embedding API with word-hash vectors (not semantic).
  - **Eval:** `run_reply_eval.py --compare [--fake-embeddings]` shows keyword-only vs hybrid. A real key is needed to measure the paraphrase and Bengali gains.
- **Orders, SMS, P&L, business type, unified inbox, branding (2026-10-22): SPEC-BE-107…114 + SPEC-FE-073…078.**
  Verified on the local DB (222 rolled-back checks, eval 38/38) and by a browser E2E with dev fakes. Additive DDL
  in `backend/deploy/sql/2026-10-21_orders_sms_expenses.sql` (cPanel `setup.sh` applies every `deploy/sql/*.sql`).
  - **Orders (BE-107):** `POST /orders` (server totals, cost snapshot per line, Idempotency-Key, number from 1001),
    `order_service.TRANSITIONS` (+ `awaiting_confirmation`, `returned`), `order_status_events` history, manager+ for
    cancel-after-confirm / return / refund. Customer stats are recomputed from orders.
  - **SMS (BE-108):** one Twilio account (`platform_settings` group `twilio`), one number per company
    (`tenants.settings.sms.number`, set by the Super admin). Signed webhooks `/webhooks/twilio/{inbound,status}`,
    deduped in `webhook_events`; a reply changes an order only when it is unambiguous. `utils/phone.py` (E.164).
  - **Customer record (BE-109), P&L + expenses (BE-110, rules in `analytics_service.PL_RULES`), business type
    (BE-111, `utils/business_types.py`; products by hand, categories, payments).**
  - **Inbox (BE-112):** `/inbox/*` merges local conversations (WhatsApp Cloud, SMS, stored) with SocialAPI DMs (live).
    WhatsApp = Embedded Signup + signed `/webhooks/whatsapp`; needs the Super admin's `whatsapp_app` group.
  - **Branding/health (BE-113):** public `GET /platform/branding`, `/users/me`, `/platform/integrations/{health,errors}`.
  - **Chat (BE-114):** `orders_awaiting_confirmation`, `update_order_status`, `send_order_confirmation`,
    `profit_and_loss`, `inspect_conversations`.
- Structurally stubbed (routes exist, bodies minimal or "not_implemented"):
  `kb/documents` (list/ingest only, no embedding; the model matches the live
  table since SPEC-BE-071), webhooks other than Twilio/WhatsApp (404), the CRM/messaging
  adapters in `app/integrations/` (`hubspot.py`, `email.py`:
  nothing is sent or synced through them; `verify.py`'s connection tests are
  real), and 4 of the scheduler's job function bodies in `app/workers/tasks/`.

## Commands

### Backend (`backend/`)

```bash
# The working venv is backend/.venv (Python 3.12). The repo-root .venv is broken
# (no pyvenv.cfg) and the global Python has an incompatible pydantic-settings.
cd backend
.venv\Scripts\activate                                # Windows
pip install -r requirements.txt                       # includes ruff, mypy; no requirements-dev.txt
# no .env.example — edit backend/.env directly

uvicorn app.main:app --reload --port 8000             # API at :8000, docs at /docs; also starts APScheduler

ruff check app                                         # lint (line-length 100, E/F/I rules)
ruff format app
mypy app

alembic revision --autogenerate -m "message"           # alembic isn't initialized — no migrations dir exists
alembic upgrade head

# Command Chat golden set (SPEC-BE-085), on the live DB in one rolled-back transaction
python evals/run_command_eval.py                       # stub model = recorded answers; tests the guards, no AI cost
python evals/run_command_eval.py --live --ai-from <company slug>   # that company's saved AI models; spends its AI credits

# AI customer-service replies with RAGAS (SPEC-BE-086): ONLY in the separate eval venv, never .venv
python -m venv .venv-eval && .venv-eval\Scripts\pip install -r evals\requirements-eval.txt
.venv-eval\Scripts\python evals\run_reply_eval.py                # retrieval hit rate only, no AI call
.venv-eval\Scripts\python evals\run_reply_eval.py --compare      # keyword-only vs hybrid (SPEC-BE-087; uses EMBEDDINGS_* from .env)
#   add --embeddings-from <slug> to use that company's saved OpenAI/Gemini key in memory; --similarities to tune the threshold
.venv-eval\Scripts\python evals\run_reply_eval.py --ragas --ai-from <company slug> [--delay 10] [--out r.json]
```

Current lint/type baseline (pre-existing, not caused by the spec work):
`ruff check app` → 1 unused-import error (`db/tenant_filter.py`); `mypy app`
→ 7 errors in 5 files (missing stubs for jose/passlib/apscheduler ×2/anthropic/
openai, `error_handler` signature), as of 2026-10-01 (the old
`Workflow.conditions` error is gone; the engine was rewritten).
`ruff format --check` also flags most pre-existing files (the formatter isn't
applied repo-wide), so don't reformat untouched code. New code should add none.

**Job scheduler (SPEC-BE-004):** in-process APScheduler, no Celery/Redis.
`app/workers/celery_app.py` keeps its old name but only exposes
`get_scheduler()` (an `AsyncIOScheduler`); `app/workers/schedules.py` lists one
job per file in `app/workers/tasks/` (11 jobs; `ad_tasks` = Meta + other ad platforms' results every 3h,
`sync_tasks` = shipping re-sync every 6h, `workflow_tasks` = cron workflows every
minute are real since 2026-10-01; since 2026-10-03 `publish_tasks` = organic
posts every minute, `generation_tasks` = resume generations every minute and
`organic_metrics` (in `analytics_tasks.py`) = post results every 6h; since SPEC-BE-080
`social_token_refresh` (in `sync_tasks.py`) = social sign-in tokens every 30 min; the other
4 are still inert stubs);
`services/scheduler_service.start_scheduler()` / `shutdown_scheduler()` are
called from `main.py`'s startup/shutdown. `SCHEDULER_ENABLED` /
`SCHEDULER_TIMEZONE` in `config.py` control it.

### Frontend (`frontend/`)

See `frontend/CLAUDE.md` for the authoritative version. In short:

```bash
cd frontend
npm install        # .env.local must exist (copy .env.local.example)
npm run dev        # http://localhost:3000; backend CORS_ORIGINS allows :3000 and :5173
npm run build
npx tsc --noEmit   # strict type check (ESLint is not configured)
```

## Live database vs ORM models

The app connects to Postgres via `DATABASE_URL_SYNC` in `backend/.env`
(`marketing` on `localhost:5432`, psycopg2, sync `Session`). `SELECT version()`
reports PostgreSQL 16.15 (checked 2026-10-09). `pgvector` is not installed (and
can't be built here), so SPEC-BE-087 stores embeddings as `real[]`. **Always use this
Postgres database — never SQLite**, including for verification. The schema was
created outside Alembic; it uses native `uuid` PKs, Postgres enums, arrays,
and `jsonb`, and has 55 tables in `public`.

Many ORM models were written against an imagined schema. Before using a model,
compare it with `information_schema.columns` for its table. Known state:

- **Aligned with the live table:** `Inventory`, `InventoryMovement`,
  `Product`, `ScheduledPost`, `AuditLog` (maps `audit_log`; jsonb `metadata`
  values must be JSON-serializable, so stringify UUIDs), `PricingRule`,
  `ShippingZone`/`ShippingPolicy` (a zone has many policies = rates),
  `Campaign` (enums, `metadata` as `extra_metadata`, launch/approval
  timestamps), `AdGroup`, `Ad`, `Audience`, `OrganicContent` (`media_ids`/`product_ids` are
  `uuid[]`, mapped `ARRAY(UUID(as_uuid=False))` since 2026-10-09). `ApprovalQueue` still maps only
  some columns (not `requested_by_type`, `summary`, `payload`): insert approval
  rows through a Core table (see `campaign_service`). A DB trigger resets
  `campaigns.updated_at` to now() on every UPDATE.
  `Order` maps only the columns its specs need (order_number, channel, status,
  totals, payment, tracking, placed_at).
- **Auth (fixed, SPEC-BE-036/037):** `User`/`Tenant`/`Role`/`UserRole` match
  the live tables. A user's role is `user_roles` → `roles.type` (live
  `role_type`), mapped to the app RBAC level in `auth_service`; only
  `status = 'active'` users in `active`/`trial` tenants can log in.
  `POST /auth/register` creates a new tenant + active owner (`subdomain` =
  slug). `Permission`/`RolePermission` are still misaligned and unused.
- **Other known mismatches:** `ProductVariant` (no `tenant_id`/`attributes`
  mapped; `name`/`price` don't exist live — `inventory_service` reads
  `product_variants` via a Core table instead), `InventoryLocation`
  (`address` is jsonb live; only `name` is safe to read),
  `AnalyticsEvent` (live:
  `event_time`, `metric`, `value`). There is no model for
  `analytics_daily_rollups`.
- **Enum values to use (don't invent others):** `campaign_status` = draft,
  scheduled, running, paused, completed, failed (no `active`);
  `post_status` = pending, scheduled, publishing, published, failed,
  cancelled; `product_status` = draft, active, archived, out_of_stock;
  `channel_type` = facebook, instagram, tiktok, whatsapp, messenger, email,
  sms, web (no Shopify).
- **Timezone:** the Postgres server runs in `Asia/Dhaka`, so `TIMESTAMPTZ`
  values come back as `+06:00`. Normalize to UTC in responses
  (`.astimezone(timezone.utc)`).
- **RLS is effectively off:** some tables (users, products, orders, customers,
  conversations, campaigns, workflows, content_assets, integrations) have
  `tenant_isolation_*` policies, but the app connects as the `postgres`
  superuser, which bypasses them. Tenant isolation is only the explicit
  `tenant_id` filter in each service.
- **Model registration:** `app/models/__init__.py` is empty and the running app
  never imports `db/init_db.py`, so a model is only registered on
  `Base.metadata` if something imports its module. A `ForeignKey("x.id")` to
  an unimported model raises `NoReferencedTableError` on flush — import the
  target model module explicitly (see `models/scheduled_post.py` importing
  `models.content`).
- `models/base.py`'s docstring still mentions SQLite portability; that is stale.
  New columns may use Postgres-only types (e.g. `ARRAY` of an enum with
  `create_type=False`).

## Spec-driven workflow

Work arrives as specs in `specs/SPEC-BE-NNN.md` (FR/NFR, edge cases,
acceptance criteria, target files). Specs 001–003 cover the dependency
manifest, env template, and `config.py`; 004 the scheduler; 005–011 the
domain slices above. The expected flow:

1. Save a new spec **verbatim** when asked; do nothing else.
2. Read the target files and the live schema, then propose a plan (per-file
   changes, open decisions with a recommendation) and wait for approval.
3. Implement only in the spec's target files. Specs frequently assume "stub
   files" that are actually full CRUD, or list target files that don't exist
   (SPEC-BE-010's `scheduled_post_service.py` — the scheduled-post service
   lives in `services/scheduler_service.py`; SPEC-BE-011's `models/ad.py` and
   `schemas/ad.py` — `Ad` lives in `models/campaign.py`). Flag these; never
   create new files unless explicitly approved.
4. Verify on the live Postgres DB inside one transaction that is rolled back
   (seed → call → assert → rollback → confirm nothing persisted), via
   `TestClient` with `get_db` overridden to that session (a fresh
   `Session(bind=conn, join_transaction_mode="create_savepoint")` per request,
   so one failing call doesn't abort the rest). Get real tokens from
   `POST /auth/register` + `/auth/login` inside the transaction — no
   `get_current_user` stub. Run checks inline (heredoc), not from saved
   scripts; create no files.
5. Report each acceptance criterion as pass/fail with evidence, plus a file
   timestamp scan and every deviation.

## Backend architecture

**Layering is strict and one-directional:** `api/v1/*.py` (routes, thin) →
`services/*.py` (business logic, plain functions taking `db: Session` +
`tenant_id` as explicit args, not classes) → `models/*.py` (SQLAlchemy). Routes
never touch the DB directly; services never import FastAPI. `schemas/*.py`
mirrors this by domain for Pydantic request/response variants. All 26 domain
routers are aggregated in `app/api/router.py` and mounted under the
`API_V1_PREFIX` constant (`/api/v1`) in `app/main.py` — that prefix is a
hardcoded module-level constant in `main.py`, *not* a `Settings` field.
Adding a new domain means creating the model, schema, service, and router,
then registering the router in `app/api/router.py`.

**Multi-tenancy is enforced by convention, not a global ORM filter.** There is
no automatic query-level tenant scoping (`db/tenant_filter.py`'s SQLAlchemy
event only guards that tenant-scoped rows aren't inserted without a
`tenant_id`). Every service function takes `tenant_id` explicitly and must
filter by it manually (see `services/inventory_service.py` and
`services/product_service.py`). Return 404 — not 403 — for another tenant's
row, so existence isn't leaked. `tenant_context.py` provides a `ContextVar`
(set in `dependencies.get_current_user`) for cross-cutting code (logging,
audit). `validators/tenant_scope.py`'s `assert_same_tenant` guards explicit
checks.

**Auth flow:** JWT access + refresh tokens (`core/security.py`). Every
protected route depends on `dependencies.get_current_user` (decodes the bearer
token, loads the `User`, sets the tenant `ContextVar`) — the tenant is derived
from the authenticated user. `TenantMiddleware` resolves a tenant from the
`X-Tenant-ID` header or subdomain for *unauthenticated* contexts. RBAC is a
flat hierarchy (`owner > admin > manager > agent > viewer`,
`core/permissions.py`); gate routes with
`dependencies.require_permission("manager")` or
`core/permissions.require_role`.

**Primary keys** are mapped as `String(36)` in the models; the live columns
are native `uuid`, and psycopg2 casts between them transparently.

**AI/LLM calls go through `app/ai/llm_client.py`'s singleton `llm_client`**,
never directly through `anthropic`/`openai` SDKs. Provider SDKs are imported
lazily inside each method so a missing package doesn't break `app.main`
import. Order of resolution (SPEC-BE-053):
1. If the caller passes `db=` and `tenant_id=` (needed: the tenant
   `ContextVar` isn't visible inside FastAPI endpoints), the company's own AI
   models are tried in priority order. Any error, timeout, 429 or bad key moves
   on to the next one (`ai/providers.py`, plain `httpx`).
2. Otherwise, the `.env` provider (`LLM_PROVIDER`/`LLM_API_KEY`).
3. With no real key (`LLM_PROVIDER=mock`, or empty/`changeme` keys), you get a
   mock answer.

What happens on failure depends on the method:
- `complete()` falls back silently: tenant chain → `.env` provider → mock.
- `complete_with_usage()` **raises `LLMProviderError`** when a real provider
  fails, so callers never mistake a mock for a real answer. Creative
  generation and AI reply drafts turn this into a 503. The orchestrator chat
  catches it and shows an "unavailable" message instead.

Keep both behaviors. The app must always boot without real API keys.

**Workflow engine** (`app/workflow_engine/`): `engine.run_workflow()` runs
trigger payload → `conditions.evaluate_all()` → `actions.execute_action()` per
action, recording an `ActionExecution` row per step and a `WorkflowRun`
status. Add new action types in `actions.py`'s registry, not by branching
inside `engine.py`.

## Frontend architecture

Documented in `frontend/CLAUDE.md`, which is authoritative. In short:
- **Routing and data:** App Router pages live in `app/(app)/<page>/page.tsx`.
  API functions live in `lib/api/<domain>.ts` and all go through `apiFetch`,
  which handles bearer tokens from localStorage and one silent refresh on a
  401. Types in `lib/types/<domain>.ts` mirror the backend schemas field for
  field. Server state is TanStack Query.
- **Charts and styling:** charts are hand-rolled from the mockup's
  `.chart`/`.bar` markup (no chart library). Colors come only from the CSS
  variable tokens.
- **Verification:** every frontend spec is verified end to end against the
  running backend and the live DB.

## Coding conventions (apply to all new/changed backend code)

- Type hints on every function signature; no bare `print()` — use
  `structlog` (`structlog.get_logger(__name__)`) in new code. Older modules
  (e.g. the scheduler functions in `scheduler_service.py`) still use stdlib
  `logging`.
- Every route declares `response_model` and an explicit `status_code`.
- Every service function takes `tenant_id` as an explicit parameter, never
  reads it from a global/thread-local.
- Passwords are never logged or included in any response schema.
- Timezone-aware UTC `datetime` everywhere — no naive datetimes; normalize
  values read from Postgres to UTC before returning them.
- Money: the live DB stores integer cents (`*_cents`); the API returns
  `price: float` in major units plus `currency`, converted via `Decimal`.
- Validate all external input via Pydantic schemas at the route boundary, not
  ad hoc checks inside services.
- Document non-obvious mapping rules (which enum values count, which column a
  metric comes from, placeholders) as code comments — specs require it.

### Security rules — current status, don't assume more than this

- ✅ Passwords hashed with bcrypt (`core/security.py`, via passlib).
- ✅ JWT access + refresh tokens, tenant-scoped payload (`core/security.py`).
- ✅ RBAC role check via `dependencies.require_permission` /
  `core/permissions.require_role`.
- ✅ Manual `tenant_id` filtering per service call — no ORM-level
  auto-filter, and Postgres RLS is bypassed by the superuser connection.
- ⚠️ `core/audit.write_audit_log()` writes the live `audit_log` table and
  commits the session itself. It is wired into several services (inventory,
  pricing, shipping, users, brand, FAQs, conversations, approvals, …) but not
  every mutation. Wire it into other mutations as you touch them, using the
  `(actor_user_id, action, resource_type, resource_id, metadata)` shape.
- ✅ Login protection (SPEC-BE-039): per-account lockout after
  `LOGIN_MAX_FAILED_ATTEMPTS` (5) wrong passwords, lasting 1, 2, 4, 8 minutes,
  capped at `LOGIN_LOCKOUT_MAX_MINUTES` (15), using `users.failed_login_attempts` /
  `locked_until`. It's reset on a successful login, and while locked the password isn't
  checked (429 with the wait). Plus a per-IP safety net in `RateLimitMiddleware` that
  counts only FAILED logins (`RATE_LIMIT_LOGIN_ATTEMPTS` 20 per
  `RATE_LIMIT_LOGIN_WINDOW_MINUTES` 5). Successful logins never count. The
  limiter is in-memory per process; all other routes are unlimited.
- ✅ Password reset (SPEC-BE-040): `POST /auth/password-reset/request` (always
  the same 202, no account enumeration; 60s resend throttle) and `/confirm`.
  Tokens are SHA-256-hashed in `password_reset_tokens`, expire after 30 minutes, are
  single-use, and a confirm also clears a lockout. With SMTP unconfigured (placeholder
  `changeme` creds), `utils/email_sender.py` prints the email, link included, to
  the backend console at WARNING (dev mode). Links use `FRONTEND_BASE_URL`.
- ✅ Refresh tokens (SPEC-BE-071 F7, 2026-10-02) are rotated and revocable: each
  one is recorded in `refresh_tokens` (SHA-256 of its jti, never the raw token).
  A refresh needs a recorded, unrevoked, unexpired token and revokes it
  (`replaced_by`). A reused revoked token revokes all of that user's tokens.
  `POST /auth/logout {refresh_token}` revokes it (always 204), and a password reset
  revokes all of them. Tokens issued before 2026-10-02 have no row: those users sign
  in once more. Access tokens stay stateless (15 minutes). Reuse of a token rotated less
  than `REUSE_GRACE` (30 s) ago is a tab race, not a theft: 401, nothing revoked (SPEC-FE-070,
  2026-10-11; the frontend also serialises refreshes across tabs with a Web Lock).
- ✅ Third-party credentials and per-company LLM keys (SPEC-BE-052/053) are
  Fernet-encrypted with `ENCRYPTION_KEY` (`utils/crypto`), never returned (only
  masked), and never logged. Integration test calls go through an SSRF guard.
  Changing `ENCRYPTION_KEY` makes every stored credential unreadable.
- ✅ `BCRYPT_ROUNDS` sets the bcrypt cost (SPEC-BE-071 F14). Passwords (sign-up, user
  creation, reset) need 10+ characters with upper, lower and digit, not a common
  password or common word + digits, and not the email name (`validators/password_policy.py`).
- ✅ Production hardening (SPEC-BE-071, 2026-10-02):
  - `APP_DEBUG` defaults to false. With `APP_ENV=production`, startup refuses debug, a weak
    `SECRET_KEY`, non-https or localhost `CORS_ORIGINS`, `LLM_PROVIDER` mock/fixture, and a
    superuser/BYPASSRLS database login.
  - `/docs`, `/redoc` and `/openapi.json` are off in production. `/health` checks the database
    (503 when unreachable).
  - `middleware/body_limit.py`: 2 MB per request body (413), with 1 GB on ad media uploads.
  - `POST /webhooks/{provider}` answers 404 except Twilio (SPEC-BE-108) and WhatsApp
    (SPEC-BE-112), which verify their signatures.
  - The operator checklist (least-privilege DB role, prod `.env`, one scheduler process,
    backups) is at the end of `specs/SPEC-BE-071.md`.

Don't state or assume these gaps are closed elsewhere in the codebase — check
the file directly before relying on this behavior existing.

## Cross-cutting notes

- No `backend/migrations/` directory exists (alembic isn't initialized). The
  live schema was created elsewhere; if Alembic is introduced, autogenerate
  against it will propose destructive changes wherever models are misaligned —
  fix the models first.
- No backend `.env.example` exists, only a real `backend/.env`. The frontend
  has `frontend/.env.local.example`.
- `backend/scripts/` and `backend/tests/` don't exist. `backend/evals/` holds only the
  golden sets and runners of SPEC-BE-085 (Command Chat) and SPEC-BE-086 (RAGAS, AI replies).
- If you touch `requirements.txt`, env vars, or `config.py`, check
  `specs/SPEC-BE-001..003.md` and update the matching spec rather than editing
  the code in isolation.
- **Production (since 2026-10-21):** cPanel host s106.srvx.ws (LiteSpeed + CloudLinux
  selectors), database still Neon. Backend = Python 3.12 app at api.pilotsonic.com from
  `backend/passenger_wsgi.py` (a2wsgi, installed by the setup script, not in
  `requirements.txt`; the server forks after loading it, so the a2wsgi loop is per process
  and the startup DB connection is disposed). `SCHEDULER_ENABLED=false` there; jobs run from
  the crontab via `backend/run_jobs.py`, which must `import app.main` so every ORM model is
  registered. Frontend = Node app at pilotsonic.com. Setup scripts:
  `backend/deploy/cpanel/setup.sh`, `frontend/deploy/cpanel/{setup.sh,app.js}`. The Railway
  and Vercel files are from earlier hosts (Railway was stopped, not deleted).
