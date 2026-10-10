# SPEC-BE-095: Voice commands for Command Chat (speech in, spoken reply in the same language)

Status: IMPLEMENTED and verified (2026-10-10), approved by the user (2026-10-10). The frontend is SPEC-FE-062.
- Dev fakes, live Postgres, one rolled-back transaction: 27/27 checks (AC1-AC3), nothing persisted.
- AC4: stub eval 31/31; ruff 1 / mypy 7 (baseline).
- Real run (pilotsonic keys, rolled back): Claude translated a plan reply into Bengali, OpenAI `gpt-4o-mini-tts` read it
  (156 KB MP3), `whisper-1` transcribed that MP3 back as `bn`, and the replay came from the cache.
  **Quality finding:** `whisper-1` makes Bengali spelling mistakes ("করিকল্পনাটি" for "পরিকল্পনাটি"). The user reviews
  the transcript before sending, so it can be fixed. `gpt-4o-transcribe` is likely better, but it doesn't return the language.
- **Deviations:**
  - The speech route answers JSON with base64 audio, not raw audio with `X-Voice-*` headers, because `main.py`'s CORS
    setup exposes no custom headers.
  - `ChatMessage.voice: bool` was added next to `voice_language`, because a voice message's language can be unknown (null).
  - Whisper's names that differ from CLDR are mapped by an alias table (CLDR says "Bangla", Whisper says "bengali").

Asked: "We need to add voice command, so that user can give his speech as voice command or voice
prompt any language and then command chat will do as voice command and you will keep voice reply for
input language." and "do not change anything in the entire software except this change."

## Context

- **What exists:** Command Chat takes typed text only (`POST /orchestrator/messages`). Its replies
  (plan, clarification and summary) are fixed English templates in `orchestrator_service`. The planner
  LLM already reads commands in any language, and `command_guard.numbers_in` already reads Bengali
  digits, so a transcript in any language can go through the normal planner and guards unchanged.
- **Speech services on the company's own AI Model keys (SPEC-BE-053/088), plain `httpx`:**
  - OpenAI: `POST /v1/audio/transcriptions` (`whisper-1`, `verbose_json` returns `language`) and
    `POST /v1/audio/speech` (`gpt-4o-mini-tts`, already used by SPEC-BE-094).
  - Groq: `POST /openai/v1/audio/transcriptions` (`whisper-large-v3`, `verbose_json`, `language`).
  - Gemini: `generateContent` with inline audio (transcribe + detect language as JSON) and
    `gemini-2.5-flash-preview-tts` (24 kHz PCM, wrapped as WAV here).
- **Storage without DDL:** `orchestrator_messages.parsed_intent` (jsonb) exists on every row.

## Requirements

- **FR1 (transcribe):** `POST /orchestrator/voice/transcribe` (any role, multipart `audio`).
  - **Input:** WebM/Ogg (Opus), MP4/M4A, MP3 or WAV, recognised by magic bytes, at most 1.9 MB (under
    the 2 MB body limit, about 2 minutes of Opus) and not empty. Otherwise 422 with a plain message.
  - **Chain:** the company's own keys, in this fixed order: OpenAI → Groq → Gemini. A provider without a
    key is skipped. Any error, timeout or 429 moves to the next one. The `.env` LLM key is never used
    (companies use their own models, SPEC-BE-088).
  - **Answer:** `{text, language, provider}`. `language` is an ISO 639-1 code (Whisper's names such as
    "bengali" are mapped), or null when unknown. Silence or empty text → 422 "I couldn't hear any
    words. Try again closer to the microphone.".
  - **No provider:** 409 "Voice commands need an OpenAI, Groq or Gemini key in Integrations › AI Models."
  - **All failed:** 503 naming each provider's short reason.
  - The audio is never stored or logged. Only provider, language and duration are logged.
- **FR2 (send a voice command):** `ChatMessageCreate` gets an optional `voice: {language: str | null}`.
  - The user message is stored and planned exactly as typed text (same planner, guards and approval
    policy, so spend steps still need the owner). Voice adds no new rights.
  - `parsed_intent.voice = {language}` is stored on the user message, and `ChatMessage` gets
    `voice_language: str | null` so the chat can show a "Voice" badge after a reload.
- **FR3 (spoken reply):** `POST /orchestrator/messages/{id}/speech` (any role) with
  `{language: str | null}` returns `{audio (base64), mime, text, language, provider, note}` for an AI
  message of the company: MP3 from OpenAI, WAV from Gemini. JSON, not raw audio with headers, because
  `main.py`'s CORS setup exposes no custom headers and stays unchanged. Another company's or a user
  message → 404.
  - **What is spoken:** the message's text in `language`. When the language isn't English, the company's
    AI text chain translates it for speech: short and natural, the same facts, numbers, names and step
    numbers, no markdown. The translation is saved in the reply's `parsed_intent.voice_text[language]`, so a
    replay costs only the voice. A failed translation speaks the original text and says so in `note`.
  - **Plain speech:** list markers, URLs and ids are removed before speaking. The text is cut at 1,200
    characters with "…and more on screen".
  - **Voice chain:** OpenAI `gpt-4o-mini-tts` (voice from `tenants.settings.creative.video_audio.voice`, default
    alloy; instructions "Speak in <language name>, clearly and warmly") → Gemini TTS. Same 409/503 rules as FR1.
  - `text` is the spoken text, so the chat can show it as a caption.
- **FR4 (unchanged):** typed messages and their replies, the planner prompt, guards, approval policy,
  plan execution, every other route, and the stored reply text (the translation is only for speech).

## Edge cases

- A transcript that only says "yes"/"approve": it goes to the planner as text, like typing it. Voice
  never approves a step; approving stays a button.
- A mixed-language command (e.g. Banglish): Whisper's detected language is used for the reply.
- The summary arrives later (after the steps run): the chat asks FR3 for it too (SPEC-FE-062).
- `LLM_PROVIDER=mock` / no company keys: FR1 and FR3 answer 409. The app still boots and typed chat works.

## Acceptance criteria (dev fakes on the live DB, one rolled-back transaction)

- **AC1:** a WebM transcribes to `{text, language, provider:"openai"}`. With an OpenAI 429, Groq answers.
  Without keys → 409. A text file → 422. 2 MB → 413/422.
- **AC2:** a voice message is stored with `voice_language`, planned the same as the typed text (same
  actions), and the listing returns `voice_language` after a reload.
- **AC3:** speech for an English reply returns MP3 with no translation. For `bn` it translates once (second
  call: no LLM call), returns audio and the Bengali `text`. A user message or another company's message → 404.
- **AC4:** stub eval `run_command_eval.py` 31/31; ruff/mypy baseline unchanged (1 / 7).

## Target files

- `backend/app/api/v1/orchestrator.py` (3 routes)
- `backend/app/schemas/orchestrator.py` (`VoiceInfo`, `voice` on create, `voice_language`, `TranscriptRead`, `SpeechRequest`)
- `backend/app/services/orchestrator_service.py` (store/return voice, speech text + translation cache)
- **New:** `backend/app/ai/speech.py` (STT and TTS chains, magic bytes, language names, WAV wrap). Needs approval.
- `backend/app/integrations/dev_fakes.py` (fake transcription and TTS answers for verification only)

## Amendment A (2026-10-10): accurate transcription

Asked: "do change and check fucntionality works or not" (after the report of `whisper-1`'s Bengali mistakes).

Measured on one Bengali sentence spoken by OpenAI TTS (pilotsonic's keys): `whisper-1` wrote it in Devanagari
(wrong script); `gpt-4o-transcribe` made 2 word errors; `gpt-4o-mini-transcribe` was exact in 1.0 s; Gemini was exact
in 6.0 s; Groq's saved key is invalid (401).

- **FR1 change (OpenAI step):** the text comes from `gpt-4o-mini-transcribe` (`json`). Since it reports no language,
  the language is:
  1. the script's language when the transcript's letters are mostly one script used by one main language (Bengali → bn,
     Gurmukhi → pa, Gujarati, Tamil, Telugu, Kannada, Malayalam, Sinhala, Thai, Lao, Khmer, Myanmar, Georgian, Armenian,
     Greek, Hebrew, Ethiopic → am, Hangul → ko, Kana → ja);
  2. otherwise `whisper-1`'s detected language (`verbose_json`), requested at the same time so it adds no wait;
  3. otherwise null.
  If `gpt-4o-mini-transcribe` fails, the step falls back to `whisper-1`'s own text; if both fail, the chain moves on.
- Groq and Gemini steps unchanged.
- **Result (2026-10-10):** through `speech.transcribe()` on pilotsonic's key, Bengali, English, Hindi and Arabic each came
  back word for word with the right language (bn, en, hi, ar) in about 2 s. The fake-transport checks stay 27/27, and
  ruff/mypy are at the baseline (1 / 7). The browser E2E is in SPEC-FE-062 (18/18).
- **AC5:** the Bengali sentence through the real OpenAI step → exact text and `bn`. A headless Chrome with a fake microphone
  playing that sentence goes through the page: mic → transcript in the composer with "Bengali" → Send → plan → spoken
  Bengali reply.
