# SPEC-BE-094: Sound for AI slideshow videos (voiceover + the company's music)

Status: IMPLEMENTED and verified (2026-10-10), approved by the user (2026-10-09/10).
- The DDL is applied; the existing rows (5 videos, 2 images) are untouched.
- Dev fakes, live Postgres, rolled back: AC1-AC5 pass.
  - Generated MP3/M4A/WAV files are stored as audio, with durations.
  - Audio as post media → 422.
  - Every sound combination is a 6.0 s video with AAC: voice -24.8 dB, music -29.5 dB, both -24.5 dB.
    "Neither" stays silent with a note, and a TTS failure keeps the music with a note.
- AC6: stub eval 31/31; ruff 1 / mypy 7.
- AC7, real run (pilotsonic, rolled back):
  - Veo 429 → slideshow.
  - Claude wrote "Slow down, sip, and let the morning find you."
  - `gpt-4o-mini-tts` read it as alloy: 6 s video, AAC 48 kHz, -25.8 dB mean.
- **Deviation:** the mix is two ffmpeg runs: audio to a WAV, then a mux with the video copied. A single run
  (video input + amix + -t) produced only 0.06 s of audio, whether or not `-stream_loop` was used. The
  music loops with `aloop` + `atrim`. Asked: "ad published but i cant get any sound", then
"after producing videos, it shows but no sound i get, fix it". Chosen: "Voiceover + your music", for new
videos only. The settings card is SPEC-FE-060.

## Context

- **Every AI video so far is silent:** pilotsonic's three AI videos (2026-10-09 22:01, 22:07, 22:26) are
  `openai_slideshow` videos with no audio track. SPEC-BE-093 FR4 encoded them without sound (`-an`).
- **Why the slideshow runs:** Google Veo makes video with sound, but the Gemini key is on the free tier
  (429), so the chain always falls back to the slideshow.
- **What OpenAI offers:** text-to-speech (`POST /v1/audio/speech`; pilotsonic's key has `gpt-4o-mini-tts`
  and `tts-1`), but no music generation. Music therefore comes from a track the company uploads.

## Requirements

- **FR1 (DDL, additive):** the media library accepts audio.
  `ALTER TABLE media_assets DROP CONSTRAINT media_assets_kind_check, ADD CONSTRAINT media_assets_kind_check
  CHECK (kind = ANY (ARRAY['image','video','audio']));`
- **FR2 (audio uploads, `media_service`):**
  - **File types:** recognised by magic bytes, never the file name:
    - MP3: `ID3`, or an MPEG frame sync `FF Ex/Fx`;
    - M4A: `ftyp` with brand `M4A ` or `M4B `;
    - WAV: `RIFF….WAVE`.
  - **Size and length:** at most 20 MB. The duration comes from the bundled ffmpeg, or is None if
    unreadable.
  - **Never in posts or ads:** audio is never returned by `GET /media` without `kind=audio`, so every
    existing picker is unchanged. `media_rows` and the planner's `media_library` leave audio out:
    `media_rows` answers 422 "Audio files can only be used as background music for AI videos.".
- **FR3 (settings):** `tenants.settings.creative.video_audio` =
  `{voiceover: bool = true, voice: str = "alloy", music_media_id: str | null, music_volume: 0.05–1.0 = 0.25}`.
  - `GET /ai-models/video-audio` is open to any role and returns the settings plus `music` (the media item
    or null).
  - `PUT /ai-models/video-audio` is manager+. `music_media_id` must be the company's own audio item.
    The change is audited.
  - Voices are OpenAI's: alloy, ash, ballad, coral, echo, fable, nova, onyx, sage, shimmer, verse.
- **FR4 (slideshow sound, `creative_providers.OpenAISlideshowProvider`):**
  1. **Voiceover** (when on):
     - The company's AI text chain writes a script of at most ⌊2.3 × (seconds − 1)⌋ words in the brand's
       `primary_language`. It is plain spoken text with no hashtags or emojis, based on the video prompt.
     - OpenAI TTS (`gpt-4o-mini-tts`, the chosen voice, mp3) reads it.
     - If it runs longer than the video, it is sped up (at most 1.3×) and then trimmed with a fade.
  2. **Music** (when set): looped or trimmed to the video, at `music_volume` under a voice (twice that
     with no voice), with a 0.5 s fade-in and a 1.2 s fade-out.
  3. **Mixing:** ffmpeg mixes both into AAC 128 kb/s, 48 kHz stereo. The video is copied, not re-encoded.
  - **No sound source:** neither voiceover nor music → the video stays silent, with a note saying how to
    add sound.
  - **Failures never fail the video:** a voiceover failure (LLM or TTS) or an unreadable music file keeps
    whatever audio still works, and the reason is added to the job notes.
  - **Cost:** + an estimate of 1¢ per voiceover.
- **FR5 (notes):** `CreativeResult.notes` (new, default []) is appended to the job's notes by
  `generation_service._finish`, so the chat summary says "Voiceover added (alloy)", "Background music:
  <name>", or why not.
- **FR6 (unchanged):** Veo videos (they have their own sound), images, the Organic pages and every other
  media use.

## Acceptance criteria

- **AC1:** an MP3, an M4A and a WAV upload are stored as `audio` with a duration. A text file is still 422,
  and an MP4 is still a video.
- **AC2:** `GET /media` (no kind) leaves out audio, and `kind=audio` lists it. Using an audio id as post
  media → 422.
- **AC3:** with voiceover and music, the slideshow MP4 has a video stream and an AAC audio stream for the
  full duration (ffmpeg).
- **AC4:** voiceover only, music only, and neither each work. A failing TTS still gives a video (with
  music, if set) plus a note.
- **AC5:** the settings round-trip. A foreign or non-audio `music_media_id` → 422, and a viewer's PUT → 403.
- **AC6:** stub eval 31/31; ruff and mypy at their baselines.
- **AC7:** a real run with pilotsonic's keys gives a video with an audible voiceover (rolled back).

## Target files

- `backend/app/services/media_service.py`, `backend/app/schemas/media.py`, `backend/app/api/v1/media.py`;
- `backend/app/ai/creative_providers.py`, `backend/app/services/generation_service.py`;
- `backend/app/services/ai_model_service.py`, `backend/app/schemas/ai_model.py`,
  `backend/app/api/v1/ai_models.py`;
- `backend/app/services/orchestrator_service.py` (the `media_library` filter);
- the DDL above.
