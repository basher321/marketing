"""Speech for Command Chat voice commands (SPEC-BE-095).

Listening (speech-to-text) and speaking (text-to-speech) on the company's own
AI Model keys, plain httpx through `base_adapter.http` (so dev_fakes can
answer it). The `.env` LLM key is never used: a company uses its own models
(SPEC-BE-088). Audio is never stored or logged.

- Listen: OpenAI -> Groq `whisper-large-v3` -> Gemini (inline audio, asked
  for JSON). OpenAI's text comes from `gpt-4o-mini-transcribe`; its language
  from the script, else `whisper-1`'s detection (Amendment A). Whisper's
  `verbose_json` names the language ("bengali"); it is mapped to ISO 639-1.
- Speak: OpenAI `gpt-4o-mini-tts` (MP3) -> Gemini TTS (24 kHz PCM, wrapped
  here as WAV).
A provider without a key is skipped; any error, timeout or 429 moves on.
"""
from __future__ import annotations

import base64
import json
import struct
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.integrations.base_adapter import PlatformError, http, short

logger = structlog.get_logger(__name__)

MAX_AUDIO_BYTES = 1_900_000  # under the 2 MB body limit; ~2 minutes of Opus
LISTEN_ORDER = ("openai", "groq", "gemini")
SPEAK_ORDER = ("openai", "gemini")
LABELS = {"openai": "OpenAI", "groq": "Groq", "gemini": "Gemini"}
OPENAI_STT_MODEL = "gpt-4o-mini-transcribe"  # the text (SPEC-BE-095 Amendment A)
OPENAI_LANGUAGE_MODEL = "whisper-1"  # only its detected language
GROQ_STT_MODEL = "whisper-large-v3"
GEMINI_DEFAULT_MODEL = "gemini-2.5-flash"
OPENAI_TTS_MODEL = "gpt-4o-mini-tts"
GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"
GEMINI_TTS_VOICE = "Kore"
GEMINI_TTS_RATE = 24_000
_GEMINI = "https://generativelanguage.googleapis.com/v1beta/models"

NO_PROVIDER_LISTEN = "Voice commands need an OpenAI, Groq or Gemini key in Integrations › AI Models."
NO_PROVIDER_SPEAK = "Voice replies need an OpenAI or Gemini key in Integrations › AI Models."
NO_WORDS = "I couldn't hear any words. Try again closer to the microphone."
BAD_AUDIO = "That recording isn't a supported audio file (WebM, Ogg, MP4/M4A, MP3 or WAV)."


class _Failed(Exception):
    """One provider failed; the chain moves on."""


def audio_type(data: bytes) -> tuple[str, str] | None:
    """(extension, mime) by magic bytes, never the file name."""
    if data[:4] == b"\x1aE\xdf\xa3":
        return "webm", "audio/webm"
    if data[:4] == b"OggS":
        return "ogg", "audio/ogg"
    if data[4:8] == b"ftyp":
        return "m4a", "audio/mp4"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav", "audio/wav"
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return "mp3", "audio/mpeg"
    return None


# Whisper's language names that differ from CLDR's English names (CLDR says
# "Bangla", Whisper says "bengali").
_WHISPER_NAMES = {
    "bengali": "bn", "castilian": "es", "flemish": "nl", "letzeburgesch": "lb", "moldavian": "ro", "moldovan": "ro",
    "myanmar": "my", "nynorsk": "nn", "panjabi": "pa", "pushto": "ps", "sinhalese": "si", "valencian": "ca",
    "haitian": "ht", "kirghiz": "ky", "maori": "mi", "cantonese": "zh",
}


def language_code(raw: object) -> str | None:
    """ISO 639-1 from a code ("bn", "en-US") or Whisper's English name ("bengali")."""
    from app.utils import locale_data

    text = str(raw or "").strip().lower().replace("_", "-")
    if not text:
        return None
    if text in _WHISPER_NAMES:
        return _WHISPER_NAMES[text]
    base = text.split("-")[0]
    names = locale_data.languages()
    if len(base) == 2 and base in names:
        return base
    for code, item in names.items():
        if len(code) == 2 and item["name"].lower() == text:
            return code
    return None


def language_name(code: str | None) -> str:
    from app.utils import locale_data

    item = locale_data.languages().get(code or "")
    return item["name"] if item else "the same language as the text"


def _key(db: Session, tenant_id: str, provider: str) -> str | None:
    from app.services.ai_model_service import provider_key

    return provider_key(db, tenant_id, provider)


def _gemini_model(db: Session, tenant_id: str) -> str:
    # The company's chosen Gemini chat model when it is a Gemini model that
    # takes audio; otherwise the documented default.
    from app.services.ai_model_service import resolve_chain

    for provider, _, model in resolve_chain(db, tenant_id):
        if provider == "gemini" and model.startswith("gemini-") and "tts" not in model and "image" not in model:
            return model
    return GEMINI_DEFAULT_MODEL


def _error(resp: Any) -> str:
    try:
        err = resp.json().get("error") or {}
        text = err.get("message") if isinstance(err, dict) else err
    except (ValueError, AttributeError):
        text = None
    return f"HTTP {resp.status_code}" + (f": {short(text, 140)}" if text else "")


def _post(url: str, **kwargs: Any) -> Any:
    try:
        resp = http("POST", url, **kwargs)
    except PlatformError as exc:
        raise _Failed(exc.message) from None
    if resp.status_code >= 400:
        raise _Failed(_error(resp))
    return resp


def _whisper(url: str, key: str, model: str, audio: bytes, ext: str, mime: str) -> tuple[str, str | None]:
    resp = _post(url, headers={"Authorization": f"Bearer {key}"}, files={"file": (f"voice.{ext}", audio, mime)},
                 data={"model": model, "response_format": "verbose_json"}, timeout=60.0)
    try:
        body = resp.json()
    except ValueError:
        raise _Failed("unreadable answer") from None
    return str(body.get("text") or ""), body.get("language")


def _gemini_text(body: Any) -> str:
    parts = ((((body or {}).get("candidates") or [{}])[0].get("content") or {}).get("parts")) or []
    return "".join(str(p.get("text") or "") for p in parts if isinstance(p, dict))


def _listen_gemini(key: str, model: str, audio: bytes, mime: str) -> tuple[str, str | None]:
    prompt = ("Transcribe this voice command exactly as spoken, in its original language and script. "
              'Reply with JSON only: {"text": "<the words>", "language": "<ISO 639-1 code>"}. '
              'If there are no spoken words, reply {"text": "", "language": null}.')
    payload = {"contents": [{"parts": [{"inline_data": {"mime_type": mime, "data": base64.b64encode(audio).decode()}},
                                       {"text": prompt}]}],
               "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}
    resp = _post(f"{_GEMINI}/{model}:generateContent", headers={"x-goog-api-key": key}, json=payload, timeout=60.0)
    try:
        data = json.loads(_gemini_text(resp.json()) or "{}")
    except ValueError:
        raise _Failed("unreadable answer") from None
    if not isinstance(data, dict):
        raise _Failed("unreadable answer")
    return str(data.get("text") or ""), data.get("language")


# Scripts used by one main language (SPEC-BE-095 Amendment A): the language of
# a transcript in one of these needs no detection. Shared scripts (Latin,
# Cyrillic, Arabic, Devanagari, Han) are left to Whisper's detection.
_SCRIPTS: tuple[tuple[int, int, str], ...] = (
    (0x0980, 0x09FF, "bn"), (0x0A00, 0x0A7F, "pa"), (0x0A80, 0x0AFF, "gu"), (0x0B80, 0x0BFF, "ta"),
    (0x0C00, 0x0C7F, "te"), (0x0C80, 0x0CFF, "kn"), (0x0D00, 0x0D7F, "ml"), (0x0D80, 0x0DFF, "si"),
    (0x0E00, 0x0E7F, "th"), (0x0E80, 0x0EFF, "lo"), (0x1780, 0x17FF, "km"), (0x1000, 0x109F, "my"),
    (0x10A0, 0x10FF, "ka"), (0x0530, 0x058F, "hy"), (0x0370, 0x03FF, "el"), (0x0590, 0x05FF, "he"),
    (0x1200, 0x137F, "am"), (0xAC00, 0xD7AF, "ko"), (0x1100, 0x11FF, "ko"), (0x3040, 0x30FF, "ja"),
)


def script_language(text: str) -> str | None:
    """The language of a one-language script when most letters are in it."""
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return None
    counts: dict[str, int] = {}
    for ch in letters:
        cp = ord(ch)
        for lo, hi, code in _SCRIPTS:
            if lo <= cp <= hi:
                counts[code] = counts.get(code, 0) + 1
                break
    if not counts:
        return None
    code, n = max(counts.items(), key=lambda kv: kv[1])
    return code if n * 2 > len(letters) else None


def _listen_openai(key: str, audio: bytes, ext: str, mime: str) -> tuple[str, str | None]:
    """Text from gpt-4o-mini-transcribe (exact on Bengali where whisper-1 wrote
    Devanagari); the language from the script, else from whisper-1, asked at
    the same time. If the accurate model fails, whisper-1's own text is used."""
    from concurrent.futures import ThreadPoolExecutor

    url = "https://api.openai.com/v1/audio/transcriptions"

    def accurate() -> str:
        resp = _post(url, headers={"Authorization": f"Bearer {key}"}, files={"file": (f"voice.{ext}", audio, mime)},
                     data={"model": OPENAI_STT_MODEL, "response_format": "json"}, timeout=60.0)
        try:
            return str(resp.json().get("text") or "")
        except ValueError:
            raise _Failed("unreadable answer") from None

    with ThreadPoolExecutor(max_workers=2) as pool:
        text_job = pool.submit(accurate)
        lang_job = pool.submit(_whisper, url, key, OPENAI_LANGUAGE_MODEL, audio, ext, mime)
        try:
            text = text_job.result()
            text_error: _Failed | None = None
        except _Failed as exc:
            text, text_error = "", exc
        try:
            whisper_text, whisper_lang = lang_job.result()
        except _Failed:
            whisper_text, whisper_lang = "", None
    if text_error is not None:
        if not whisper_text.strip():
            raise text_error
        text = whisper_text  # the accurate model failed; whisper-1 still heard it
    return text, script_language(text) or whisper_lang


def transcribe(db: Session, tenant_id: str, audio: bytes) -> dict[str, Any]:
    """{text, language, provider}; 422 bad/empty audio, 409 no key, 503 all failed."""
    if not audio:
        raise AppError("The recording is empty.", 422)
    if len(audio) > MAX_AUDIO_BYTES:
        raise AppError("The recording is too long. Keep voice commands under 2 minutes.", 422)
    kind = audio_type(audio)
    if kind is None:
        raise AppError(BAD_AUDIO, 422)
    ext, mime = kind
    chain = [(p, k) for p in LISTEN_ORDER if (k := _key(db, tenant_id, p))]
    if not chain:
        raise AppError(NO_PROVIDER_LISTEN, 409)
    failures: list[str] = []
    for provider, key in chain:
        try:
            if provider == "openai":
                text, lang = _listen_openai(key, audio, ext, mime)
            elif provider == "groq":
                text, lang = _whisper("https://api.groq.com/openai/v1/audio/transcriptions", key, GROQ_STT_MODEL, audio, ext, mime)
            else:
                text, lang = _listen_gemini(key, _gemini_model(db, tenant_id), audio, mime)
        except _Failed as exc:
            failures.append(f"{LABELS[provider]}: {exc}")
            continue
        text = " ".join(text.split())
        logger.info("voice_transcribed", tenant_id=tenant_id, provider=provider, language=lang, audio_bytes=len(audio))
        if not text:
            raise AppError(NO_WORDS, 422)
        return {"text": text, "language": language_code(lang), "provider": provider}
    logger.warning("voice_transcribe_failed", tenant_id=tenant_id, failures=failures)
    raise AppError("Voice couldn't be transcribed: " + "; ".join(failures), 503)


def _wav(pcm: bytes, rate: int = GEMINI_TTS_RATE) -> bytes:
    """16-bit mono PCM -> a WAV file."""
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
    return header + b"data" + struct.pack("<I", len(pcm)) + pcm


def _voice(db: Session, tenant_id: str) -> str:
    # The company's chosen OpenAI voice (SPEC-BE-094 settings), default alloy.
    from app.services.ai_model_service import video_audio

    try:
        return str(video_audio(db, tenant_id).get("voice") or "alloy")
    except AppError:
        return "alloy"


def speak(db: Session, tenant_id: str, text: str, language: str | None) -> dict[str, Any]:
    """{audio: bytes, mime, provider}; 409 no key, 503 all failed."""
    chain = [(p, k) for p in SPEAK_ORDER if (k := _key(db, tenant_id, p))]
    if not chain:
        raise AppError(NO_PROVIDER_SPEAK, 409)
    name = language_name(language)
    failures: list[str] = []
    for provider, key in chain:
        try:
            if provider == "openai":
                resp = _post("https://api.openai.com/v1/audio/speech", headers={"Authorization": f"Bearer {key}"},
                             json={"model": OPENAI_TTS_MODEL, "voice": _voice(db, tenant_id), "input": text,
                                   "response_format": "mp3",
                                   "instructions": f"Speak in {name}, clearly and warmly, at a natural pace."},
                             timeout=90.0)
                audio, mime = bytes(resp.content), "audio/mpeg"
            else:
                payload = {"contents": [{"parts": [{"text": f"Say in {name}, clearly and warmly: {text}"}]}],
                           "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                               "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": GEMINI_TTS_VOICE}}}}}
                resp = _post(f"{_GEMINI}/{GEMINI_TTS_MODEL}:generateContent", headers={"x-goog-api-key": key},
                             json=payload, timeout=90.0)
                parts = ((((resp.json() or {}).get("candidates") or [{}])[0].get("content") or {}).get("parts")) or []
                data = next((p["inlineData"]["data"] for p in parts if isinstance(p, dict) and p.get("inlineData")), "")
                audio, mime = _wav(base64.b64decode(data)), "audio/wav"
        except _Failed as exc:
            failures.append(f"{LABELS[provider]}: {exc}")
            continue
        except (ValueError, KeyError, TypeError):
            failures.append(f"{LABELS[provider]}: unreadable answer")
            continue
        if len(audio) < 256:
            failures.append(f"{LABELS[provider]}: no audio returned")
            continue
        logger.info("voice_spoken", tenant_id=tenant_id, provider=provider, language=language, chars=len(text))
        return {"audio": audio, "mime": mime, "provider": provider}
    logger.warning("voice_speak_failed", tenant_id=tenant_id, failures=failures)
    raise AppError("The reply couldn't be spoken: " + "; ".join(failures), 503)
