# SPEC-BE-092: Command Chat makes images with Nano Banana and videos with Google Flow (Veo)

Status: SUPERSEDED in part by SPEC-BE-093 (2026-10-09): chat media is now a Google → OpenAI chain,
not pinned to Google. Originally IMPLEMENTED and verified (2026-10-09), approved by the user ("approve spec and go execution").
- Live Postgres, one rolled-back transaction, dev fakes: AC1-AC5 pass (chat photo = gemini_image only
  while OpenAI images are set up; chat video = gemini_video, and a Gemini failure fails the step with no
  OpenAI call; FR4 messages with no job row; summary items carry media {id, kind}, and GET /media/{id}
  returns 200; an Organic page job still uses openai_image). Persisted rows: 0. The test media files were
  deleted from MEDIA_ROOT.
- AC6: stub eval 31/31; ruff 1 / mypy 7 (baselines).
- Not yet run against Google's real API (needs the company's Gemini key with Nano Banana / Veo access).
Requested by the user: "we will use nano banana for imge generation and google flow is for video
generation. so make my http://localhost:3000/chat, command chant for creating image and video by using
these nano banana and google flow. you will follow spec driven devolopment. do not change anything in the
entire software except this." The chat-side display is SPEC-FE-057.

## Context

- Command Chat already has `generate_photo` and `generate_video` (SPEC-BE-078). They call
  `generation_service.start(...)`, which tries the company's creative order (`ai/creative_providers.ordered`).
  - The default image order is OpenAI image → Gemini image.
  - The default video order is Veo (Gemini) → Sora (OpenAI), and MCP tools are tried last.
  So a chat image is made by OpenAI whenever the company has an OpenAI image model.
- **Nano Banana** is Google's name for the Gemini image models: `gemini-2.5-flash-image`, Nano Banana 2 /
  2.1, Nano Banana Pro `gemini-3-pro-image`, and so on. They are reached through
  `models/{model}:generateContent` with `responseModalities: ["IMAGE"]`, which is what
  `GeminiImageProvider` already sends.
- **Google Flow** is Google's video app (flow.google.com). It has **no public API**. The only unofficial
  wrappers drive a signed-in browser session, which can break at any time and isn't allowed by its terms.
  Flow makes its videos with **Veo 3.1**, which developers reach through the Gemini API
  (`models/veo-3.1-*:predictLongRunning`, 4/6/8 s, 16:9 or 9:16). That is what `GeminiVideoProvider`
  already sends. "Google Flow" in this spec therefore means Veo 3.1 through the company's Gemini key.
- Google's model ids change often. For example, `gemini-3.1-flash-image` shuts down on 2026-10-29. The
  company already chooses its Gemini image and video models in Integrations › AI Models (SPEC-BE-053/077),
  from Google's live list, and `ai/providers.py` deliberately never picks one silently. This spec keeps
  that rule and hardcodes no model id.

## Requirements

- **FR1 (images = Nano Banana only):** a chat `generate_photo` step uses only the `gemini_image` provider,
  with the company's chosen Gemini image model. OpenAI images, the catalog and MCP tools are **not** tried
  for chat images.
- **FR2 (videos = Google Flow / Veo only):** a chat `generate_video` step uses only the `gemini_video`
  provider, with the company's chosen Gemini video model. Sora and MCP tools are **not** tried for chat
  videos.
- **FR3 (pinning the provider):** the job's request carries `"providers": ["gemini_image"]` or
  `["gemini_video"]`. `generation_service` honours it wherever it picks providers: the first run,
  `resume_stale`, and regenerate/edit of that job, which inherit the request. Jobs without the key behave
  exactly as today.
- **FR4 (not set up):** with no Gemini key, or no Gemini image/video model chosen, the step fails before
  any job is created. It never falls back to another provider, and the message is fixed:
  - image: "Nano Banana isn't set up: add a Google Gemini key and choose a Nano Banana image model
    (e.g. gemini-2.5-flash-image) in Integrations › AI Models."
  - video: "Google Flow (Veo) isn't set up: add a Google Gemini key and choose a Veo video model
    (e.g. veo-3.1-generate-preview) in Integrations › AI Models."
- **FR5 (planner wording):** the action descriptions say "Nano Banana (Gemini image)" and "Google Flow
  (Veo 3.1)". "make a picture with nano banana" or "a google flow video of …" therefore plans
  `generate_photo` / `generate_video`. The words `nano banana`, `banana`, `flow`, `veo`, `picture`,
  `image`, `photo` and `video` count as request evidence for these two actions in `ai/command_guard.py`'s
  scope check, as far as the existing words list needs them.
- **FR6 (result):** the step result keeps `summary`, `media_id`, `generation_id` and `link`, and adds
  `media_kind` (`image` | `video`), `provider` (`Nano Banana` | `Google Flow (Veo)`) and `model`. The
  summary names them, for example "Image made with Nano Banana (gemini-2.5-flash-image)." or "Video made
  with Google Flow (Veo 3.1, veo-3.1-generate-preview): 8 s, 9:16. <notes>".
- **FR7 (chat summary item):** `ResultItem` (`schemas/orchestrator.py`) gets an optional
  `media: {id, kind} | null`, filled from the step result's `media_id` / `media_kind`. No URL is stored
  in the message, because signed URLs expire; SPEC-FE-057 fetches a fresh one through the existing
  `GET /media/{id}`.
- **FR8 (unchanged):** the Organic Photo/Video Generation pages, Create with AI (SPEC-BE-069/070),
  `create_organic_posts` with `media: generate_*`, the creative order setting, AI Models, and every other
  action keep their current behaviour. The existing daily cost guard and moderation still apply.

## Edge cases

- **Wrong model kind:** a chosen Gemini image model that isn't an image model is rejected by Google, and
  the job fails with Google's message. No fallback is tried.
- **Unsupported shape:**
  - A 1:1 or other ratio for video becomes Veo's nearest supported ratio, and other durations its nearest
    supported length, as today. The job notes say so, and the summary repeats the notes.
  - With a reference image, Veo makes 8 s.
- **Refused prompt:** Google refuses the prompt (safety): the step fails with "Gemini returned no image
  (it may have refused the prompt)" or "Veo finished without a video …".
- **Quota:** a 429 or quota error fails the step with Google's message.
- **Tenant isolation:** `reference_media_id` must still belong to the company (unchanged checks).

## Acceptance criteria

- **AC1:** a company with both OpenAI and Gemini image models set gets a chat `generate_photo` job whose
  `provider` is `gemini_image` and whose attempts list only `gemini_image` (dev fakes).
- **AC2:** a chat `generate_video` job uses `gemini_video`. Sora isn't tried even when the Gemini call
  fails, and the step fails with Google's error.
- **AC3:** with no Gemini key, or no image/video model chosen, the step fails with the FR4 text, and no
  `generation_jobs` row is created.
- **AC4:** the result and the summary `ResultItem` carry `media {id, kind}`, provider and model;
  `GET /media/{id}` returns a fresh URL for it.
- **AC5:** an Organic page photo job (no `providers` key) still follows the company order (OpenAI first).
- **AC6:** the stub Command Chat eval stays 31/31; ruff and mypy stay at their baselines (1 / 7).

## Target files

- `backend/app/ai/command_actions.py`: the two actions, the pinned providers, the readiness check, and the
  result fields.
- `backend/app/services/generation_service.py`: honour `request.providers`.
- `backend/app/ai/command_guard.py`: request words, only if needed (FR5).
- `backend/app/schemas/orchestrator.py`: `ResultItem.media`.
- `backend/app/services/orchestrator_service.py`: fill `media` in the summary items.

No DDL, no new settings, no new files.
