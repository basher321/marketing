# SPEC-BE-077: Photo and video generation (provider abstraction)

Status: IMPLEMENTED (code, 2026-10-03; approved by the user). Providers checked against dev fakes (12 checks). **Pending:** the `generation_jobs` DDL and acceptance 1–10 on the live DB (Postgres unreachable). Veo and Sora haven't been called for real yet (needs the user's keys and video models). Depends on SPEC-BE-074 (media library). Extends SPEC-BE-070 (creative providers).
Decisions (user, 2026-10-03): D2 = Google Veo (Gemini key), OpenAI Sora (OpenAI key) and MCP video tools, in the order each company sets.

## Purpose
Organic Marketing → **Photo Generation** and **Video Generation**:

prompt → generation provider → preview → regenerate/edit → approve → use in a post (publish/schedule through SPEC-BE-076).

The provider sits behind one abstraction, so it can be changed per company without code changes.

## Provider abstraction (extends `ai/creative_providers.py`)
- **New kind `video`.** Video is slow (30 s – several minutes), so video providers are **asynchronous**:
  ```python
  class VideoProvider(Protocol):
      key: str; kinds = {"video"}
      def available(db, tenant_id) -> bool
      def start(db, tenant_id, req: CreativeRequest) -> str          # provider job ref
      def poll(db, tenant_id, ref: str) -> Pending | CreativeResult   # CreativeResult.video bytes
      def supported(req) -> Supported   # nearest duration/ratio/resolution it can do
  ```
- **`CreativeRequest` gets new fields:** `duration_s`, `style`, `reference_media` (bytes + mime, from the media library or product photos), `negative_prompt`, `resolution`.
- **Built-in video providers (decision D2)**, both using the company's keys saved in AI Models (SPEC-BE-053) and a `video_model` chosen per provider from the provider's live model list, as `image_model` is:
  - `gemini_video`: Google Veo through the Gemini API (long-running operation; poll; download the result).
  - `openai_video`: OpenAI Sora through `/v1/videos` (create; poll; download content).
  - MCP creative tools can map a `video` tool (as for images in SPEC-BE-070), using the same start/poll pattern if the tool returns a job ID, or a direct result otherwise.
  - The exact endpoints, parameters, durations and ratios are confirmed against each provider's current docs at implementation time, and recorded in the spec's implementation notes.
- **Durations are what the provider supports.** Providers produce short clips (typically 4–12 s per generation).
  - A request is mapped to the provider's **nearest supported duration**, and the response says so. For example, "15 s requested → 12 s generated (longest this provider makes)".
  - Clips are never stitched or extended (no ffmpeg); that is a follow-up.
- **Image providers** (`openai_image`, `gemini_image`, MCP) gain **reference images**: Gemini takes inline image parts; OpenAI uses the image edit endpoint. That gives "use my product photo" and "edit: make the background white".
- **Order and fallback:** each company sets the provider order for `video` (and `image`) in AI Models, as SPEC-BE-070 does. Fallback to the next provider only happens **before** a job starts (not set up, or start error); a started job that fails reports its error.
- **Cost guard:** the estimated cost (image per call, video per second, constants in `creative_providers`) counts toward the company's existing daily AI limit, the same guard the AI Autopilot uses. Over the limit → 429 with the remaining budget.

## Table (additive DDL)
```sql
CREATE TABLE generation_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  kind text NOT NULL CHECK (kind IN ('image','video')),
  status text NOT NULL CHECK (status IN ('queued','running','succeeded','failed','cancelled')),
  request jsonb NOT NULL,             -- prompt, product_ids, reference_media_ids, aspect_ratio, duration_s, style, target_platform
  effective jsonb NOT NULL DEFAULT '{}',  -- what the provider actually does (duration/ratio mapping)
  provider text, model text, provider_ref text,
  attempts jsonb NOT NULL DEFAULT '[]',
  result_media_id uuid REFERENCES media_assets(id) ON DELETE SET NULL,
  parent_job_id uuid REFERENCES generation_jobs(id) ON DELETE SET NULL,   -- regenerate/edit lineage
  approved_at timestamptz, approved_by uuid REFERENCES users(id) ON DELETE SET NULL,
  cost_cents int NOT NULL DEFAULT 0, error text,
  created_by uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz
);
CREATE INDEX generation_jobs_tenant_idx ON generation_jobs (tenant_id, created_at DESC);
```

## Running jobs
- `POST` creates a `queued` job and runs it with `scheduler_service.run_soon` (inline under `INLINE_JOBS`).
- **Images** finish in that one run.
- **Video** starts, stores `provider_ref`, then polls every 10 s up to `VIDEO_TIMEOUT_S` (default 600) → `failed: "timed out"`.
- A job left `running` by a restart is picked up by a 1-minute `generation_tasks` job that resumes polling from `provider_ref`.
- The result is saved to the media library (`source = ai_image|ai_video`, `metadata.prompt/provider/model`). The prompt is saved for the user's own history and is never logged in full (truncated to 200 characters).
- **Safety:** prompts are checked by `ai/moderation.py` before the provider call. A provider refusal is a `failed` job with the provider's reason.

## API (`api/v1/generation.py`, `services/generation_service.py`)
| Method | Path | Role | Notes |
|---|---|---|---|
| POST | `/organic/generate/photo` | agent+ | `{prompt, product_ids?, reference_media_ids?, aspect_ratio, style?, target_platform?, count 1–4}` → 202 job(s) |
| POST | `/organic/generate/video` | agent+ | `{prompt, product_ids?, reference_media_ids?, aspect_ratio (9:16, 16:9, 1:1 where supported), duration_s, style?, target_platform?}` → 202 job |
| GET | `/organic/generations` | viewer+ | `?kind=&status=&page=` |
| GET | `/organic/generations/{id}` | viewer+ | job + media (signed URL) + `effective` |
| POST | `/organic/generations/{id}/regenerate` | agent+ | same request, or with edits (`prompt`, `aspect_ratio`…) → new job, `parent_job_id` set |
| POST | `/organic/generations/{id}/edit` | agent+ | image only: `{instruction}`; the previous result is used as the reference → new job |
| POST | `/organic/generations/{id}/cancel` | agent+ | queued/running |
| POST | `/organic/generations/{id}/approve` | manager+ | marks the media approved; optional `{create_content: {caption?, targets[…], adapt}}` creates a SPEC-BE-076 content with this media in one step |
| GET | `/organic/generation/providers` | viewer+ | readiness per kind: which providers are set up, their models, supported ratios and durations |

- **Target platform:** when `target_platform` is set, the default `aspect_ratio` comes from that platform's rules (SPEC-BE-076), e.g. TikTok/Reels 9:16 and IG feed 4:5.
- **Audit:** every write is audited (`generation.*`).

## dev_fakes
Answers Veo, Sora and image-edit calls with small fixture files, and supports a fake "running → done after N polls" for video.

## Acceptance criteria (live DB, rolled back, dev_fakes, `INLINE_JOBS`)
1. Photo, 4:5, Gemini key + model saved → job `succeeded`; the media row is `ai_image` with ratio within tolerance and has a signed URL.
2. Video, 15 s, 9:16 → `effective.duration_s` is the provider's nearest supported value and the response states it; after fake polls → `succeeded`; the media row is `ai_video` with its duration read.
3. No video provider set up → 409 "Set up a video model in Integrations › AI Models"; readiness lists why.
4. The first provider's start error → the next provider is used; `attempts` records both.
5. Regenerate → a new job with `parent_job_id`; the first media is untouched. Image edit sends the previous image as the reference.
6. Approve with `create_content` → an organic content (SPEC-BE-076) in `approved` with that media.
7. Daily AI limit exceeded → 429; nothing is started.
8. Cancel a running video → `cancelled`; a late provider result is discarded.
9. Restart simulation: a `running` job is resumed by `generation_tasks`.
10. Another tenant's job → 404. Viewer generate → 403.

## Target files
- New: `models/generation.py`, `schemas/generation.py`, `services/generation_service.py`, `api/v1/generation.py`, `workers/tasks/generation_tasks.py`.
- Changed: `ai/creative_providers.py` (video kind, reference images, Veo/Sora providers, costs), `services/ai_model_service.py` (`video_model` per provider + model list filter), `api/v1/ai_models.py` and its schema (`video_model`), `integrations/dev_fakes.py`, `workers/schedules.py`, `api/router.py`.

## Out of scope
Clip stitching or extension, voice-over and music, subtitles, avatars, and editing video in a timeline.

## Implementation notes (2026-10-03)
- **Provider API details** (checked 2026-10-03 against ai.google.dev/gemini-api/docs/veo and developers.openai.com video generation):
  - **Veo:**
    - `POST v1beta/models/{model}:predictLongRunning` with `instances[{prompt, referenceImages}]` and `parameters{aspectRatio 16:9|9:16, durationSeconds 4|6|8, negativePrompt}`;
    - 8 s is required with reference images;
    - poll `GET v1beta/{operation}`, then download `response.generateVideoResponse.generatedSamples[0].video.uri` with the `x-goog-api-key` header (redirects followed).
  - **Sora:**
    - `POST /v1/videos {model, prompt, seconds, size}` (multipart with `input_reference` when a reference image is given; it is centre-cropped to the video size first);
    - poll `GET /v1/videos/{id}` (queued / in_progress / completed / failed), then `GET /v1/videos/{id}/content`.
- **Sora durations:** sources disagreed (4/8/12, and up to 20 s in newer docs). The conservative `4, 8, 12` is used (`OpenAIVideoProvider.DURATIONS`). Widen it after a real call confirms longer values.
- **Sizes:** 9:16 → 720x1280, 16:9 → 1280x720. A 1:1 request maps to the nearest supported ratio, and the note says so.
- **Video models:** each company picks one per provider in AI Models (`video_model`, `has_video` on openai/gemini). The live model lists now have a `video` bucket (names with veo / sora). The creative order has a `video` kind (default `gemini_video`, then `openai_video`), and MCP tools can map `video`; they answer synchronously.
- **Image references:** Gemini uses inline image parts; OpenAI uses `/v1/images/edits` with `image[]` files.
- **Costs** (estimates for the daily limit only): video 40¢/s (Veo), 10¢/s (Sora). The guard shares `tenants.llm_daily_cap_cents` with the AI Autopilot (runs + generations, last 24 h).
- **Run loop:** `POLL_INTERVAL_S` (10) and `VIDEO_TIMEOUT_S` (600) are module constants; a check can set the interval to 0. `generation_tasks` (every minute) resumes jobs not polled for 2 minutes and starts queued jobs older than 2 minutes.
- **Command Chat:** generation runs inside the plan step (`run=False` + `run_job`), so `$n.media_id` is ready for the next step.
- **No-DB checks (pass):**
  - Veo 15 s → 8 s; Sora 15 s → 12 s; 1:1 → a supported ratio; note text "15 s requested → 12 s generated";
  - both providers: start → running → done MP4, with cost = ¢/s × seconds;
  - Veo start error → `ProviderFailed` (so fallback happens);
  - OpenAI image with a reference → the edits endpoint; Gemini image with an inline reference;
  - Sora reference fitting; video kind registered; model-list kinds.
- **Pending (live DB):** the DDL, then acceptance 1–10.
