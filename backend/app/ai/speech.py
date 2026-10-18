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

NO_PROVIDER_LISTEN = "Voice commands aren't set up in PilotSonic yet: the Super admin adds an OpenAI, Groq or Gemini key."
NO_PROVIDER_SPEAK = "Voice replies aren't set up in PilotSonic yet: the Super admin adds an OpenAI or Gemini key."
NO_WORDS = "I couldn't hear any words. Try again closer to the microphone."
BAD_AUDIO = "That recording couldn't be read as audio (WebM, Ogg, MP4/M4A, MP3 or WAV). Please record again."


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


def _whose(db: Session, tenant_id: str) -> str:
    """Nothing to add since SPEC-BE-101: the AI keys are PilotSonic's, the same
    for every company (they were per company before, 2026-10-10)."""
    return ""


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
    """The language of a one-language script when it is at least a fifth of the
    letters (3+): "Hello, what's your name? তোমার নাম কী?" is Bengali, since
    Latin is shared by many languages and people mix in English words."""
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
    return code if n >= 3 and n * 5 >= len(letters) else None


# Scripts of languages written in a shared script: Whisper's guess must match
# the transcript (it once said Urdu for a Bengali + English sentence).
_SHARED_SCRIPTS: dict[str, tuple[tuple[int, int], ...]] = {
    **dict.fromkeys(("ar", "ur", "fa", "ps", "sd", "ug"), ((0x0600, 0x06FF), (0x0750, 0x077F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))),
    **dict.fromkeys(("hi", "mr", "ne", "sa"), ((0x0900, 0x097F),)),
    **dict.fromkeys(("ru", "uk", "bg", "sr", "mk", "be", "kk", "ky", "mn", "tg"), ((0x0400, 0x04FF),)),
    **dict.fromkeys(("zh",), ((0x4E00, 0x9FFF), (0x3400, 0x4DBF))),
}


def _is_latin(ch: str) -> bool:
    return ord(ch) < 0x0250


def consistent(language: str | None, text: str) -> bool:
    """Whether a detected language can be the transcript's: a language with its
    own script needs letters of that script; romanized speech (all Latin
    letters) keeps the guess."""
    if not language:
        return False
    letters = [ch for ch in text if ch.isalpha()]
    if not letters or all(_is_latin(ch) for ch in letters):
        return True
    ranges = _SHARED_SCRIPTS.get(language) or tuple((lo, hi) for lo, hi, code in _SCRIPTS if code == language)
    if ranges:
        return any(lo <= ord(ch) <= hi for ch in letters for lo, hi in ranges)
    return any(_is_latin(ch) for ch in letters)  # a Latin-script language


_EN_COMMON = frozenset(
    "the a an is are was be to of in on at for and or with my me i you your our we it this that these those what "
    "how when where who which show list create make send post posts add set update delete give tell please can "
    "do does all any new low stock product products price order orders campaign campaigns ad ads today tomorrow "
    "week day hello hi name from by about some many more less not no yes".split()
)


def _looks_english(text: str) -> bool:
    import re

    if any(ch.isalpha() and not _is_latin(ch) for ch in text):
        return False
    words = re.findall(r"[a-z']+", text.lower())
    return len(words) >= 2 and sum(w in _EN_COMMON for w in words) * 10 >= len(words) * 3


def pick_language(text: str, detected: str | None, hints: list[str]) -> str | None:
    """The transcript's language: its script, else the detector's guess when it
    fits the transcript, else the first hint that fits."""
    by_script = script_language(text)
    if by_script:
        return by_script
    guess = language_code(detected)
    if guess and guess != "en" and _SHARED_SCRIPTS.get(guess) and _looks_english(text):
        # All-Latin text that reads as English: Whisper's "urdu" for "Show products low on
        # stock" is wrong. Romanized speech ("kya haal hai") has few English words and keeps the guess.
        return "en"
    if guess and guess not in hints and _SHARED_SCRIPTS.get(guess) and text and all(_is_latin(ch) for ch in text if ch.isalpha()):
        # Romanized speech guessed as a language this company doesn't use: its own
        # non-Latin language is likelier ("Amar product gulo dekhao" in Bangladesh is Bengali).
        own = next((h for h in hints if h != "en" and (h in _SHARED_SCRIPTS or any(c == h for _, _, c in _SCRIPTS))), None)
        if own:
            return own
    if guess and consistent(guess, text):
        return guess
    return next((h for h in hints if consistent(h, text)), None)


def language_hints(db: Session, tenant_id: str, browser: list[str] | None = None) -> list[str]:
    """Languages this company's people likely speak, best first: a saved brand
    language, the main languages (official or 25%+) of its timezone's country,
    the browser's, the main languages of its registered country, and English
    last. Used to steer transcription, never to force it.

    Order matters: the sign-up country is only a browser hint (pilotsonic1 was
    registered as US but runs on Asia/Dhaka), and the brand helper's built-in
    "en" default isn't a real setting, so only a saved brand row counts."""
    import pytz  # type: ignore[import-untyped]  # no stubs installed
    from babel import languages as babel_languages
    from sqlalchemy import text as sql

    from app.models.tenant import Tenant

    out: list[str] = []

    def add(code: object) -> None:
        c = language_code(code)
        if c and c not in out:
            out.append(c)

    def main_languages(country: str) -> None:
        info = babel_languages.get_territory_language_info(country.upper())
        for code, meta in sorted(info.items(), key=lambda kv: -float(kv[1].get("population_percent") or 0)):
            # National languages only ("official_regional" Spanish in the US isn't one).
            if meta.get("official_status") in ("official", "de_facto_official") or float(meta.get("population_percent") or 0) >= 25:
                add(code)

    try:
        add(db.execute(sql("SELECT primary_language FROM brand_settings WHERE tenant_id = :t"), {"t": tenant_id}).scalar())
    except Exception:  # noqa: BLE001 - hints are best effort
        db.rollback()
    tenant = db.get(Tenant, tenant_id)
    if tenant is not None and tenant.timezone:
        for country, zones in pytz.country_timezones.items():
            if tenant.timezone in zones:
                main_languages(country)
    for b in browser or []:
        add(b)
    if tenant is not None and tenant.country_code:
        main_languages(tenant.country_code)
    add("en")
    return out[:3]


def _hint_prompt(hints: list[str]) -> str:
    if not hints:
        return ""
    names = " or ".join(language_name(h) for h in hints)
    return (f"The speaker may talk in {names}, and may mix them. Write every word in the script of the language it was "
            "spoken in (Bengali in Bengali script, Hindi in Devanagari, Urdu in Arabic script, English in Latin letters).")


# "Reply in English", "ইংরেজিতে বলো", "हिंदी में बोलो": the user asks for the
# reply language. Names come from CLDR in English and in the speaker's language.
_ALIASES = {"bengali": "bn", "bangla": "bn", "हिंदी": "hi", "बांग्ला": "bn", "बंगाली": "bn", "ইংলিশ": "en", "इंग्लिश": "en", "farsi": "fa", "mandarin": "zh", "chinese": "zh", "hindustani": "hi",
            "filipino": "tl", "tagalog": "tl", "malay": "ms", "burmese": "my"}
_CUE_EN = r"(?:reply|answer|respond|speak|talk|say|tell|explain|voice|response|replies)"


def requested_language(text: str, spoken: str | None = None) -> str | None:
    """The language the user explicitly asks to be answered in, else None."""
    import re

    from babel import Locale, UnknownLocaleError

    low = text.lower()
    names: dict[str, str] = dict(_ALIASES)
    locales = ["en", *([spoken] if spoken else []), "bn", "hi", "ur", "ar"]
    for loc in dict.fromkeys(locales):
        try:
            for code, name in Locale.parse(loc).languages.items():
                if len(code) == 2 and name and len(name) >= 3:
                    names.setdefault(name.lower(), code)
        except (UnknownLocaleError, ValueError):
            continue
    alt = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    patterns = [
        rf"{_CUE_EN}\b[^.?!]{{0,40}}?\b(?:in|into)\s+({alt})\b",          # reply (to me) in English
        rf"\b(?:in|into)\s+({alt})\s*(?:please|pls)?\s*[.!?]*\s*$",        # ... in English please
        rf"({alt})(?:য়|য|তে|ে)?\s*(?:বলো|বলুন|বল|বলবে|বলবেন|উত্তর|জবাব|কথা|লিখ|শোনাও)",  # ইংরেজিতে বলো
        rf"({alt})\s*(?:में|میں)",                                         # हिंदी में बोलो / اردو میں
    ]
    # "Write the posts in Spanish" is about the content's language, not the reply's:
    # the trailing "... in <language>" form counts only when no content is being made.
    content = re.search(r"\b(?:write|create|draft|generate|make|translate|caption|post|posts|description|listing|ad|ads|copy)\b", low)
    for n, pattern in enumerate(patterns):
        if n == 1 and content:
            continue
        m = re.search(pattern, low)
        if m:
            return names.get(m.group(1).strip())
    return None


def _listen_openai(key: str, audio: bytes, ext: str, mime: str, hints: list[str] | None = None) -> tuple[str, str | None]:
    """Text from gpt-4o-mini-transcribe (exact on Bengali where whisper-1 wrote
    Devanagari); the language from the script, else from whisper-1, asked at
    the same time. If the accurate model fails, whisper-1's own text is used."""
    from concurrent.futures import ThreadPoolExecutor

    url = "https://api.openai.com/v1/audio/transcriptions"

    def accurate() -> str:
        data = {"model": OPENAI_STT_MODEL, "response_format": "json"}
        if hints:
            data["prompt"] = _hint_prompt(hints)
        resp = _post(url, headers={"Authorization": f"Bearer {key}"}, files={"file": (f"voice.{ext}", audio, mime)},
                     data=data, timeout=60.0)
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
    return text, pick_language(text, whisper_lang, hints or [])


def transcribe(db: Session, tenant_id: str, audio: bytes, declared_type: str | None = None,
               browser_languages: list[str] | None = None) -> dict[str, Any]:
    """{text, language, provider}; 422 bad/empty audio, 409 no key, 503 all failed,
    403 AI switched off for this company (SPEC-BE-103)."""
    from app.services import platform_service

    platform_service.require(tenant_id, "ai", db)
    if not audio:
        raise AppError("The recording is empty.", 422)
    if len(audio) > MAX_AUDIO_BYTES:
        raise AppError("The recording is too long. Keep voice commands under 2 minutes.", 422)
    kind = audio_type(audio)
    if kind is None:
        # Only the first bytes and the browser's stated type are logged, never the audio.
        logger.warning("voice_audio_unrecognised", tenant_id=tenant_id, head=audio[:16].hex(), declared=declared_type,
                       audio_bytes=len(audio))
        raise AppError(BAD_AUDIO, 422)
    ext, mime = kind
    chain = [(p, k) for p in LISTEN_ORDER if (k := _key(db, tenant_id, p))]
    if not chain:
        raise AppError(NO_PROVIDER_LISTEN + _whose(db, tenant_id), 409)
    hints = language_hints(db, tenant_id, browser_languages)
    failures: list[str] = []
    for provider, key in chain:
        try:
            if provider == "openai":
                text, lang = _listen_openai(key, audio, ext, mime, hints)
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
        language = pick_language(text, lang, hints)
        logger.info("voice_language_picked", tenant_id=tenant_id, provider=provider, detected=lang, picked=language, hints=hints)
        return {"text": text, "language": language, "provider": provider}
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
    """{audio: bytes, mime, provider}; 409 no key, 503 all failed, 403 AI switched off (SPEC-BE-103)."""
    from app.services import platform_service

    platform_service.require(tenant_id, "ai", db)
    chain = [(p, k) for p in SPEAK_ORDER if (k := _key(db, tenant_id, p))]
    if not chain:
        raise AppError(NO_PROVIDER_SPEAK + _whose(db, tenant_id), 409)
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
