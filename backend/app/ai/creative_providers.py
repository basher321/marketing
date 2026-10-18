"""Creative providers (SPEC-BE-070): one interface for every source the AI Ad
Autopilot (SPEC-BE-069) can use.

Kinds: "plan", "copy", "review" (text, JSON out) and "image".
Built in:
- llm            : the company's AI model chain (SPEC-BE-053: Claude -> GPT ->
                   Gemini -> Groq in its order), all text kinds;
- openai_image   : OpenAI Images with the company's saved OpenAI key;
- gemini_image   : Gemini image generation with the company's saved Gemini key;
- catalog        : the featured products' own images (no generation, no cost).
Plus MCP creative tools the company adds (key "mcp:<id>"), for any kind.

`generate()` tries the company's order for the kind and falls back on any
provider error; it is the only place a provider is chosen. Providers only
*generate*: none of them gets ad platform credentials.

Images are never resized here (no image library is installed): each provider
is asked for its nearest native aspect ratio, the real size is read from the
file header, and an image more than 15 % off the requested ratio is refused,
so the next provider is tried.
"""
import base64
import json
import re
import struct
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.integrations.base_adapter import PlatformError, http, short

logger = structlog.get_logger(__name__)

TEXT_KINDS = ("plan", "copy", "review")
KINDS = (*TEXT_KINDS, "image", "video")
# Image models aren't constants: each company picks one per provider in AI
# Models from the provider's live list (SPEC-BE-070 amendment 2026-10-02).
# Estimated cost per generated image, in US cents, used only for the
# company's daily AI limit guard (providers don't return a price).
IMAGE_COST_CENTS = {"openai_image": 4, "gemini_image": 4}
RATIO_TOLERANCE = 0.15
MAX_IMAGE_BYTES = 30 * 1024 * 1024
DEFAULT_ORDER = {"plan": ["llm"], "copy": ["llm"], "review": ["llm"], "image": ["openai_image", "gemini_image"],
                 "video": ["gemini_video", "openai_video"]}
# Estimated video cost per generated second, US cents (daily AI limit only;
# providers don't return a price). SPEC-BE-077.
VIDEO_CENTS_PER_SECOND = {"gemini_video": 40, "openai_video": 10}


class ProviderFailed(Exception):
    """This provider couldn't produce the result; the next one is tried."""


class AllProvidersFailed(Exception):
    def __init__(self, kind: str, attempts: list[tuple[str, str]]):
        self.kind = kind
        self.attempts = attempts
        summary = "; ".join(f"{k}: {e}" for k, e in attempts) or "no provider is set up for this"
        super().__init__(f"No {kind} provider succeeded ({summary})"[:600])


@dataclass
class CreativeRequest:
    kind: str
    system: str = ""
    prompt: str = ""
    max_tokens: int = 2000
    aspect_ratio: str | None = None  # "1:1", "4:5", "9:16", "16:9", "1.91:1", "2:3"
    skus: list[str] = field(default_factory=list)
    # SPEC-BE-077: video length, style words, negative prompt, and reference
    # images [(bytes, mime)] for providers that accept them.
    duration_s: int | None = None
    style: str | None = None
    negative_prompt: str | None = None
    reference_images: list[tuple[bytes, str]] = field(default_factory=list)
    # SPEC-BE-098 FR4: this video's own sound (voiceover on/off, music_media_id,
    # voiceover_text) over the company's Sound for AI videos settings.
    audio: dict[str, Any] = field(default_factory=dict)


@dataclass
class CreativeResult:
    provider: str
    model: str
    text: str | None = None
    image: bytes | None = None
    video: bytes | None = None
    mime: str | None = None
    width: int | None = None
    height: int | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_cents: int = 0
    # Plain-language notes for the job (SPEC-BE-094: what sound was added, or why not).
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------
def ratio_value(ratio: str) -> float:
    a, b = ratio.split(":")
    return float(a) / float(b)


def image_size(data: bytes) -> tuple[str, int, int]:
    """(mime, width, height) from the PNG / JPEG / WebP header; ValueError otherwise."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        w, h = struct.unpack(">II", data[16:24])
        return "image/png", w, h
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            length = struct.unpack(">H", data[i + 2:i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return "image/jpeg", w, h
            i += 2 + length
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        chunk = data[12:16]
        if chunk == b"VP8X":
            w = 1 + int.from_bytes(data[24:27], "little")
            h = 1 + int.from_bytes(data[27:30], "little")
            return "image/webp", w, h
        if chunk == b"VP8 ":
            w, h = struct.unpack("<HH", data[26:30])
            return "image/webp", w & 0x3FFF, h & 0x3FFF
        if chunk == b"VP8L":
            bits = int.from_bytes(data[21:25], "little")
            return "image/webp", (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    raise ValueError("not a PNG, JPEG or WebP image")


def _crop_to_ratio(data: bytes, mime: str, w: int, h: int, want: float, ratio: str) -> tuple[bytes, int, int]:
    import io

    from PIL import Image

    if w / h > want:
        new_w, new_h = round(h * want), h
    else:
        new_w, new_h = w, round(w / want)
    left, top = (w - new_w) // 2, (h - new_h) // 2
    try:
        with Image.open(io.BytesIO(data)) as img:
            out = io.BytesIO()
            fmt = {"image/jpeg": "JPEG", "image/webp": "WEBP"}.get(mime, "PNG")
            img.crop((left, top, left + new_w, top + new_h)).save(out, format=fmt)
    except Exception as exc:  # noqa: BLE001 - an unreadable image is a provider failure
        raise ProviderFailed(f"image is {w}x{h} and couldn't be cropped to {ratio} ({type(exc).__name__})") from None
    return out.getvalue(), new_w, new_h


def checked_image(provider: str, model: str, data: bytes, ratio: str | None, cost: int) -> CreativeResult:
    if len(data) > MAX_IMAGE_BYTES:
        raise ProviderFailed("image larger than 30 MB")
    try:
        mime, w, h = image_size(data)
    except ValueError as exc:
        raise ProviderFailed(str(exc)) from None
    if ratio and h:
        want = ratio_value(ratio)
        if abs((w / h) - want) / want > RATIO_TOLERANCE:
            # OpenAI images come only as 1:1, 2:3 or 3:2, so 4:5 or 9:16 arrive
            # as the nearest size: centre-crop to the asked ratio, never fail.
            data, w, h = _crop_to_ratio(data, mime, w, h, want, ratio)
    return CreativeResult(provider=provider, model=model, image=data, mime=mime, width=w, height=h, cost_cents=cost)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
class LLMProvider:
    key = "llm"
    kinds = set(TEXT_KINDS)

    def available(self, db: Session, tenant_id: str) -> bool:
        return True  # the chain decides; a mock answer is refused in generate()

    def generate(self, db: Session, tenant_id: str, req: CreativeRequest) -> CreativeResult:
        from app.ai.llm_client import LLMProviderError, llm_client

        try:
            out = llm_client.complete_with_usage(req.system, req.prompt, req.max_tokens, 90.0, db=db, tenant_id=tenant_id)
        except LLMProviderError as exc:
            raise ProviderFailed(str(exc.detail if hasattr(exc, "detail") else exc)) from None
        if out.is_mock:
            raise ProviderFailed("PilotSonic's AI isn't set up yet (the Super admin adds it)")
        return CreativeResult(provider=f"llm:{out.provider}", model=out.model, text=out.text,
                              input_tokens=out.input_tokens, output_tokens=out.output_tokens)


def _saved_key(db: Session, tenant_id: str, provider: str) -> str | None:
    from app.services.ai_model_service import provider_key

    return provider_key(db, tenant_id, provider)


def _image_model(db: Session, tenant_id: str, provider: str) -> str | None:
    from app.services.ai_model_service import image_model

    return image_model(db, tenant_id, provider)


class OpenAIImageProvider:
    key = "openai_image"
    kinds = {"image"}
    SIZES = {"1:1": "1024x1024", "3:2": "1536x1024", "2:3": "1024x1536"}

    def available(self, db: Session, tenant_id: str) -> bool:
        return bool(_saved_key(db, tenant_id, "openai") and _image_model(db, tenant_id, "openai"))

    def _size(self, ratio: str | None) -> tuple[str, str]:
        want = ratio_value(ratio or "1:1")
        best = min(self.SIZES, key=lambda r: abs(ratio_value(r) - want))
        return best, self.SIZES[best]

    def generate(self, db: Session, tenant_id: str, req: CreativeRequest) -> CreativeResult:
        key = _saved_key(db, tenant_id, "openai")
        model = _image_model(db, tenant_id, "openai")
        if not key:
            raise ProviderFailed("no OpenAI key saved")
        if not model:
            raise ProviderFailed("no OpenAI image model chosen")
        _, size = self._size(req.aspect_ratio)
        try:
            if req.reference_images:
                # Reference / product photos (SPEC-BE-077): the edits endpoint
                # takes them as image[] files with the prompt.
                files = [("image[]", (f"ref{i}.{m.split('/')[-1]}", data, m)) for i, (data, m) in enumerate(req.reference_images[:4])]
                resp = http("POST", "https://api.openai.com/v1/images/edits", headers={"Authorization": f"Bearer {key}"},
                            data={"model": model, "prompt": req.prompt[:4000], "size": size, "n": "1"}, files=files, timeout=180.0)
            else:
                resp = http("POST", "https://api.openai.com/v1/images/generations", headers={"Authorization": f"Bearer {key}"},
                            json={"model": model, "prompt": req.prompt[:4000], "size": size, "n": 1}, timeout=180.0)
        except PlatformError as exc:
            raise ProviderFailed(exc.message) from None
        if resp.status_code >= 400:
            raise ProviderFailed(f"HTTP {resp.status_code}: {short((resp.json().get('error') or {}).get('message') if resp.content else '')}")
        item = ((resp.json().get("data") or [{}])[0]) or {}
        if not item.get("b64_json"):
            raise ProviderFailed("OpenAI returned no image")
        return checked_image(self.key, model, base64.b64decode(item["b64_json"]), req.aspect_ratio, IMAGE_COST_CENTS[self.key])


class GeminiImageProvider:
    key = "gemini_image"
    kinds = {"image"}
    RATIOS = ("1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9")

    def available(self, db: Session, tenant_id: str) -> bool:
        return bool(_saved_key(db, tenant_id, "gemini") and _image_model(db, tenant_id, "gemini"))

    def generate(self, db: Session, tenant_id: str, req: CreativeRequest) -> CreativeResult:
        key = _saved_key(db, tenant_id, "gemini")
        model = _image_model(db, tenant_id, "gemini")
        if not key:
            raise ProviderFailed("no Gemini key saved")
        if not model:
            raise ProviderFailed("no Gemini image model chosen")
        want = ratio_value(req.aspect_ratio or "1:1")
        ratio = min(self.RATIOS, key=lambda r: abs(ratio_value(r) - want))
        parts: list[dict[str, Any]] = [{"inlineData": {"mimeType": m, "data": base64.b64encode(data).decode()}} for data, m in req.reference_images[:3]]
        parts.append({"text": req.prompt[:4000]})
        try:
            resp = http("POST", f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                        headers={"x-goog-api-key": key},
                        json={"contents": [{"parts": parts}],
                              "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": ratio}}}, timeout=180.0)
        except PlatformError as exc:
            raise ProviderFailed(exc.message) from None
        if resp.status_code >= 400:
            raise ProviderFailed(f"HTTP {resp.status_code}: {short((resp.json().get('error') or {}).get('message') if resp.content else '')}")
        for cand in resp.json().get("candidates") or []:
            for part in (cand.get("content") or {}).get("parts") or []:
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    return checked_image(self.key, model, base64.b64decode(inline["data"]), req.aspect_ratio, IMAGE_COST_CENTS[self.key])
        raise ProviderFailed("Gemini returned no image (it may have refused the prompt)")


class CatalogImageProvider:
    """The featured products' own images, first one that fits the ratio."""

    key = "catalog"
    kinds = {"image"}

    def available(self, db: Session, tenant_id: str) -> bool:
        return True

    def generate(self, db: Session, tenant_id: str, req: CreativeRequest) -> CreativeResult:
        from sqlalchemy import text

        from app.integrations import verify

        urls: list[str] = []
        for (images,) in db.execute(
            text("SELECT images FROM products WHERE tenant_id = :t AND sku = ANY(:s) AND deleted_at IS NULL"),
            {"t": tenant_id, "s": list(req.skus) or [""]},
        ).all():
            for img in images or []:
                url = img if isinstance(img, str) else (img or {}).get("url") or (img or {}).get("src")
                if isinstance(url, str) and url.startswith("https://"):
                    urls.append(url)
        last = "the featured products have no https images"
        for url in urls:
            try:
                host = re.sub(r"^https://([^/:]+).*$", r"\1", url)
                verify._require_public_host(host)
                resp = http("GET", url, timeout=60.0)
                if resp.status_code >= 400:
                    raise ProviderFailed(f"HTTP {resp.status_code}")
                return checked_image(self.key, "catalog", resp.content, req.aspect_ratio, 0)
            except (ProviderFailed, PlatformError, verify.VerifyError) as exc:
                last = str(exc)
        raise ProviderFailed(last)


# ---------------------------------------------------------------------------
# Video providers (SPEC-BE-077). Video is slow, so these are asynchronous:
#   supported(req) -> {"duration_s", "aspect_ratio"}: what will really be made
#   start(db, tenant_id, req) -> provider job ref (str), or a finished
#                                CreativeResult for synchronous tools
#   poll(db, tenant_id, ref)  -> None while running, CreativeResult when done
# ProviderFailed on start lets the next provider try; a failure after start
# is the job's error. Durations are the provider's own (no stitching).
# Checked against the providers' docs on 2026-10-03:
#   Veo (Gemini API): POST models/{model}:predictLongRunning, 4/6/8 s,
#     16:9 or 9:16, 8 s with reference images; poll GET v1beta/{operation};
#     download response.generateVideoResponse.generatedSamples[0].video.uri.
#   Sora (OpenAI): POST /v1/videos {model, prompt, seconds "4"|"8"|"12", size};
#     GET /v1/videos/{id} queued|in_progress|completed|failed;
#     GET /v1/videos/{id}/content -> MP4.
# ---------------------------------------------------------------------------
def nearest(value: float, options: tuple[Any, ...]) -> Any:
    return min(options, key=lambda o: (abs(float(o) - value), -float(o)))


def nearest_ratio(ratio: str | None, options: tuple[str, ...]) -> str:
    want = ratio_value(ratio or options[0])
    return min(options, key=lambda r: abs(ratio_value(r) - want))


def _video_model(db: Session, tenant_id: str, provider: str) -> str | None:
    from app.services.ai_model_service import video_model

    return video_model(db, tenant_id, provider)


def _video_result(provider: str, model: str, data: bytes, seconds: int) -> CreativeResult:
    if len(data) > 1024 * 1024 * 1024:
        raise ProviderFailed("video larger than 1 GB")
    if data[4:8] != b"ftyp" and data[4:8] not in (b"moov", b"mdat", b"wide", b"free"):
        raise ProviderFailed("the provider didn't return an MP4/MOV video")
    return CreativeResult(provider=provider, model=model, video=data, mime="video/mp4",
                          cost_cents=VIDEO_CENTS_PER_SECOND.get(provider, 0) * seconds)


def _error_message(resp: Any) -> str:
    try:
        err = resp.json().get("error") or {}
        return short(err.get("message") if isinstance(err, dict) else err)
    except ValueError:
        return f"HTTP {resp.status_code}"


class GeminiVideoProvider:
    key = "gemini_video"
    kinds = {"video"}
    DURATIONS = (4, 6, 8)
    RATIOS = ("16:9", "9:16")
    BASE = "https://generativelanguage.googleapis.com/v1beta"

    def available(self, db: Session, tenant_id: str) -> bool:
        return bool(_saved_key(db, tenant_id, "gemini") and _video_model(db, tenant_id, "gemini"))

    def supported(self, req: CreativeRequest) -> dict[str, Any]:
        seconds = 8 if req.reference_images else nearest(float(req.duration_s or 8), self.DURATIONS)
        return {"duration_s": seconds, "aspect_ratio": nearest_ratio(req.aspect_ratio, self.RATIOS)}

    def start(self, db: Session, tenant_id: str, req: CreativeRequest) -> str | CreativeResult:
        key, model = _saved_key(db, tenant_id, "gemini"), _video_model(db, tenant_id, "gemini")
        if not key or not model:
            raise ProviderFailed("no Gemini key or video model chosen")
        eff = self.supported(req)
        instance: dict[str, Any] = {"prompt": (req.prompt + (f" Style: {req.style}." if req.style else ""))[:4000]}
        if req.reference_images:
            instance["referenceImages"] = [{"image": {"inlineData": {"mimeType": m, "data": base64.b64encode(d).decode()}}, "referenceType": "asset"}
                                           for d, m in req.reference_images[:3]]
        params: dict[str, Any] = {"aspectRatio": eff["aspect_ratio"], "durationSeconds": eff["duration_s"]}
        if req.negative_prompt:
            params["negativePrompt"] = req.negative_prompt[:1000]
        try:
            resp = http("POST", f"{self.BASE}/models/{model}:predictLongRunning", headers={"x-goog-api-key": key},
                        json={"instances": [instance], "parameters": params}, timeout=60.0)
        except PlatformError as exc:
            raise ProviderFailed(exc.message) from None
        if resp.status_code >= 400:
            raise ProviderFailed(f"HTTP {resp.status_code}: {_error_message(resp)}")
        name = resp.json().get("name")
        if not name:
            raise ProviderFailed("Gemini returned no operation")
        return json.dumps({"op": name, "model": model, "seconds": eff["duration_s"]})

    def poll(self, db: Session, tenant_id: str, ref: str) -> CreativeResult | None:
        info = json.loads(ref)
        key = _saved_key(db, tenant_id, "gemini")
        if not key:
            raise ProviderFailed("the Gemini key was removed")
        try:
            resp = http("GET", f"{self.BASE}/{info['op']}", headers={"x-goog-api-key": key}, timeout=30.0)
        except PlatformError as exc:
            raise ProviderFailed(exc.message) from None
        if resp.status_code >= 400:
            raise ProviderFailed(f"HTTP {resp.status_code}: {_error_message(resp)}")
        body = resp.json()
        if not body.get("done"):
            return None
        if body.get("error"):
            raise ProviderFailed(short((body["error"] or {}).get("message") or "Veo failed"))
        samples = (((body.get("response") or {}).get("generateVideoResponse") or {}).get("generatedSamples") or [])
        uri = ((samples[0] if samples else {}).get("video") or {}).get("uri")
        if not uri:
            raise ProviderFailed("Veo finished without a video (it may have refused the prompt)")
        try:
            video = http("GET", uri, headers={"x-goog-api-key": key}, timeout=600.0, follow_redirects=True)
        except PlatformError as exc:
            raise ProviderFailed(exc.message) from None
        if video.status_code >= 400:
            raise ProviderFailed(f"Couldn't download the video (HTTP {video.status_code})")
        return _video_result(self.key, info["model"], video.content, int(info["seconds"]))


class OpenAIVideoProvider:
    key = "openai_video"
    kinds = {"video"}
    DURATIONS = (4, 8, 12)
    SIZES = {"16:9": "1280x720", "9:16": "720x1280"}
    BASE = "https://api.openai.com/v1/videos"

    def available(self, db: Session, tenant_id: str) -> bool:
        return bool(_saved_key(db, tenant_id, "openai") and _video_model(db, tenant_id, "openai"))

    def supported(self, req: CreativeRequest) -> dict[str, Any]:
        return {"duration_s": nearest(float(req.duration_s or 8), self.DURATIONS),
                "aspect_ratio": nearest_ratio(req.aspect_ratio, tuple(self.SIZES))}

    def start(self, db: Session, tenant_id: str, req: CreativeRequest) -> str | CreativeResult:
        key, model = _saved_key(db, tenant_id, "openai"), _video_model(db, tenant_id, "openai")
        if not key or not model:
            raise ProviderFailed("no OpenAI key or video model chosen")
        eff = self.supported(req)
        size = self.SIZES[eff["aspect_ratio"]]
        prompt = (req.prompt + (f" Style: {req.style}." if req.style else ""))[:4000]
        try:
            if req.reference_images:
                ref = _fit_reference(req.reference_images[0][0], size)
                resp = http("POST", self.BASE, headers={"Authorization": f"Bearer {key}"},
                            data={"model": model, "prompt": prompt, "seconds": str(eff["duration_s"]), "size": size},
                            files={"input_reference": ("reference.png", ref, "image/png")}, timeout=60.0)
            else:
                resp = http("POST", self.BASE, headers={"Authorization": f"Bearer {key}"},
                            json={"model": model, "prompt": prompt, "seconds": str(eff["duration_s"]), "size": size}, timeout=60.0)
        except PlatformError as exc:
            raise ProviderFailed(exc.message) from None
        if resp.status_code >= 400:
            raise ProviderFailed(f"HTTP {resp.status_code}: {_error_message(resp)}")
        vid = resp.json().get("id")
        if not vid:
            raise ProviderFailed("OpenAI returned no video id")
        return json.dumps({"id": vid, "model": model, "seconds": eff["duration_s"]})

    def poll(self, db: Session, tenant_id: str, ref: str) -> CreativeResult | None:
        info = json.loads(ref)
        key = _saved_key(db, tenant_id, "openai")
        if not key:
            raise ProviderFailed("the OpenAI key was removed")
        headers = {"Authorization": f"Bearer {key}"}
        try:
            resp = http("GET", f"{self.BASE}/{info['id']}", headers=headers, timeout=30.0)
        except PlatformError as exc:
            raise ProviderFailed(exc.message) from None
        if resp.status_code >= 400:
            raise ProviderFailed(f"HTTP {resp.status_code}: {_error_message(resp)}")
        body = resp.json()
        status = body.get("status")
        if status == "failed":
            raise ProviderFailed(short(((body.get("error") or {}).get("message")) or "Sora failed"))
        if status != "completed":
            return None
        try:
            video = http("GET", f"{self.BASE}/{info['id']}/content", headers=headers, timeout=600.0, follow_redirects=True)
        except PlatformError as exc:
            raise ProviderFailed(exc.message) from None
        if video.status_code >= 400:
            raise ProviderFailed(f"Couldn't download the video (HTTP {video.status_code})")
        return _video_result(self.key, info["model"], video.content, int(info["seconds"]))


def _fit_reference(data: bytes, size: str) -> bytes:
    """Sora's input_reference must match the video size: centre-crop + resize."""
    import io

    from PIL import Image

    w, h = (int(x) for x in size.split("x"))
    img = Image.open(io.BytesIO(data)).convert("RGB")
    scale = max(w / img.width, h / img.height)
    img = img.resize((max(w, int(img.width * scale)), max(h, int(img.height * scale))))
    left, top = (img.width - w) // 2, (img.height - h) // 2
    out = io.BytesIO()
    img.crop((left, top, left + w, top + h)).save(out, format="PNG")
    return out.getvalue()


class MCPProvider:
    """A company's MCP creative tool (Integrations › AI Models › Creative tools)."""

    def __init__(self, tool_id: str, config: dict[str, Any], token: str | None):
        self.key = f"mcp:{tool_id}"
        self.config = config
        self.token = token
        self.kinds = {k for k, v in (config.get("tools") or {}).items() if v}

    def available(self, db: Session, tenant_id: str) -> bool:
        return bool(self.config.get("enabled", True) and self.kinds)

    # Video through MCP (SPEC-BE-077) is synchronous: the tool returns the
    # finished video, so start() hands back the result itself.
    def supported(self, req: CreativeRequest) -> dict[str, Any]:
        return {"duration_s": int(req.duration_s or 8), "aspect_ratio": req.aspect_ratio or "9:16"}

    def start(self, db: Session, tenant_id: str, req: CreativeRequest) -> str | CreativeResult:
        return self.generate(db, tenant_id, req)

    def poll(self, db: Session, tenant_id: str, ref: str) -> CreativeResult | None:
        raise ProviderFailed("MCP video tools answer synchronously; nothing to poll")

    def _arguments(self, kind: str, req: CreativeRequest) -> dict[str, Any]:
        template = (self.config.get("arguments") or {}).get(kind) or {"prompt": "{prompt}"}
        values = {"prompt": req.prompt, "system": req.system, "aspect_ratio": req.aspect_ratio or "1:1",
                  "duration_s": req.duration_s or 8, "style": req.style or ""}

        def fill(v: Any) -> Any:
            if isinstance(v, str):
                for name, val in values.items():
                    if v == "{" + name + "}":
                        return val
                    v = v.replace("{" + name + "}", str(val))
                return v
            if isinstance(v, dict):
                return {k: fill(x) for k, x in v.items()}
            if isinstance(v, list):
                return [fill(x) for x in v]
            return v

        return dict(fill(template))

    def generate(self, db: Session, tenant_id: str, req: CreativeRequest) -> CreativeResult:
        from app.integrations import mcp_client

        tool = (self.config.get("tools") or {}).get(req.kind)
        if not tool:
            raise ProviderFailed(f"no tool mapped for {req.kind}")
        try:
            session = mcp_client.MCPSession(self.config.get("url", ""), self.token)
            session.initialize()
            result = session.call_tool(tool, self._arguments(req.kind, req))
            if req.kind == "image":
                data, _mime = mcp_client.first_image(result)
                return checked_image(self.key, tool, data, req.aspect_ratio, int(self.config.get("cost_cents_per_call") or 0))
            if req.kind == "video":
                data, _mime = mcp_client.first_video(result)
                video = _video_result(self.key, tool, data, 0)
                video.cost_cents = int(self.config.get("cost_cents_per_call") or 0)
                return video
            return CreativeResult(provider=self.key, model=tool, text=json.dumps(mcp_client.first_json(result)),
                                  cost_cents=int(self.config.get("cost_cents_per_call") or 0))
        except PlatformError as exc:
            raise ProviderFailed(exc.message) from None


# ---------------------------------------------------------------------------
# OpenAI slideshow video (SPEC-BE-093). OpenAI shut down its Sora Videos API
# on 2026-09-24 and has no other video model, so Command Chat's OpenAI video
# is a slideshow: n images from the company's OpenAI image model, each with a
# slow zoom, joined with 0.5 s crossfades by the bundled ffmpeg
# (imageio-ffmpeg). Synchronous: start() returns the finished result. Not
# real motion video, and the summary says so.
# ---------------------------------------------------------------------------
class OpenAISlideshowProvider:
    key = "openai_slideshow"
    kinds = {"video"}
    MIN_S, MAX_S = 4, 30
    FPS = 30
    FADE_S = 0.5
    # output size, and the OpenAI image ratio the frames are made at
    SHAPES = {"9:16": ((720, 1280), "2:3"), "16:9": ((1280, 720), "3:2"), "1:1": ((1080, 1080), "1:1")}
    SHOTS = ("wide establishing shot", "close-up detail shot", "the same subject from a different angle",
             "lifestyle shot of it in use", "dramatic hero shot with soft background blur", "final shot, clean composition")

    def available(self, db: Session, tenant_id: str) -> bool:
        return bool(_saved_key(db, tenant_id, "openai") and _image_model(db, tenant_id, "openai"))

    def supported(self, req: CreativeRequest) -> dict[str, Any]:
        seconds = min(self.MAX_S, max(self.MIN_S, int(req.duration_s or 8)))
        ratio = req.aspect_ratio if req.aspect_ratio in self.SHAPES else "1:1"
        return {"duration_s": seconds, "aspect_ratio": ratio}

    def frames(self, seconds: int) -> int:
        return min(6, max(2, -(-seconds // 3)))

    def start(self, db: Session, tenant_id: str, req: CreativeRequest) -> str | CreativeResult:
        return self.generate(db, tenant_id, req)

    def poll(self, db: Session, tenant_id: str, ref: str) -> CreativeResult | None:
        raise ProviderFailed("the slideshow finishes when it starts")

    def generate(self, db: Session, tenant_id: str, req: CreativeRequest) -> CreativeResult:
        eff = self.supported(req)
        seconds, (size, image_ratio) = eff["duration_s"], self.SHAPES[eff["aspect_ratio"]]
        n = self.frames(seconds)
        images: list[bytes] = []
        model, cost = "", 0
        for i in range(n):
            prompt = f"{req.prompt} — {self.SHOTS[i % len(self.SHOTS)]}." + (f" Style: {req.style}." if req.style else "")
            shot = OPENAI_IMAGE.generate(db, tenant_id, CreativeRequest(kind="image", prompt=prompt, aspect_ratio=image_ratio,
                                                                         reference_images=req.reference_images))
            images.append(shot.image or b"")
            model, cost = shot.model, cost + shot.cost_cents
        data = self._encode(images, size, seconds)
        data, notes, audio_cost = self._with_sound(db, tenant_id, req, data, seconds)
        result = _video_result(self.key, f"{model} slideshow ({n} images)", data, 0)
        result.width, result.height, result.cost_cents, result.notes = size[0], size[1], cost + audio_cost, notes
        return result

    # --- Sound (SPEC-BE-094): an AI voiceover and/or the company's music ---
    TTS_MODEL = "gpt-4o-mini-tts"
    WORDS_PER_SECOND = 2.3
    VOICE_CENTS = 1

    def _with_sound(self, db: Session, tenant_id: str, req: CreativeRequest, video: bytes, seconds: int) -> tuple[bytes, list[str], int]:
        """Adds sound when the company set any up; a failure never fails the
        video, it keeps what still works and says why in the notes."""
        from app.services.ai_model_service import video_audio

        cfg = video_audio(db, tenant_id)
        if req.audio.get("voiceover") is not None:
            cfg["voiceover"] = bool(req.audio["voiceover"])
        if req.audio.get("voiceover_text"):
            cfg["voiceover"] = True
        if req.audio.get("music_media_id"):
            cfg["music_media_id"] = str(req.audio["music_media_id"])
            cfg["music"] = {"name": "the chosen track"}
        notes: list[str] = []
        voice: bytes | None = None
        music: bytes | None = None
        cost = 0
        if cfg.get("voiceover"):
            try:
                voice = self._voiceover(db, tenant_id, req, seconds, str(cfg.get("voice") or "alloy"))
                cost += self.VOICE_CENTS
                notes.append(f"Voiceover added ({cfg.get('voice')}).")
            except ProviderFailed as exc:
                notes.append(f"No voiceover: {exc}")
        if cfg.get("music"):
            try:
                music = self._music(db, tenant_id, str(cfg["music_media_id"]))
                notes.append(f"Background music: {cfg['music'].get('name') or 'your track'}.")
            except ProviderFailed as exc:
                notes.append(f"No background music: {exc}")
        if voice is None and music is None:
            if not cfg.get("voiceover") and not cfg.get("music"):
                notes.append("No sound: turn on the voiceover or add background music in Integrations › AI Models › Sound for AI videos.")
            return video, notes, cost
        try:
            return self._mix(video, voice, music, seconds, float(cfg.get("music_volume") or 0.25)), notes, cost
        except ProviderFailed as exc:
            return video, [*notes, f"Sound couldn't be added: {exc}"], 0

    def _voiceover(self, db: Session, tenant_id: str, req: CreativeRequest, seconds: int, voice: str) -> bytes:
        from app.ai.llm_client import LLMProviderError, llm_client
        from app.ai.retrieval import get_brand_voice

        brand = get_brand_voice(db, tenant_id)
        words = max(4, int(self.WORDS_PER_SECOND * (seconds - 1)))
        if req.audio.get("voiceover_text"):  # the user's own words (SPEC-BE-098 FR4), trimmed to fit
            script = " ".join(str(req.audio["voiceover_text"]).split()[: words + 3])
            return self._speak(db, tenant_id, script, voice)
        system = ("You write voiceover scripts for short social media video ads. Reply with the spoken words only: "
                  "no quotes, labels, hashtags, emojis, stage directions or URLs.")
        user = (f"Video: {req.prompt[:1500]}\nBrand: {brand.brand_name or 'the brand'}\n"
                f"Language (ISO code): {brand.primary_language or 'en'}\n"
                f"Write one natural, upbeat spoken script of at most {words} words that fits {seconds} seconds.")
        try:
            out = llm_client.complete_with_usage(system, user, 300, 60.0, db=db, tenant_id=tenant_id)
        except LLMProviderError as exc:
            raise ProviderFailed(f"the AI couldn't write the script ({short(str(exc), 120)})") from None
        script = " ".join(out.text.replace('"', "").split())
        script = " ".join(script.split()[: words + 3])
        if len(script) < 3:
            raise ProviderFailed("the AI returned an empty script")
        return self._speak(db, tenant_id, script, voice)

    def _speak(self, db: Session, tenant_id: str, script: str, voice: str) -> bytes:
        key = _saved_key(db, tenant_id, "openai")
        if not key:
            raise ProviderFailed("no OpenAI key saved (needed for the voice)")
        try:
            resp = http("POST", "https://api.openai.com/v1/audio/speech", headers={"Authorization": f"Bearer {key}"},
                        json={"model": self.TTS_MODEL, "voice": voice, "input": script, "response_format": "mp3",
                              "instructions": "Warm, confident, upbeat advertising voice. Natural pace."}, timeout=120.0)
        except PlatformError as exc:
            raise ProviderFailed(f"OpenAI voice: {exc.message}") from None
        if resp.status_code >= 400:
            raise ProviderFailed(f"OpenAI voice: HTTP {resp.status_code}: {_error_message(resp)}")
        if len(resp.content) < 256:
            raise ProviderFailed("OpenAI returned no audio")
        return bytes(resp.content)

    def _music(self, db: Session, tenant_id: str, media_id: str) -> bytes:
        from app.integrations.storage import get_storage
        from app.services import media_service

        try:
            asset = media_service.media_rows(db, tenant_id, [media_id], kinds=("audio",))[0]
            return bytes(get_storage().get(asset.storage_key))
        except Exception as exc:  # noqa: BLE001 - the video still goes out without music
            raise ProviderFailed(f"the music file couldn't be read ({short(str(getattr(exc, 'detail', exc)), 100)})") from None

    def _mix(self, video: bytes, voice: bytes | None, music: bytes | None, seconds: int, volume: float) -> bytes:
        """Two ffmpeg runs: mix the audio to a WAV of exactly `seconds`, then
        mux it with the video (copied, not re-encoded). One combined run
        (video input + amix + -t) produced only ~0.06 s of audio."""
        import subprocess
        import tempfile
        from pathlib import Path

        from app.services.media_service import audio_duration_ms

        try:
            import imageio_ffmpeg  # type: ignore[import-untyped]  # no stubs published

            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError, RuntimeError) as exc:
            raise ProviderFailed(f"ffmpeg isn't available ({exc})") from None

        def run(args: list[str]) -> None:
            try:
                done = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *args],  # noqa: S603 - fixed binary, no shell
                                      capture_output=True, timeout=300, check=False)
            except subprocess.TimeoutExpired:
                raise ProviderFailed("ffmpeg timed out adding sound") from None
            if done.returncode != 0:
                raise ProviderFailed(f"ffmpeg: {short(done.stderr.decode(errors='replace'), 160)}")

        with tempfile.TemporaryDirectory() as tmp:
            args: list[str] = []
            chains: list[str] = []
            labels: list[str] = []
            index = 0
            if voice is not None:
                (Path(tmp) / "voice.mp3").write_bytes(voice)
                args += ["-i", str(Path(tmp) / "voice.mp3")]
                spoken = (audio_duration_ms(voice) or 0) / 1000
                room = max(1.0, seconds - 0.6)
                tempo = min(1.3, spoken / room) if spoken > room else 1.0  # speed up a long read, then trim
                # Each chain is exactly `seconds` long (apad / aloop + atrim).
                chains.append(f"[{index}:a]aresample=48000,atempo={tempo:.3f},adelay=300:all=1,apad,atrim=0:{seconds},"
                              f"afade=t=out:st={max(0.0, seconds - 0.5):.2f}:d=0.5[vo]")
                labels.append("[vo]")
                index += 1
            if music is not None:
                (Path(tmp) / "music.bin").write_bytes(music)
                args += ["-i", str(Path(tmp) / "music.bin")]
                level = volume if voice is not None else min(1.0, volume * 2)  # quieter under a voice
                chains.append(f"[{index}:a]aresample=48000,aloop=loop=-1:size=2147483647,atrim=0:{seconds},asetpts=N/SR/TB,"
                              f"volume={level:.2f},afade=t=in:d=0.5,afade=t=out:st={max(0.0, seconds - 1.2):.2f}:d=1.2[mu]")
                labels.append("[mu]")
            if len(labels) == 2:
                chains.append("[vo][mu]amix=inputs=2:duration=first:normalize=0[a]")
                out_label = "[a]"
            else:
                out_label = labels[0]
            mix = Path(tmp) / "mix.wav"
            run([*args, "-filter_complex", ";".join(chains), "-map", out_label, "-ar", "48000", "-ac", "2", str(mix)])
            (Path(tmp) / "v.mp4").write_bytes(video)
            out = Path(tmp) / "out.mp4"
            run(["-i", str(Path(tmp) / "v.mp4"), "-i", str(mix), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                 "-c:a", "aac", "-b:a", "128k", "-t", str(seconds), "-movflags", "+faststart", str(out)])
            if not out.exists():
                raise ProviderFailed("ffmpeg produced no file")
            return out.read_bytes()

    def _encode(self, images: list[bytes], size: tuple[int, int], seconds: int) -> bytes:
        import subprocess
        import tempfile
        from pathlib import Path

        try:
            import imageio_ffmpeg  # type: ignore[import-untyped]  # no stubs published

            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError, RuntimeError) as exc:
            raise ProviderFailed(f"ffmpeg isn't available ({exc})") from None
        w, h = size
        n = len(images)
        seg = (seconds + (n - 1) * self.FADE_S) / n  # each clip, so the crossfaded total = seconds
        frames = round(seg * self.FPS)
        with tempfile.TemporaryDirectory() as tmp:
            args = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
            for i, img in enumerate(images):
                path = Path(tmp) / f"f{i}.img"
                path.write_bytes(img)
                args += ["-i", str(path)]
            parts = []
            for i in range(n):
                # Upscale 2x before zoompan so the slow zoom doesn't judder; odd clips drift sideways.
                x = "iw/2-(iw/zoom/2)" if i % 2 == 0 else f"(iw-iw/zoom)*on/{frames}"
                parts.append(f"[{i}:v]scale={2 * w}:{2 * h}:force_original_aspect_ratio=increase,crop={2 * w}:{2 * h},"
                             f"zoompan=z='min(zoom+0.0010,1.15)':x='{x}':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h}:fps={self.FPS},"
                             f"setsar=1,format=yuv420p[v{i}]")
            last = "v0"
            for i in range(1, n):
                offset = i * (seg - self.FADE_S)
                parts.append(f"[{last}][v{i}]xfade=transition=fade:duration={self.FADE_S}:offset={offset:.3f}[x{i}]")
                last = f"x{i}"
            out = Path(tmp) / "out.mp4"
            args += ["-filter_complex", ";".join(parts), "-map", f"[{last}]", "-t", str(seconds), "-r", str(self.FPS),
                     "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(out)]
            try:
                done = subprocess.run(args, capture_output=True, timeout=300, check=False)  # noqa: S603 - fixed binary, no shell
            except subprocess.TimeoutExpired:
                raise ProviderFailed("ffmpeg timed out after 5 minutes") from None
            if done.returncode != 0 or not out.exists():
                raise ProviderFailed(f"ffmpeg failed: {short(done.stderr.decode(errors='replace'), 200)}")
            return out.read_bytes()


OPENAI_IMAGE = OpenAIImageProvider()
BUILT_IN: dict[str, Any] = {p.key: p for p in (LLMProvider(), OPENAI_IMAGE, GeminiImageProvider(), CatalogImageProvider(),
                                                GeminiVideoProvider(), OpenAIVideoProvider())}
# Providers only Command Chat pins (SPEC-BE-093): not in the creative order
# setting, readiness lists or the Organic pages.
CHAT_ONLY: dict[str, Any] = {p.key: p for p in (OpenAISlideshowProvider(),)}


def provider(key: str) -> Any:
    """A built-in or chat-only provider by key (None if unknown)."""
    return BUILT_IN.get(key) or CHAT_ONLY.get(key)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
def creative_settings(db: Session, tenant_id: str) -> dict[str, Any]:
    from app.models.tenant import Tenant

    tenant = db.get(Tenant, tenant_id)
    return dict(((tenant.settings or {}) if tenant else {}).get("creative") or {})


def mcp_providers(db: Session, tenant_id: str) -> dict[str, MCPProvider]:
    from cryptography.fernet import InvalidToken

    from app.utils.crypto import decrypt_secret

    out: dict[str, MCPProvider] = {}
    for tool_id, cfg in (creative_settings(db, tenant_id).get("mcp_tools") or {}).items():
        token = None
        if cfg.get("token_enc"):
            try:
                token = decrypt_secret(cfg["token_enc"])
            except (InvalidToken, ValueError):
                token = None
        out[f"mcp:{tool_id}"] = MCPProvider(tool_id, cfg, token)
    return out


def ordered(db: Session, tenant_id: str, kind: str) -> list[Any]:
    """The company's providers for a kind, in its order; MCP tools that
    handle the kind but aren't in the order are tried last."""
    settings = creative_settings(db, tenant_id)
    mcps = mcp_providers(db, tenant_id)
    order = list((settings.get("order") or {}).get(kind) or DEFAULT_ORDER[kind])
    order += [k for k, p in mcps.items() if kind in p.kinds and k not in order]
    found = []
    for key in order:
        provider = BUILT_IN.get(key) or mcps.get(key)
        if provider is not None and kind in provider.kinds and key != "catalog":
            found.append(provider)
    return found


def generate(db: Session, tenant_id: str, req: CreativeRequest, providers: list[Any] | None = None) -> CreativeResult:
    from app.services import platform_service

    if not platform_service.allowed(tenant_id, "ai", db):  # SPEC-BE-103: also covers jobs already queued
        raise AllProvidersFailed(req.kind, [("pilotsonic", platform_service.BLOCKED["ai"])])
    attempts: list[tuple[str, str]] = []
    for provider in providers if providers is not None else ordered(db, tenant_id, req.kind):
        if not provider.available(db, tenant_id):
            attempts.append((provider.key, "not set up"))
            continue
        try:
            result: CreativeResult = provider.generate(db, tenant_id, req)
            logger.info("creative_generated", tenant_id=tenant_id, kind=req.kind, provider=result.provider, model=result.model)
            return result
        except ProviderFailed as exc:
            attempts.append((provider.key, short(str(exc), 200)))
            logger.warning("creative_provider_failed", tenant_id=tenant_id, kind=req.kind, provider=provider.key, error=short(str(exc), 200))
    raise AllProvidersFailed(req.kind, attempts)
