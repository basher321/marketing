"""Text embeddings for meaning-based knowledge search (SPEC-BE-087).

One platform key (EMBEDDINGS_* in backend/.env), plain httpx like
ai/providers.py. Supported embedding APIs: OpenAI, Google Gemini (GenAI),
Voyage AI, Mistral, Cohere, and any OpenAI-compatible server
(EMBEDDINGS_BASE_URL: Together, Jina, Ollama, LM Studio, ...).

EMBEDDINGS_PROVIDER=auto (default) recognises the provider from the key
("AIza" Gemini, "pa-" Voyage, "sk-" OpenAI); with no EMBEDDINGS_API_KEY it
tries LLM_API_KEY. Anthropic (Claude) and Groq have no embeddings API: their
keys switch embeddings off with a logged reason. Mistral and Cohere keys have
no recognisable prefix, so they need an explicit provider.

Vectors come back normalized to unit length (cosine = dot product). Any
failure raises EmbeddingError; callers fall back to full-text search.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import httpx
import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)

TIMEOUT_S = 10.0
Purpose = Literal["document", "query"]


@dataclass(frozen=True)
class ProviderInfo:
    url: str
    default_model: str
    batch: int
    # Vector sizes the API accepts on request (None = any; empty = fixed size, never sent).
    sizes: frozenset[int] | None


PROVIDERS: dict[str, ProviderInfo] = {
    "openai": ProviderInfo("https://api.openai.com/v1/embeddings", "text-embedding-3-small", 100, None),
    "gemini": ProviderInfo("https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents",
                           "gemini-embedding-001", 100, None),
    "voyage": ProviderInfo("https://api.voyageai.com/v1/embeddings", "voyage-3.5", 100, frozenset({256, 512, 1024, 2048})),
    "mistral": ProviderInfo("https://api.mistral.ai/v1/embeddings", "mistral-embed", 100, frozenset()),
    "cohere": ProviderInfo("https://api.cohere.com/v2/embed", "embed-v4.0", 96, frozenset({256, 512, 1024, 1536})),
    "openai_compatible": ProviderInfo("", "", 100, frozenset()),
}
NO_EMBEDDINGS = {
    "anthropic": "Claude (Anthropic) keys have no embeddings API; Anthropic recommends Voyage AI. Set an OpenAI, Gemini, "
                 "Voyage, Mistral or Cohere key in EMBEDDINGS_API_KEY.",
    "groq": "Groq keys have no embeddings API. Set an OpenAI, Gemini, Voyage, Mistral or Cohere key in EMBEDDINGS_API_KEY.",
}


class EmbeddingError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    provider: str
    key: str
    model: str
    dims: int | None  # requested size; None = the model's own size
    url: str


# Swappable in tests (dev_fakes / httpx.MockTransport).
def _default_client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_S, follow_redirects=False)


client_factory: Callable[[], httpx.Client] = _default_client
_reported: set[str] = set()


def detect(key: str) -> str | None:
    """The provider a key belongs to, from its documented prefix."""
    if key.startswith("sk-ant-"):
        return "anthropic"
    if key.startswith("gsk_"):
        return "groq"
    if key.startswith("AIza"):
        return "gemini"
    if key.startswith("pa-"):
        return "voyage"
    if key.startswith("sk-"):
        return "openai"
    return None


def _off(reason: str) -> None:
    if reason not in _reported:  # once per process
        _reported.add(reason)
        logger.warning("embeddings_off", reason=reason)


def _usable(key: str) -> bool:
    return bool(key) and key != "changeme"


def config() -> Config | None:
    """The embedding setup, or None when embeddings are off (reason logged)."""
    s = get_settings()
    provider: str = s.EMBEDDINGS_PROVIDER
    if provider == "none":
        return None
    key = s.EMBEDDINGS_API_KEY.get_secret_value().strip()
    from_llm = False
    if not _usable(key) and provider == "auto":
        key, from_llm = s.LLM_API_KEY.get_secret_value().strip(), True
    if not _usable(key):
        if provider != "auto":
            _off(f"EMBEDDINGS_PROVIDER={provider} but EMBEDDINGS_API_KEY is empty.")
        return None
    if provider == "auto":
        detected = detect(key)
        if detected is None:
            _off("Can't tell the provider from the key: set EMBEDDINGS_PROVIDER (e.g. mistral or cohere).")
            return None
        if detected in NO_EMBEDDINGS:
            _off(NO_EMBEDDINGS[detected] + (" (tried LLM_API_KEY)" if from_llm else ""))
            return None
        provider = detected
    info = PROVIDERS[provider]
    url = info.url
    if provider == "openai_compatible":
        base = s.EMBEDDINGS_BASE_URL.strip().rstrip("/")
        if not base or not s.EMBEDDINGS_MODEL.strip():
            _off("EMBEDDINGS_PROVIDER=openai_compatible needs EMBEDDINGS_BASE_URL and EMBEDDINGS_MODEL.")
            return None
        url = f"{base}/embeddings"
    wanted = s.EMBEDDINGS_DIMENSIONS
    dims = wanted if info.sizes is None or wanted in info.sizes else None
    return Config(provider, key, s.EMBEDDINGS_MODEL.strip() or info.default_model, dims, url)


def model_id() -> str | None:
    """The stored model tag ("<provider>:<model>@<size>"): rows of another
    model or size are never compared with this one."""
    cfg = config()
    return f"{cfg.provider}:{cfg.model}@{cfg.dims or 'native'}" if cfg else None


def _unit(vector: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        raise EmbeddingError("The provider returned an empty vector.")
    return [v / norm for v in vector]


def _error(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        err = body.get("error") if isinstance(body, dict) else None
        msg = err.get("message") if isinstance(err, dict) else (err or (body.get("message") if isinstance(body, dict) else None))
    except ValueError:
        msg = None
    return f"HTTP {resp.status_code}: " + " ".join(str(msg or resp.reason_phrase).split())[:200]


def _request(cfg: Config, batch: list[str], purpose: Purpose) -> tuple[str, dict[str, str], dict[str, Any]]:
    bearer = {"Authorization": f"Bearer {cfg.key}"}
    if cfg.provider == "gemini":
        task = "RETRIEVAL_QUERY" if purpose == "query" else "RETRIEVAL_DOCUMENT"
        extra = {"outputDimensionality": cfg.dims} if cfg.dims else {}
        return cfg.url.format(model=cfg.model), {"x-goog-api-key": cfg.key}, {"requests": [
            {"model": f"models/{cfg.model}", "content": {"parts": [{"text": t}]}, "taskType": task, **extra} for t in batch]}
    if cfg.provider == "voyage":
        body: dict[str, Any] = {"model": cfg.model, "input": batch, "input_type": purpose}
        if cfg.dims:
            body["output_dimension"] = cfg.dims
        return cfg.url, bearer, body
    if cfg.provider == "cohere":
        body = {"model": cfg.model, "texts": batch, "input_type": f"search_{purpose}", "embedding_types": ["float"]}
        if cfg.dims and cfg.model.startswith("embed-v4"):
            body["output_dimension"] = cfg.dims
        return cfg.url, bearer, body
    body = {"model": cfg.model, "input": batch}  # openai, mistral, openai_compatible
    if cfg.provider == "openai" and cfg.dims:
        body["dimensions"] = cfg.dims
    return cfg.url, bearer, body


def _vectors(provider: str, data: Any) -> list[Any]:
    if provider == "gemini":
        return [e["values"] for e in data["embeddings"]]
    if provider == "cohere":
        return list(data["embeddings"]["float"])
    return [r["embedding"] for r in sorted(data["data"], key=lambda r: r.get("index", 0))]


def embed(texts: Sequence[str], purpose: Purpose) -> list[list[float]]:
    """Unit vectors for `texts`, in order. Raises EmbeddingError."""
    cfg = config()
    if cfg is None:
        raise EmbeddingError("Embeddings are not configured.")
    size = PROVIDERS[cfg.provider].batch
    out: list[list[float]] = []
    try:
        with client_factory() as client:
            for start in range(0, len(texts), size):
                batch = [t[:8000] for t in texts[start:start + size]]
                url, headers, body = _request(cfg, batch, purpose)
                resp = client.post(url, headers=headers, json=body)
                if resp.status_code >= 400:
                    raise EmbeddingError(_error(resp))
                vectors = _vectors(cfg.provider, resp.json())
                if len(vectors) != len(batch):
                    raise EmbeddingError("The provider returned a different number of vectors.")
                out.extend(_unit([float(x) for x in v]) for v in vectors)
    except httpx.TimeoutException:
        raise EmbeddingError(f"Timed out after {TIMEOUT_S:.0f}s.") from None
    except httpx.HTTPError as exc:
        raise EmbeddingError(f"Network error ({type(exc).__name__}).") from None
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise EmbeddingError(f"Unexpected response format ({type(exc).__name__}).") from None
    return out
