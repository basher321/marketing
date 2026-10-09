# SPEC-BE-093: Command Chat media failover (Google → OpenAI) and OpenAI slideshow videos

Status: IMPLEMENTED and verified (2026-10-09), approved by the user: "first claude google and the
failover is openai, follow this sequence if anyone fail then others will do its job, and you can do for
B". This amends SPEC-BE-092: chat images and videos are no longer pinned to a single provider.
- Dev fakes, live Postgres, rolled back: AC1-AC5 pass, plus a Veo polling failure → slideshow.
  The slideshow measured 7.00 s at 1080×1080 (ffmpeg). Persisted rows: 0, and the media files were removed.
- AC6: stub eval 31/31; ruff 1 / mypy 7.
- AC7, real run (pilotsonic, rolled back):
  - Image: Nano Banana 429 → OpenAI `gpt-image-2.5-flare` (21 s).
  - Video: Veo 429 → OpenAI slideshow, 2 images, 6.00 s at 720×1280 (28 s). The frames show the zoom and
    the crossfade.
- FR6 done: pilotsonic's order is anthropic → gemini → openai → groq → openrouter → ollama (audited).
- Deviation, needed for FR5: `run_job` commits before `_finish` for a synchronous result, because
  `_finish` refreshes the job and dropped uncommitted effective/notes/attempts. This also fixes the same
  loss for synchronous MCP tools on the Organic pages.
- Not yet run: a real Veo video, which needs Google billing.

## Context

- **Google is blocked for now:** chat media was pinned to Google (SPEC-BE-092), and then briefly to
  OpenAI. pilotsonic's Gemini key is on Google's free tier (HTTP 429 for Nano Banana and Veo).
- **OpenAI has no video:** OpenAI shut down the Sora Videos API on 2026-09-24 (`/v1/videos` answers 404
  even though the model list still shows `sora-2`), and it has no other video model.
- **Option B,** which the user chose as OpenAI's video: OpenAI makes a few images, and we join them into an
  MP4 with slow zoom/pan and crossfades. It isn't real motion video.
- **Claude** makes neither images nor videos. For text the user's order is Claude → Google → OpenAI. That
  is the company's AI Models priority order (SPEC-BE-053/088), a setting and not code.

## Requirements

- **FR1 (image chain):** chat `generate_photo` tries `gemini_image` (Nano Banana), then `openai_image`.
  The job request carries `"providers": ["gemini_image", "openai_image"]`. Any failure of the first
  (429, error, refusal) moves on to the next, which is the existing `cp.generate` behaviour.
- **FR2 (video chain):** chat `generate_video` tries `gemini_video` (Google Flow / Veo 3.1), then
  `openai_slideshow` (FR4). Sora is not in the chain, because its API is shut down.
  - A failure at start, or (for pinned jobs only) a failure while polling, moves on to the next provider.
  - A timeout still fails the job.
  - Jobs without `providers` (the Organic pages) keep today's behaviour exactly.
- **FR3 (readiness):** the step fails before any job is created only when no provider in the chain is set
  up: "No image provider is set up: add a Google Gemini key with a Nano Banana image model, or an OpenAI
  key with an image model, in Integrations › AI Models." (and the matching video text, naming a Veo video
  model or an OpenAI image model).
- **FR4 (OpenAI slideshow video, `openai_slideshow`):**
  - **Availability:** an OpenAI key and an OpenAI *image* model (no video model needed).
  - **Length:** the duration is the request's, clamped to 4–30 s.
  - **Size:** 9:16 → 720×1280, 16:9 → 1280×720, anything else → 1080×1080.
  - **Images:** n = ceil(duration / 3), clamped to 2–6, made with the company's OpenAI image model. Each
    uses the prompt plus a shot hint (wide establishing shot, close-up detail, different angle, lifestyle
    in use, …), at the nearest OpenAI size (2:3, 3:2, 1:1). Reference images are passed on as today.
  - **Video:** ffmpeg (the `imageio-ffmpeg` bundled binary) scales and crops each image to the output
    size, adds a slow zoom (Ken Burns) and 0.5 s crossfades, and encodes H.264 yuv420p at 30 fps with
    `+faststart` and no audio. It is synchronous: `start` returns the finished result.
  - **Cost estimate:** n × the OpenAI image cost, for the daily AI limit.
  - **Failures:** ffmpeg missing, a non-zero exit or a 5-minute timeout raise `ProviderFailed`.
  - **Scope:** the provider is registered as chat-only (`cp.CHAT_ONLY`), so it doesn't appear in the
    creative order setting or on the Organic pages.
- **FR5 (result):** the step summary names the provider that actually made the media ("Image made with
  Nano Banana (…)" / "with OpenAI images (…)", "Video made with Google Flow (Veo, …)" / "Video made with
  OpenAI images as a slideshow (n images, …)"). It also says when an earlier provider failed, for example
  "Nano Banana failed (HTTP 429 …), so OpenAI made it." `media_kind`, `provider` and `model` stay as they
  are, and the chat preview (SPEC-FE-057) is unchanged.
- **FR6 (text order setting):** pilotsonic's AI Models priority is set to Claude → Gemini → OpenAI
  through the existing order service, as the user asked. No code change.
- **FR7 (dependency):** `imageio-ffmpeg==0.6.0` is added to `backend/requirements.txt`, and SPEC-BE-001
  notes it.

## Edge cases

- **Nothing set up:** Gemini has no key or model and OpenAI has none: FR3, and no job row.
- **Both fail:** the job fails with every attempt listed, and the step shows it.
- **Veo refuses after start:** the next provider is tried (pinned jobs only).
- **Slideshow partial failure:** any image failing makes the slideshow fail. It never makes a shorter one
  silently.

## Acceptance criteria

- **AC1:** Gemini answers 429 → the chat image comes from `openai_image`, and the attempts list both.
- **AC2:** Veo fails at start → the chat video is an `openai_slideshow` MP4 whose duration (ffprobe)
  matches the request within ±0.5 s at the right size.
- **AC3:** Veo works → the video comes from `gemini_video` (dev fakes).
- **AC4:** neither is set up → the FR3 messages, and no job row.
- **AC5:** an Organic page video job (no `providers`) still tries Veo, then Sora, as before; the slideshow
  isn't listed in the creative order or the readiness list.
- **AC6:** stub eval 31/31; ruff / mypy baselines (1 / 7).
- **AC7:** a real run with pilotsonic's keys: an image and a short video are made through the chain.

## Target files

- `backend/app/ai/creative_providers.py`: `OpenAISlideshowProvider`, `CHAT_ONLY`, `provider(key)`.
- `backend/app/services/generation_service.py`: the pinned lookup includes CHAT_ONLY, the poll failover
  for pinned jobs, and the label.
- `backend/app/ai/command_actions.py`: the chains, the readiness check, and the summaries.
- `backend/requirements.txt`, `specs/SPEC-BE-001.md`.
- `CLAUDE.md`: the SPEC-BE-092 entry is updated.

## Amendment (2026-10-09): the video cost estimate follows the providers that may run

- **Reported by the user:** "Today's AI spending limit is reached: 4.96 USD left of 5.00 (estimate 6.00)."
- **Cause:** `generation_service._estimate` charged the requested length at the highest per-second
  rate: 15 s × 40¢ = $6.00. Veo makes at most 8 s, and the slideshow is priced per image.
- **Change:** the estimate is the maximum over the job's ready providers of what each really makes:
  Veo/Sora get the rate × `supported()` duration, and `openai_slideshow` gets `frames(duration)` × the
  OpenAI image cost. This applies to every video job, the Organic page included (the same overestimate).
- **pilotsonic now:** 8, 15 and 30 s all estimate $3.20 (it was $3.20 / $6.00 / $12.00). The BE-093
  checks still pass, and ruff and mypy are at their baselines.
- **Limit:** the daily limit itself (`tenants.llm_daily_cap_cents`, $5 for pilotsonic) can't be changed
  in the app.
