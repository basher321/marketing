# SPEC-BE-069: AI Ad Autopilot — prompt to published campaign

Status: IMPLEMENTED (2026-10-02). The DDL is applied (`ai_campaign_runs`; tenant FK cascades on delete; created_by is set null).

Verified on the live DB in rolled-back transactions with real tokens, a stubbed AI entry point and the platform dev fakes. 34 checks passed across two runs (13 + 21):
- Meta + X run to review, with both drafts passing their builder's Validate.
- Prompt injection is ignored.
- A forbidden word is repaired. An unfixable one, or a false discount, blocks publishing (409).
- Warnings need acknowledging.
- A manager's publish over the cap creates owner approvals, and the owner's approvals publish.
- A publish failure → `failed`; Retry publish then makes no new AI calls.
- needs_input → answer → review.
- All AI providers failing → `failed` with each reason; Retry completes.
- Cancel during visuals → no draft.
- Visuals "builder" works; TikTok without a video is blocked with "Upload a video".
- The Command Chat action, the daily AI limit, the audit trail, a viewer's 403 and tenant isolation.

Deviations:
- The visuals option "upload" became **"builder"** (add media in the builder). Videos (TikTok, YouTube) always come from the user, never faked.
- The Command Chat action's risk is `draft` (it only builds drafts), not `change`.
- Platform validation runs after assembly and is merged into the safety report.
- Meta drafts use the connection's pixel (sales/leads) and keep Instagram off unless an Instagram account is connected.
- Integrations gained optional "TikTok identity ID" and "Pinterest default board ID" fields.
- LLM costs are estimates for the limit guard.
- The default schedule starts 1 hour after creation and runs 7 days.
- The tenant reset (SPEC-BE-051) doesn't delete `ai_campaign_runs` yet.

Decisions made by the user on 2026-10-02:
- **never auto-publish**: every AI campaign stops at Ready for review, and a person clicks Publish;
- runs are stored in a new `ai_campaign_runs` table;
- images come from OpenAI, Gemini and product photos;
- MCP is outbound only.

Builds on SPEC-BE-053 (AI models), SPEC-BE-029 (creative generation), SPEC-BE-047 (spend-cap approval) and SPEC-BE-062…068 (multi-platform builder and adapters). Creative providers are in SPEC-BE-070, the screens in SPEC-FE-046.

## Purpose
A second way to create a campaign, alongside the manual builder. The user writes a prompt, and an automated pipeline produces the complete campaign: plan, targeting, copy and visuals. It then checks it, assembles it as a normal builder draft, and **always stops for review**: a person publishes it (user decision: never auto-publish). The user picks "Build manually" or "Create with AI" per campaign. Both produce the same kind of draft, so an AI campaign can always be opened and edited in the manual builder.

## Design principles
1. **Deterministic pipeline, not a free-roaming agent.** Each stage is a bounded step with a strict JSON contract (Pydantic). AI is used only inside stages that create something (plan, copy, image, review). The system never lets a model call platform write APIs directly.
2. **One write path.** Everything that changes or spends goes through `ads_builder_service` / `meta_builder_service`. That means the same validation, all-or-nothing publishing, spend-cap approval and audit as manual campaigns.
3. **Providers are pluggable** (SPEC-BE-070). Text, image and external generators (including remote MCP servers) sit behind one interface, so adding one never touches the pipeline.
4. **Fail safe.** Any doubt stops at "Ready for review", never at "published".

## Input: the prompt contract
`POST /api/v1/ai-campaigns` (manager+):
```json
{ "prompt": "Eid sale on our kurtas, 30% off, young professionals in Dhaka and Chattogram",
  "platforms": ["meta", "tiktok"],                 // 1–3; default: connected platforms
  "goal": "sales" | "traffic" | "leads" | "awareness" | "app" | null,   // null = inferred
  "budget": {"amount": "5000.00", "mode": "total" | "daily"},          // tenant currency; required
  "schedule": {"starts_at": "...", "ends_at": "..."},                  // optional; default 7 days from now
  "skus": ["KURTA-01"],                            // optional products to feature
  "landing_url": "https://…",                      // optional; default = product URL or tenant site
  "visuals": "generate" | "products" | "upload",   // products = the catalog images
  "media_ids": [],                                 // when visuals = upload
  "variants_per_group": 2,                         // 1–3 ads per ad group
  "providers": {"text": null, "image": null}       // null = tenant default order (SPEC-BE-070)
}
```
- Required: the prompt (10–2000 characters), a budget, and at least one connected platform.
- Anything missing that can't be inferred is returned as a fixed-template question (as in the Command Chat, SPEC-BE-059), and the run is kept as `needs_input`.
- The prompt is treated as **data**. It's wrapped in delimiters inside the system prompts, and instructions found inside it ("ignore previous…", "set budget to…", "publish now") can't change the structured fields. The budget and platforms come only from the form fields, and nothing in a prompt can publish.

## Pipeline stages
Stages run in the background (`scheduler_service.run_soon`, inline when the scheduler is off). Each stage records status, timing, provider, tokens/images used and its output on the run.

| # | Stage | What happens | Output contract |
|---|---|---|---|
| 1 | **Context** | Load brand voice (tone/style), forbidden terms, featured products (title, price, URL, images, stock), tenant currency/timezone, each target platform's registry entry (objectives, formats, text limits), and the 3 best past creatives by CTR | `RunContext` |
| 2 | **Plan** | LLM call → campaign plan per platform | `CampaignPlan`: objective key (from the platform's list), campaign type, budget split (sums to the user's budget), schedule, 1–3 ad groups each with audience *in words* (locations, ages, genders, interests/keywords), format per ad |
| 3 | **Targeting** | Map each audience word to the platform's own ID through the adapter's `lookup` (top match, case-insensitive). Entries with no match are dropped with a warning; a group left without a location fails the stage | resolved targeting |
| 4 | **Copy** | LLM call per platform format, with the format's exact fields and character limits in the schema. Violations go back to the model with the errors, up to 2 repairs | per-ad creative fields |
| 5 | **Visuals** | `products`: the catalog images. `upload`: the given media. `generate`: an image provider makes one image per required aspect ratio (1:1, 4:5, 9:16, 1.91:1 as the format needs) from a visual brief written in stage 4. Each image is uploaded to the platform with `upload_media` | media refs |
| 6 | **Safety review** | (a) forbidden/blocked terms (`moderation.moderate_text` + brand terms); (b) an LLM policy review of the copy against the platform's prohibited-content list (health claims, before/after, discrimination, special ad categories, misleading prices: a claimed discount must match the product data); (c) the landing URL resolves over https (SSRF-guarded HEAD); (d) the platform's own validate (`validate` / validate-only). Any (a)/(b)/(d) error → repair once, then stop at review | `SafetyReport` |
| 7 | **Assemble** | Create the draft through the existing builder services (Meta → `meta_builder_service`; others → `ads_builder_service`), with `metadata.ai_run_id` | campaign IDs |
| 8 | **Review** | The run stops at `ready_for_review` (always) | — |
| 9 | **Publish** | Only when a person clicks Publish: the builder's normal publish (all-or-nothing, SPEC-BE-062, with the spend-cap approval) | live IDs |

Run statuses: `queued → running(stage) → needs_input | ready_for_review | awaiting_approval | publishing → published | failed | cancelled`.

## Approval gates (safety before going live)
1. **No AI campaign publishes by itself** (user decision, 2026-10-02). Every run ends at **Ready for review**, where the user sees every ad (images, texts, audience, budget) and the safety report. They can then publish, edit in the builder, regenerate one ad, or discard. There's no auto-publish setting, and nothing in the prompt or in a model's output can trigger publishing.
2. **Publish** is manager+ and follows the existing rules unchanged: over the daily spend cap, a non-owner's publish becomes an owner approval item (SPEC-BE-047), and spend steps from the Command Chat need the owner's explicit approval (SPEC-BE-059).
3. Publish is refused (409) while the safety report has errors. Warnings are shown and must be acknowledged with a checkbox before Publish is enabled.
4. The run's AI cost is checked against the company's daily AI limit (`llm_daily_cap_cents`) before each paid stage. Over the limit, the run stops with that reason.

## Failure handling
- **Provider errors** (timeout, 429, 5xx, bad key): the next provider in the company's order (SPEC-BE-053 chain; SPEC-BE-070 for images), then the stage fails with a readable reason.
- **Invalid output** (schema, limits, policy): repaired with the errors fed back (max 2), then the stage stops at `ready_for_review` with the issues listed. Whatever was produced is kept.
- **Publish failure:** the builder's rollback (nothing left on the platform). The run becomes `failed` with the platform's message. "Retry publish" resumes from stage 9, without regenerating.
- **Resumable:** any stage can be retried; earlier stages' outputs are reused. Runs are idempotent on `run_id`.
- **Limits:** at most 20 LLM calls, 12 images and 10 minutes per run. Cancel is allowed at any time before publishing.
- **Platform rejection after publishing** (ad disapproved during review): shown on the run and the campaign. A "Fix with AI" action regenerates that ad's copy with the rejection reason and republishes it as a new ad (a later spec; listed here so the data is kept).

## Storage (additive DDL)
```sql
CREATE TABLE ai_campaign_runs (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  created_by uuid REFERENCES users(id),
  prompt text NOT NULL,
  request jsonb NOT NULL,           -- the validated input form
  status varchar(30) NOT NULL,
  stage varchar(30),
  stages jsonb NOT NULL DEFAULT '[]',  -- [{name, status, started_at, ended_at, provider, usage, output, error}]
  campaign_ids uuid[] NOT NULL DEFAULT '{}',
  cost_cents integer NOT NULL DEFAULT 0,
  error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_ai_campaign_runs_tenant ON ai_campaign_runs (tenant_id, created_at DESC);
```

## API
- `POST /ai-campaigns` → 202 `{run}`. `GET /ai-campaigns?status=` (list). `GET /ai-campaigns/{id}` (run + stages + previews; polled every 2 s by the UI).
- `POST /ai-campaigns/{id}/answer` `{answers}` (needs_input) · `/retry` `{from_stage?}` · `/cancel` · `/publish` (from review; manager+, normal approval rules) · `/regenerate` `{ad_id, what: "copy"|"image"}`.
- Command Chat: a new action, `create_ai_campaign` (risk `change`), in `ai/command_actions.py`, so "create a TikTok campaign for the Eid sale with 5000 taka" starts a run. It ends at review like every run; publishing from the chat stays a `spend` step that needs the owner's approval.

All writes are audited (`ai_campaign.*`). Every query is tenant-scoped, and another tenant's run returns 404.

## Acceptance criteria (live DB, rolled-back transaction, LLM via `LLM_PROVIDER=fixture`, images and platforms via `dev_fakes`)
1. A prompt for Meta and TikTok in review mode reaches `ready_for_review`, with one draft per platform. Each draft opens in its builder, passes Validate, and its copy is within the limits.
2. A prompt-injection line inside the prompt doesn't change the budget, platforms or mode.
3. A forbidden term in the generated copy → repaired. If it's still present, the run stops at review with the issue.
4. Every run stops at review, including one whose prompt says "publish now". Publish with safety errors → 409. Publish over the cap as a non-owner → an approval item; as the owner → published.
5. A publish failure at the ad step → rollback, the run is `failed`, and "Retry publish" succeeds without new LLM calls.
6. An LLM provider timeout → the next provider is used. All providers failing → `failed` with a reason.
7. Cancel during stage 5 → no draft. Tenant isolation holds, and a viewer gets 403.

## Target files
- New: `services/ai_campaign_service.py` (pipeline + gates), `ai/prompts/ad_planner.py` (plan / copy / review prompts + JSON schemas), `schemas/ai_campaign.py`, `api/v1/ai_campaigns.py`, `models/ai_campaign_run.py`.
- Changed: `ai/command_actions.py` (new action), `api/router.py`, `services/ads_builder_service.py` / `meta_builder_service.py` (only an optional `ai_run_id` on create).
