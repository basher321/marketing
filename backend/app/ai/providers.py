"""LLM provider adapters over plain HTTPS (SPEC-BE-053).

One function per API family, all through `httpx` (already installed), so no
provider SDK is needed. Each returns (text, input_tokens, output_tokens) and
raises ProviderCallError with a short, secret-free message on any failure.

Gemini, Groq, OpenRouter and Ollama expose OpenAI-compatible chat-completions
endpoints, so they share the OpenAI adapter with a different base URL.
"""
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings


@dataclass(frozen=True)
class ProviderSpec:
    provider: str
    label: str
    url: str
    style: str  # "anthropic" | "openai"
    docs_url: str
    models_url: str
    # Words that mark the model we suggest first (SPEC-BE-053 amendment
    # 2026-10-02, rule 4), and the same for image models (empty = no images).
    prefer: str
    prefer_image: str = ""
    # False for a local server that takes no key (Ollama, SPEC-BE-088).
    needs_key: bool = True


# Local Ollama (SPEC-BE-088): its OpenAI-compatible API on this server.
_OLLAMA = get_settings().OLLAMA_BASE_URL.rstrip("/")

# No default model (SPEC-BE-053 amendment 2026-10-02): providers retire models
# without notice, so the company always chooses one from the provider's live
# list (list_models below) and nothing is picked silently. The tuple order is
# the default fallback order (SPEC-BE-088): Claude, OpenAI, Gemini, Groq,
# OpenRouter, Ollama.
PROVIDERS: tuple[ProviderSpec, ...] = (
    ProviderSpec("anthropic", "Anthropic Claude", "https://api.anthropic.com/v1/messages", "anthropic", "https://console.anthropic.com/settings/keys",
                 "https://api.anthropic.com/v1/models?limit=1000", "sonnet"),
    ProviderSpec("openai", "OpenAI GPT", "https://api.openai.com/v1/chat/completions", "openai", "https://platform.openai.com/api-keys",
                 "https://api.openai.com/v1/models", "mini", "gpt-image"),
    ProviderSpec("gemini", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "openai", "https://aistudio.google.com/app/apikey",
                 "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000", "flash", "flash-image"),
    ProviderSpec("groq", "Groq", "https://api.groq.com/openai/v1/chat/completions", "openai", "https://console.groq.com/keys",
                 "https://api.groq.com/openai/v1/models", "gpt-oss"),
    ProviderSpec("openrouter", "OpenRouter", "https://openrouter.ai/api/v1/chat/completions", "openai", "https://openrouter.ai/settings/keys",
                 "https://openrouter.ai/api/v1/models", "gpt-oss"),
    ProviderSpec("ollama", "Ollama (local)", f"{_OLLAMA}/chat/completions", "openai", "https://ollama.com/download",
                 f"{_OLLAMA}/models", "llama", needs_key=False),
)
BY_PROVIDER = {p.provider: p for p in PROVIDERS}


class ProviderCallError(Exception):
    pass


# Swappable in tests (httpx.MockTransport) so no real provider is called.
def _default_client(timeout_s: float) -> httpx.Client:
    return httpx.Client(timeout=timeout_s, follow_redirects=False)


client_factory: Callable[[float], httpx.Client] = _default_client


def _error_text(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        err = body.get("error") if isinstance(body, dict) else None
        msg = err.get("message") if isinstance(err, dict) else (err or body)
    except ValueError:
        msg = resp.text
    return f"HTTP {resp.status_code}: " + " ".join(str(msg).split())[:240]


def call(
    provider: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    timeout_s: float,
    temperature: float | None = None,
) -> tuple[str, int, int]:
    spec = BY_PROVIDER.get(provider)
    if spec is None:
        raise ProviderCallError(f"Unknown provider {provider}.")
    body: dict[str, Any]
    if spec.style == "anthropic":
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        body = {"model": model, "max_tokens": max_tokens, "system": system_prompt, "messages": [{"role": "user", "content": user_prompt}]}
    else:
        headers = {"Authorization": f"Bearer {api_key or 'none'}", "content-type": "application/json"}
        # OpenAI's newer models (GPT-5, o-series) reject max_tokens and every
        # OpenAI chat model accepts max_completion_tokens (SPEC-BE-088
        # amendment 2026-10-09). The other OpenAI-style APIs keep max_tokens.
        limit_name = "max_completion_tokens" if provider == "openai" else "max_tokens"
        body = {
            "model": model,
            limit_name: max_tokens,
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        }
    if temperature is not None:
        body["temperature"] = temperature
    try:
        with client_factory(timeout_s) as client:
            resp = client.post(spec.url, headers=headers, json=body)
            # A provider that wants the newer name (e.g. an OpenAI model via
            # OpenRouter): ask once more with it.
            if resp.status_code == 400 and "max_tokens" in body and "max_completion_tokens" in _error_text(resp):
                body["max_completion_tokens"] = body.pop("max_tokens")
                resp = client.post(spec.url, headers=headers, json=body)
            # Some models accept only their default temperature (SPEC-BE-085
            # FR6): ask once more without it instead of failing over.
            if temperature is not None and resp.status_code == 400 and "temperature" in _error_text(resp).lower():
                body.pop("temperature")
                resp = client.post(spec.url, headers=headers, json=body)
    except httpx.TimeoutException:
        raise ProviderCallError(f"Timed out after {timeout_s:.0f}s.") from None
    except httpx.HTTPError as exc:
        raise ProviderCallError(f"Network error ({type(exc).__name__}).") from None
    if resp.status_code >= 400:
        raise ProviderCallError(_error_text(resp))
    try:
        body = resp.json()
        if spec.style == "anthropic":
            text = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")
            usage = body.get("usage") or {}
            return text, int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
        text = body["choices"][0]["message"].get("content") or ""
        usage = body.get("usage") or {}
        return text, int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise ProviderCallError("Unexpected response format.") from None


# ---------------------------------------------------------------------------
# Live model lists (SPEC-BE-053 amendment 2026-10-02, rules 2-4).
# ---------------------------------------------------------------------------
# Chat vs image, for providers whose list has no type (OpenAI, Groq): names
# decide. Gemini reports supportedGenerationMethods; Anthropic lists only chat
# models. Models that are neither (embeddings, speech, moderation, video,
# legacy completions) are left out.
_IMAGE_NAMES = re.compile(r"(gpt-image|dall-e|-image)")
_NOT_CHAT = re.compile(
    r"(embed|whisper|transcribe|tts|audio|realtime|moderation|guard|sora|davinci|babbage|aqa|imagen|veo|-live|native-audio|instruct)"
)
_UNSTABLE = re.compile(r"(preview|exp|experimental|latest|lite|beta|alpha)")
_DATED = re.compile(r"-(\d{8}|\d{4}-\d{2}-\d{2})$")


_VIDEO_NAMES = re.compile(r"(^|/|-)(veo|sora)")


def _kind(provider: str, model_id: str, methods: list[str] | None) -> str | None:
    name = model_id.lower()
    if provider == "anthropic":
        return "chat"
    # Video models (SPEC-BE-077): Veo on Gemini (predictLongRunning, no
    # generateContent), Sora on OpenAI.
    if provider in ("openai", "gemini") and _VIDEO_NAMES.search(name):
        return "video"
    if provider == "gemini" and methods is not None and "generateContent" not in methods:
        return None
    if _IMAGE_NAMES.search(name):
        return "image" if provider in ("openai", "gemini") else None
    if _NOT_CHAT.search(name):
        return None
    return "chat"


def _version(model_id: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", _DATED.sub("", model_id))[:4])


def suggest(spec: ProviderSpec, ids: list[str], image: bool = False) -> str | None:
    """Newest stable model whose name has the provider's preferred word; falls
    back to unstable ones, then to any model. Undated aliases beat dated ids."""
    word = spec.prefer_image if image else spec.prefer
    if not ids:
        return None
    pools = (
        [i for i in ids if word and word in i.lower() and not _UNSTABLE.search(i.lower())],
        [i for i in ids if word and word in i.lower()],
        [i for i in ids if not _UNSTABLE.search(i.lower())],
        ids,
    )
    pool = next(p for p in pools if p)
    return max(pool, key=lambda i: (_version(i), not _DATED.search(i), -len(i)))


def list_models(provider: str, api_key: str, timeout_s: float) -> dict[str, Any]:
    """The models this key can use: {"chat": [{id, label}], "image": [...]}.
    Raises ProviderCallError with a secret-free message on any failure."""
    spec = BY_PROVIDER.get(provider)
    if spec is None:
        raise ProviderCallError(f"Unknown provider {provider}.")
    if spec.style == "anthropic":
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    elif provider == "gemini":
        headers = {"x-goog-api-key": api_key}  # header, never the query string
    else:
        headers = {"Authorization": f"Bearer {api_key or 'none'}"}
    try:
        with client_factory(timeout_s) as client:
            resp = client.get(spec.models_url, headers=headers)
    except httpx.TimeoutException:
        raise ProviderCallError(f"Timed out after {timeout_s:.0f}s.") from None
    except httpx.HTTPError as exc:
        raise ProviderCallError(f"Network error ({type(exc).__name__}).") from None
    if resp.status_code >= 400:
        raise ProviderCallError(_error_text(resp))
    try:
        body = resp.json()
        rows = body.get("models") if provider == "gemini" else body.get("data")
        out: dict[str, list[dict[str, str]]] = {"chat": [], "image": [], "video": []}
        seen: set[str] = set()
        for row in rows or []:
            if provider == "gemini":
                model_id = str(row.get("name", "")).removeprefix("models/")
                label = str(row.get("displayName") or model_id)
                methods = list(row.get("supportedGenerationMethods") or [])
            else:
                model_id = str(row.get("id", ""))
                label = str(row.get("display_name") or model_id)
                methods = None
            kind = _kind(provider, model_id, methods) if model_id else None
            if kind and model_id not in seen:
                seen.add(model_id)
                out[kind].append({"id": model_id, "label": label})
    except (ValueError, AttributeError, TypeError):
        raise ProviderCallError("Unexpected response format.") from None
    for kind in out:
        out[kind].sort(key=lambda m: (_version(m["id"]), m["id"]), reverse=True)
    return out
