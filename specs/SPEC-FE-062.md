# SPEC-FE-062: Voice commands and spoken replies in Command Chat

Status: IMPLEMENTED (2026-10-10), approved by the user (2026-10-10), with the transcript reviewed in the composer before
sending (the user's choice). `tsc` and `next build` are clean. Browser E2E (2026-10-10): headless Chrome with a fake microphone playing a Bengali command ("আমার পণ্যগুলো
দেখাও"), the real frontend + backend + live DB, pilotsonic's AI keys copied into a throwaway company (deleted afterwards,
0 rows left): **18/18 pass**. Verified: mic → waveform → stop → the
exact Bengali transcript in the composer with a "Bangla" chip (nothing sent before review) → Send → "Voice · Bangla"
badge → plan → the reply spoken with a Bengali caption → the results summary spoken next. Typed messages get no badge and
no auto-play; nothing auto-plays after a reload; Listen plays. Chrome names `bn` "Bangla" (CLDR).
- **Fixes found by the E2E:** the microphone was blocked site-wide (Amendment A); the summary interrupted the reply, so
  auto-play is now a queue (reply, then summary; fetched ahead), while Listen still interrupts. Uses SPEC-BE-095; builds on SPEC-FE-061.

## Requirements

- **FR1 (record):** a mic button in the composer. Clicking it asks for microphone access and records with
  `MediaRecorder` (Opus WebM, or MP4 on Safari). While recording, the composer becomes a voice bar: a live
  level waveform (Web Audio `AnalyserNode`), the timer, Cancel and Stop. It stops by itself after
  90 seconds. Space/Escape work as Stop/Cancel.
  - Denied microphone → "Allow the microphone in your browser to use voice commands." No `MediaRecorder` →
    the mic button is disabled with a tooltip.
- **FR2 (transcribe and send):** on stop, "Transcribing…" shows in the bar, then
  `POST /orchestrator/voice/transcribe`. The text goes into the composer for review (the user's choice,
  2026-10-10) with a "🎙 <language name>" chip and a ✕ to drop the voice mark. Send posts it with
  `voice: {language}`. The user bubble shows a "🎙 Voice · <language name>" badge (from `voice_language`, so it
  survives a reload). Plan steps still need the normal approval buttons.
  - Errors (409 setup, 422 no words, 503) show the backend's text in the bar with "Try again"; nothing is sent.
- **FR3 (spoken reply):** a "Voice replies" toggle in the header (on by default, remembered in
  `localStorage`, guarded). After a voice command, the AI reply and its later summary are spoken in the
  command's language through `POST /orchestrator/messages/{id}/speech`. The bubble shows a small player
  (play/pause, a moving level bar) and the spoken caption (`text`) when it differs from the shown
  text. Every AI bubble has a "Listen" button that speaks it in the language of the user's latest voice
  command (or as written).
  - Only one reply plays at a time. Starting a recording stops playback. Browser autoplay blocks → a "Tap to
    hear the reply" button.
  - The base64 audio becomes a Blob object URL, revoked when done.
- **FR4 (unchanged):** typed chat works exactly as before when voice isn't used.

## Acceptance criteria

- **AC1:** with dev fakes: record → transcript in the composer → Send → a Voice badge → plan card → the reply plays and its
  summary plays after the steps run.
- **AC2:** in Bengali (real keys, pilotsonic): a spoken command is planned, and the reply is spoken in Bengali
  with a Bengali caption.
- **AC3:** mic denied, no keys (409) and silence (422) each show their message, and nothing is sent.
- **AC4:** `tsc` and `next build` pass.

## Target files

`components/chat/chat-panel.tsx`, `lib/api/orchestrator.ts`, `lib/types/orchestrator.ts`,
**new** `components/chat/voice.tsx` (recorder, waveform, player). Needs approval. No new dependency.

## Amendment A (2026-10-10): the microphone was blocked site-wide

Found by the browser E2E (headless Chrome, fake microphone): "Permissions policy violation: microphone is not allowed
in this document". SPEC-FE-047 G1's `Permissions-Policy: camera=(), microphone=(), geolocation=()` turns the microphone
off for every page, so no browser could record. Changed to `microphone=(self)` in `next.config.mjs`: this site only,
never a framed or other origin (`X-Frame-Options: DENY` stays). Camera and geolocation stay off.
**Extra target file:** `frontend/next.config.mjs` (one header value). The dev server must be restarted to send it.

## Amendment B (2026-10-10): "That recording isn't a supported audio file"

Reported by the user. Cause, reproduced in Chrome: clicking the mic again while the browser was still asking for the
microphone started a second recorder writing into the same shared buffer. The saved file could then begin mid-stream (no
WebM header), so the backend refused it, or the two recordings were mixed and transcribed as gibberish ("Amamar marp po
on", labelled Hindi, instead of "আমার পণ্যগুলো দেখাও").

**Fix** (`components/chat/voice.tsx`):
- Only one recording at a time; a second click while one is starting or running is ignored.
- Each recording keeps its own buffer.
- A "Waiting for the microphone… allow it if your browser asks." bar, with Cancel, shows while the browser asks.

**Backend** (`ai/speech.py`): an unrecognised recording is logged with its first 16 bytes and the browser's stated
type (never the audio), and the message now asks the user to record again.

**Verified:** the double-click now gives the exact Bengali transcript; the voice E2E on the live app passes 18/18; and
SPEC-BE-095's checks pass 27/27.

## Amendment C (2026-10-10): replies in the spoken language, or the one asked for

Backend: SPEC-BE-095 Amendment C.
- **Hints:** `transcribeVoice` sends the browser's languages (`navigator.languages`, up to 6) as the `languages` form
  field. It's a hint for the transcriber, never a rule.
- **Reply language:** spoken replies, and the Listen button, use the language the user asked for (`reply_language`:
  "reply in English", "ইংরেজিতে বলো", "हिंदी में बोलो"), else the language they spoke (`voice_language`). Mixed Bengali +
  English is now Bengali, not Urdu.
- **Verified:** `tsc` clean; the browser voice test on the live app passes 18/18 twice with the exact Bengali transcript.
- **Target files:** `lib/api/orchestrator.ts`, `lib/types/orchestrator.ts`, `components/chat/chat-panel.tsx`.
