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

## Amendment B (2026-10-10): "Voice commands need an OpenAI, Groq or Gemini key" with OpenAI set up

Reported by the user (Firefox; "we have openai model"). **Cause:** not the browser. The user was signed in as
abc@pilotsonic.com in a second company, **pilotsonic1**, which had no AI models; the keys were saved in **pilotsonic**
(abc@gmail.com). AI keys are per company (SPEC-BE-088), so pilotsonic1 had none.

**Fix:**
- At the user's choice, pilotsonic's AI Models settings (the same encrypted keys, models and order) were copied into
  pilotsonic1, with an `ai_models.copied` audit entry. A real voice test there gave "আমার পণ্যগুলো দেখাও।" (bn, OpenAI).
- The 409 messages now name the signed-in company: "Each company has its own AI models, and <company> has none set up
  yet."
- SPEC-BE-095's checks pass 27/27; ruff 1 / mypy 7.

## Amendment C (2026-10-10): the reply language — the spoken one, or the one asked for

Asked: "language is not comming bagla. instead of bangla it use hindi why. iput language will for output language or if
user ask any special then said language will be."

**Cause** (the stored message, pilotsonic1): the voice message was transcribed correctly as "Hello, what's your name?
তোমার নাম কী?", but stored as language `ur`. Two reasons:
- Bengali letters were less than half of the letters (mixed with English), so the script rule didn't apply.
- The fallback, Whisper's language guess, said Urdu, though the transcript has no Arabic-script letters. The reply was
  then spoken in Urdu, which sounds like Hindi.

**FR5 (choosing the language of what was said, `ai/speech.py`):**
- **`script_language`:** a language with its own script (Bengali, Gurmukhi, Thai, Korean…) wins when it is 3+ letters and at
  least a fifth of the letters, so mixed Bengali + English is Bengali.
- **`consistent`:** Whisper's guess is used only when the transcript fits it. A language with its own script needs letters
  of that script ("Urdu" with no Arabic letters is refused). All-Latin text is romanized speech, which keeps the guess.
- **`pick_language`:** the script; else the guess when it fits; else the first hint that fits. Two refinements:
  - All-Latin text that reads as English (common English words, `_looks_english`) is English, whatever the guess:
    "Show products low on stock" was guessed as Urdu.
  - Romanized speech guessed as a language the company doesn't use becomes the company's own non-Latin language ("Amar
    product gulo dekhao" in Bangladesh is Bengali, not Whisper's Hindi).
- **`language_hints`** (best first, at most 3):
  1. a saved brand language (the brand helper's built-in `en` default doesn't count);
  2. the national languages (official / de facto official, or 25%+) of the company timezone's country;
  3. the browser's languages (the `languages` form field, from `navigator.languages`);
  4. the national languages of the registered country;
  5. English, last.
  - **Results:** pilotsonic1 (Asia/Dhaka, registered as US) → `bn, en`; pilotsonic (Los Angeles) → `en`. US Spanish is
    only "official_regional", so it isn't a hint.
- **The hints steer transcription, never force it:** `gpt-4o-mini-transcribe` (and `whisper-1`) get a prompt: "The speaker
  may talk in Bangla or English, and may mix them. Write every word in the script of the language it was spoken in…".
  - Measured on the same recording, 3 runs each: exact with no prompt, with this hint and with a short hint (3/3 each),
    so the hint doesn't hurt accuracy.
- **Logging:** each result is logged as `voice_language_picked` (provider, detected, picked, hints), never the audio or
  the text.

**FR6 (the asked-for reply language):** `requested_language(text, spoken)` finds an explicit request:
- **Forms:** "reply/answer/speak/tell … in English", a trailing "… in English (please)", Bengali "ইংরেজিতে বলো" /
  "বাংলায় উত্তর দাও" / "ইংলিশে বলো", Hindi "हिंदी में बोलो", Urdu "اردو میں جواب دیں".
- **Names:** come from CLDR in English, Bengali, Hindi, Urdu, Arabic and the speaker's language, plus aliases (Bangla,
  Bengali, हिंदी, ইংলিশ…).
- **Content requests aren't reply requests:** a trailing "in <language>" doesn't count when the message makes content
  (write / create / post / description / listing / ad…), so "write the posts in Spanish" isn't one. "Create an English
  description" isn't one either.
- **Storage:** `send_user_message` stores it as `parsed_intent.reply_language`, and `ChatMessage.reply_language` returns
  it. The chat speaks replies in it, else in the spoken language.
- **Unchanged:** the displayed reply text (only speech is translated, with its caption), the planner, the guards and
  every other route.

**Verified (2026-10-10):**
- **Language choice:** 15 request phrases and 9 language-choice cases give the expected result (including your sentence →
  `bn`, Whisper "urdu" for English → `en`, romanized Bengali → `bn`, Arabic → `ur`).
- **Real audio** (pilotsonic1's own keys, OpenAI TTS → the transcribe route with `languages=en-US,en`, rolled back): 7/7.
  - Your mixed sentence → `bn`, exact; an English sentence → `en`; "আমার পণ্যগুলো দেখাও" → `bn`, exact.
  - "…, ইংরেজিতে বলো" → `reply_language` `en`; "… reply in Bangla" → `bn`; plain → none; it survives a reload.
- **Regressions:** SPEC-BE-095 checks 27/27; the Command Chat golden set 31/31; the browser voice test on the live app
  18/18 twice. (One run had one word blurred by Chrome's mic pipeline; the next two were exact.)
- **Baseline:** ruff 1 / mypy 7.

**Target files:** `ai/speech.py`, `api/v1/orchestrator.py` (the `languages` form field), `services/orchestrator_service.py`
(`reply_language`), `schemas/orchestrator.py`.
