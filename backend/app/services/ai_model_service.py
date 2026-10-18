"""The AI providers with a fallback order (SPEC-BE-053, SPEC-BE-088).

SPEC-BE-101: the keys are PilotSonic's, managed by the Super admin, and every
company uses them ("Shared only"). They live in platform_settings["llm_providers"]
= {provider: {key_enc, model, image_model, video_model, enabled, priority,
last_error, last_ok_at}}: the shape each company used to keep in
tenants.settings["llm_providers"], which is no longer read (kept, not deleted).
There is no default model (SPEC-BE-053 amendment 2026-10-02): a provider is used
only once a model was chosen from the provider's live list (list_models). Keys are
Fernet-encrypted (utils/crypto) and never returned; companies don't even see them
masked. The `tenant_id` arguments name the caller (for the audit), not the keys.
"""
import time
from datetime import datetime, timezone
from typing import Any

import structlog
from cryptography.fernet import InvalidToken
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai import providers as llm_providers
from app.config import get_settings
from app.core.audit import write_audit_log
from app.core.exceptions import AppError, NotFoundError
from app.models.tenant import Tenant
from app.schemas.ai_model import AIModelUpdate
from app.services import platform_service
from app.utils.crypto import decrypt_secret, encrypt_secret

logger = structlog.get_logger(__name__)
# Providers with video models (SPEC-BE-077): Sora (OpenAI) and Veo (Gemini).
VIDEO_PROVIDERS = ("openai", "gemini")
TEST_TIMEOUT_S = 20.0
LIST_TIMEOUT_S = 15.0
STORE_KEY = "llm_providers"
# SPEC-BE-101 FR3: what a company sees when it tries to manage keys.
PROVIDED = "AI keys are provided by PilotSonic; the Super admin manages them."
NOT_SET_UP = "PilotSonic's AI isn't set up yet (the Super admin adds the keys)."


def _tenant(db: Session, tenant_id: str) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant not found.")
    return tenant


def _config(db: Session | None) -> dict[str, dict[str, Any]]:
    """The software's providers (SPEC-BE-101)."""
    return {k: dict(v) for k, v in platform_service.get(STORE_KEY, db).items() if isinstance(v, dict)}


def _save(db: Session, config: dict[str, dict[str, Any]], actor_user_id: str) -> None:
    platform_service.put(db, STORE_KEY, config, actor_user_id)


def _spec(provider: str) -> llm_providers.ProviderSpec:
    spec = llm_providers.BY_PROVIDER.get(provider)
    if spec is None:
        raise NotFoundError("Unknown AI provider.")
    return spec


def _key(entry: dict[str, Any]) -> str | None:
    blob = entry.get("key_enc")
    if not blob:
        return None
    try:
        return decrypt_secret(blob)
    except (InvalidToken, ValueError):
        return None


def _usable_key(spec: llm_providers.ProviderSpec, entry: dict[str, Any]) -> str | None:
    """The saved key; "" for a provider that takes none (Ollama); None when a
    needed key is missing (SPEC-BE-088)."""
    key = _key(entry)
    return key if key is not None else (None if spec.needs_key else "")


def _priority(config: dict[str, dict[str, Any]], provider: str) -> int:
    default = [p.provider for p in llm_providers.PROVIDERS].index(provider)
    return int(config.get(provider, {}).get("priority", default))


def _ts(raw: str | None) -> datetime | None:
    return datetime.fromisoformat(raw).astimezone(timezone.utc) if raw else None


def list_providers(db: Session, tenant_id: str | None = None, admin: bool = False) -> dict[str, Any]:
    """The software's providers. Only the Super admin (admin=True) sees masked keys."""
    config = _config(db)
    items: list[dict[str, Any]] = []
    for spec in llm_providers.PROVIDERS:
        entry = config.get(spec.provider, {})
        key = _key(entry)
        items.append(
            {
                "provider": spec.provider,
                "label": spec.label,
                "enabled": bool(entry.get("enabled")) and _usable_key(spec, entry) is not None and bool(entry.get("model")),
                "model": entry.get("model") or None,
                "image_model": entry.get("image_model") or None,
                "has_images": bool(spec.prefer_image),
                "video_model": entry.get("video_model") or None,
                "has_video": spec.provider in VIDEO_PROVIDERS,
                "priority": _priority(config, spec.provider),
                "has_key": key is not None or not spec.needs_key,
                "key_masked": (platform_service.mask(key) if admin else None),
                "last_error": entry.get("last_error"),
                "last_ok_at": _ts(entry.get("last_ok_at")),
                "docs_url": spec.docs_url,
                "needs_key": spec.needs_key,
            }
        )
    items.sort(key=lambda i: int(i["priority"]))
    settings = get_settings()
    env_key = settings.LLM_API_KEY.get_secret_value()
    return {
        "providers": items,
        "env_fallback": {
            "provider": settings.LLM_PROVIDER,
            "configured": settings.LLM_PROVIDER in ("anthropic", "openai") and bool(env_key) and env_key != "changeme",
        },
        "managed_by": "platform",
    }


def update_provider(
    db: Session, tenant_id: str, actor_user_id: str, provider: str, payload: AIModelUpdate
) -> dict[str, Any]:
    """Super admin only (api/v1/platform.py); tenant_id is the Super admin's workspace."""
    spec = _spec(provider)
    config = _config(db)
    entry = config.get(provider, {})
    entry.setdefault("priority", _priority(config, provider))
    sent = payload.model_fields_set
    if "api_key" in sent and payload.api_key and payload.api_key.strip():
        entry["key_enc"] = encrypt_secret(payload.api_key.strip())
        entry["last_error"] = None
    if "model" in sent and payload.model:
        entry["model"] = payload.model.strip()
    if "image_model" in sent:
        if payload.image_model and payload.image_model.strip() and not spec.prefer_image:
            raise AppError(f"{spec.label} has no image models.", 422)
        entry["image_model"] = (payload.image_model or "").strip() or None
    if "video_model" in sent:
        if payload.video_model and payload.video_model.strip() and provider not in VIDEO_PROVIDERS:
            raise AppError(f"{spec.label} has no video models.", 422)
        entry["video_model"] = (payload.video_model or "").strip() or None
    if "enabled" in sent and payload.enabled is not None:
        if payload.enabled and _usable_key(spec, entry) is None:
            raise AppError("Add an API key before enabling this model.", 422)
        if payload.enabled and not entry.get("model"):
            raise AppError("Choose a model before enabling.", 422)
        entry["enabled"] = payload.enabled
    elif "enabled" not in entry and _usable_key(spec, entry) is not None and entry.get("model"):
        entry["enabled"] = True  # turns on the first time it has a key and a model
    config[provider] = entry
    _save(db, config, actor_user_id)
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="platform.ai_model.update",
        resource_type="tenant",
        resource_id=tenant_id,
        metadata={"provider": provider, "fields": sorted(f for f in sent if f != "api_key") + (["api_key"] if payload.api_key else [])},
    )
    return list_providers(db, tenant_id, admin=True)


def set_order(db: Session, tenant_id: str, actor_user_id: str, order: list[str]) -> dict[str, Any]:
    if len(set(order)) != len(order):
        raise AppError("Each provider may appear once.", 422)
    config = _config(db)
    rest = [p.provider for p in llm_providers.PROVIDERS if p.provider not in order]
    for index, provider in enumerate(list(order) + rest):
        config.setdefault(provider, {})["priority"] = index
    _save(db, config, actor_user_id)
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="platform.ai_model.order",
        resource_type="tenant",
        resource_id=tenant_id,
        metadata={"order": list(order) + rest},
    )
    return list_providers(db, tenant_id, admin=True)


def delete_key(db: Session, tenant_id: str, actor_user_id: str, provider: str) -> dict[str, Any]:
    _spec(provider)
    config = _config(db)
    entry = config.get(provider, {})
    entry.pop("key_enc", None)
    entry["enabled"] = False
    entry["last_error"] = None
    config[provider] = entry
    _save(db, config, actor_user_id)
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="platform.ai_model.delete",
        resource_type="tenant",
        resource_id=tenant_id,
        metadata={"provider": provider},
    )
    return list_providers(db, tenant_id, admin=True)


def test_provider(db: Session, tenant_id: str, actor_user_id: str, provider: str) -> dict[str, Any]:
    spec = _spec(provider)
    config = _config(db)
    entry = config.get(provider, {})
    key = _usable_key(spec, entry)
    if key is None:
        raise AppError("Save an API key first.", 409)
    model = entry.get("model")
    if not model:
        raise AppError("Choose a model first.", 409)
    started = time.perf_counter()
    error = None
    suggestions: list[str] = []
    suggested = None
    try:
        llm_providers.call(provider, key, model, "You are a connection test.", "Reply with OK.", 5, TEST_TIMEOUT_S,
                           require_complete=False)  # 5 tokens: a cut-off answer still proves the key works
    except llm_providers.ProviderCallError as exc:
        error = str(exc)
        if error.startswith("HTTP 404"):
            # A 404 nearly always means a retired model name. Offer what the key
            # can use now; the user picks one, nothing switches by itself.
            error = error[:240] + " — the model may be retired; choose another model."
            try:
                chat = [m["id"] for m in llm_providers.list_models(provider, key, LIST_TIMEOUT_S)["chat"] if m["id"] != model]
                suggested = llm_providers.suggest(spec, chat)
                suggestions = ([suggested] if suggested else []) + [m for m in chat if m != suggested][:4]
            except llm_providers.ProviderCallError:
                pass
    latency = int((time.perf_counter() - started) * 1000)
    now = datetime.now(timezone.utc).isoformat()
    entry["last_error"] = error
    if error is None:
        entry["last_ok_at"] = now
    config[provider] = entry
    _save(db, config, actor_user_id)
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="platform.ai_model.test",
        resource_type="tenant",
        resource_id=tenant_id,
        metadata={"provider": provider, "ok": error is None},
    )
    return {"ok": error is None, "latency_ms": latency, "model": model, "error": error, "suggested": suggested, "suggestions": suggestions}


def list_models(db: Session, tenant_id: str, provider: str) -> dict[str, Any]:
    """The provider's live model list for the saved key (a read: nothing is
    stored or audited). A provider error is returned in `error`."""
    spec = _spec(provider)
    key = _usable_key(spec, _config(db).get(provider, {}))
    if key is None:
        raise AppError("Save an API key first.", 409)
    try:
        models = llm_providers.list_models(provider, key, LIST_TIMEOUT_S)
    except llm_providers.ProviderCallError as exc:
        return {"ok": False, "error": str(exc), "chat": [], "image": [], "video": [], "suggested": {"chat": None, "image": None}}
    return {
        "ok": True,
        "error": None,
        **models,
        "suggested": {
            "chat": llm_providers.suggest(spec, [m["id"] for m in models["chat"]]),
            "image": llm_providers.suggest(spec, [m["id"] for m in models["image"]], image=True) if spec.prefer_image else None,
        },
    }


def resolve_chain(db: Session | None, tenant_id: str | None = None) -> list[tuple[str, str, str]]:
    """The software's enabled providers with a key, in fallback order:
    [(provider, key, model)]. The same for every company (SPEC-BE-101), and
    empty for a company the Super admin switched AI off for (SPEC-BE-103)."""
    if not platform_service.allowed(tenant_id, "ai", db):
        return []
    config = _config(db)
    chain = []
    for spec in sorted(llm_providers.PROVIDERS, key=lambda s: _priority(config, s.provider)):
        entry = config.get(spec.provider, {})
        key = _usable_key(spec, entry)
        if entry.get("enabled") and key is not None and entry.get("model"):
            chain.append((spec.provider, key, entry["model"]))
    return chain


def record_outcome(tenant_id: str | None, provider: str, error: str | None) -> None:
    """Record a live call's result (last_error / last_ok_at) on the software's
    provider, in its own short transaction, so it never commits or disturbs the
    caller's session. A failure here is logged and ignored: it must never break
    the AI call."""
    from app.db.session import engine

    path_err = "{" + provider + ",last_error}"
    path_ok = "{" + provider + ",last_ok_at}"
    try:
        with engine.begin() as conn:
            # Never wait behind the Super admin saving the same row: give up after 2 s.
            conn.execute(text("SET LOCAL lock_timeout = '2s'"))
            if error is None:
                conn.execute(
                    text("UPDATE platform_settings SET value = jsonb_set(jsonb_set(value, CAST(:pe AS text[]), 'null'::jsonb), CAST(:po AS text[]), to_jsonb(CAST(:now AS text))) WHERE key = :k AND value ? :p"),
                    {"pe": path_err, "po": path_ok, "now": datetime.now(timezone.utc).isoformat(), "k": STORE_KEY, "p": provider},
                )
            else:
                conn.execute(
                    text("UPDATE platform_settings SET value = jsonb_set(value, CAST(:pe AS text[]), to_jsonb(CAST(:e AS text))) WHERE key = :k AND value ? :p"),
                    {"pe": path_err, "e": error[:300], "k": STORE_KEY, "p": provider},
                )
    except Exception:  # noqa: BLE001 - bookkeeping only
        logger.warning("llm_outcome_record_failed", provider=provider)


def provider_key(db: Session | None, tenant_id: str, provider: str) -> str | None:
    """The software's key (decrypted) for the creative and voice providers
    (SPEC-BE-070, SPEC-BE-095): images, video and speech reuse the OpenAI /
    Gemini / Groq keys. Never returned. None for a company whose AI is
    switched off (SPEC-BE-103); "" (no company) is the platform's own use."""
    if not platform_service.allowed(tenant_id or None, "ai", db):
        return None
    return _key(_config(db).get(provider, {}))


def image_model(db: Session, tenant_id: str, provider: str) -> str | None:
    """The image model chosen for this provider (SPEC-BE-070 amendment
    2026-10-02); None means image generation isn't set up."""
    return _config(db).get(provider, {}).get("image_model") or None


def video_model(db: Session, tenant_id: str, provider: str) -> str | None:
    """The video model chosen (SPEC-BE-077); None = not set up."""
    return _config(db).get(provider, {}).get("video_model") or None


# ---------------------------------------------------------------------------
# Creative settings + MCP creative tools (SPEC-BE-070), stored in
# tenants.settings["creative"] = {order: {kind: [keys]}, mcp_tools: {id: {...,
# token_enc}}}. Tokens are Fernet-encrypted and only ever returned masked.
# ---------------------------------------------------------------------------
def _creative(tenant: Tenant) -> dict[str, Any]:
    return dict(((tenant.settings or {}).get("creative")) or {})


def _save_creative(tenant: Tenant, creative: dict[str, Any]) -> None:
    settings = dict(tenant.settings or {})
    settings["creative"] = creative
    tenant.settings = settings


def creative_settings(db: Session, tenant_id: str) -> dict[str, Any]:
    from app.ai import creative_providers as cp

    tenant = _tenant(db, tenant_id)
    creative = _creative(tenant)
    tools = []
    for tool_id, cfg in (creative.get("mcp_tools") or {}).items():
        token = None
        if cfg.get("token_enc"):
            try:
                token = decrypt_secret(cfg["token_enc"])
            except (InvalidToken, ValueError):
                token = None
        tools.append({"id": tool_id, "name": cfg.get("name", tool_id), "url": cfg.get("url", ""), "enabled": bool(cfg.get("enabled", True)),
                      "token_masked": ("••••" + token[-4:]) if token and len(token) >= 8 else ("••••" if token else None),
                      "tools": dict(cfg.get("tools") or {}), "arguments": dict(cfg.get("arguments") or {}),
                      "cost_cents_per_call": int(cfg.get("cost_cents_per_call") or 0),
                      "last_error": cfg.get("last_error"), "last_ok_at": cfg.get("last_ok_at")})
    available: dict[str, list[dict[str, Any]]] = {}
    for kind in cp.KINDS:
        rows = [{"key": k, "label": {"llm": "AI models (in your order above)", "openai_image": "OpenAI images", "gemini_image": "Gemini images",
                                     "openai_video": "OpenAI Sora video", "gemini_video": "Google Veo video"}[k],
                 "ready": p.available(db, tenant_id)} for k, p in cp.BUILT_IN.items() if kind in p.kinds and k != "catalog"]
        rows += [{"key": f"mcp:{t['id']}", "label": f"MCP: {t['name']}", "ready": t["enabled"]} for t in tools if t["tools"].get(kind)]
        available[kind] = rows
    order = {kind: [p.key for p in cp.ordered(db, tenant_id, kind)] for kind in cp.KINDS}
    return {"order": order, "available": available, "mcp_tools": tools}


def set_creative_order(db: Session, tenant_id: str, actor_user_id: str, order: dict[str, list[str]]) -> dict[str, Any]:
    from app.ai import creative_providers as cp

    tenant = _tenant(db, tenant_id)
    creative = _creative(tenant)
    known = set(cp.BUILT_IN) | {f"mcp:{t}" for t in (creative.get("mcp_tools") or {})}
    for kind, keys in order.items():
        unknown = [k for k in keys if k not in known or k == "catalog"]
        if unknown:
            raise AppError(f"Unknown provider for {kind}: {', '.join(unknown)}.", 422)
        if len(set(keys)) != len(keys):
            raise AppError("Each provider may appear once.", 422)
    creative["order"] = {**dict(creative.get("order") or {}), **{k: list(v) for k, v in order.items()}}
    _save_creative(tenant, creative)
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor_user_id, action="ai_model.creative_order",
                    resource_type="tenant", resource_id=tenant_id, metadata={"order": creative["order"]})
    return creative_settings(db, tenant_id)


def save_mcp_tool(db: Session, tenant_id: str, actor_user_id: str, tool_id: str, payload: Any) -> dict[str, Any]:
    from app.integrations import mcp_client

    try:
        mcp_client._check_url(payload.url)
    except mcp_client.MCPError as exc:
        raise AppError(exc.message, 422) from None
    tenant = _tenant(db, tenant_id)
    creative = _creative(tenant)
    tools = dict(creative.get("mcp_tools") or {})
    entry = dict(tools.get(tool_id) or {})
    entry.update(name=payload.name.strip(), url=payload.url, enabled=payload.enabled, tools=dict(payload.tools),
                 arguments=dict(payload.arguments), cost_cents_per_call=payload.cost_cents_per_call)
    if payload.token and payload.token.strip():
        entry["token_enc"] = encrypt_secret(payload.token.strip())
    tools[tool_id] = entry
    creative["mcp_tools"] = tools
    _save_creative(tenant, creative)
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor_user_id, action="ai_model.mcp_saved", resource_type="tenant",
                    resource_id=tenant_id, metadata={"tool_id": tool_id, "kinds": sorted(payload.tools), "token_changed": bool(payload.token)})
    return creative_settings(db, tenant_id)


def delete_mcp_tool(db: Session, tenant_id: str, actor_user_id: str, tool_id: str) -> dict[str, Any]:
    tenant = _tenant(db, tenant_id)
    creative = _creative(tenant)
    tools = dict(creative.get("mcp_tools") or {})
    if tool_id not in tools:
        raise NotFoundError("MCP tool not found.")
    tools.pop(tool_id)
    creative["mcp_tools"] = tools
    creative["order"] = {k: [x for x in v if x != f"mcp:{tool_id}"] for k, v in dict(creative.get("order") or {}).items()}
    _save_creative(tenant, creative)
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor_user_id, action="ai_model.mcp_deleted", resource_type="tenant",
                    resource_id=tenant_id, metadata={"tool_id": tool_id})
    return creative_settings(db, tenant_id)


def test_mcp_tool(db: Session, tenant_id: str, actor_user_id: str, tool_id: str) -> dict[str, Any]:
    """initialize + tools/list, and check every mapped tool exists."""
    from app.ai import creative_providers as cp
    from app.integrations import mcp_client

    provider = cp.mcp_providers(db, tenant_id).get(f"mcp:{tool_id}")
    if provider is None:
        raise NotFoundError("MCP tool not found.")
    found: list[str] = []
    try:
        session = mcp_client.MCPSession(provider.config.get("url", ""), provider.token)
        session.initialize()
        found = [str(t.get("name")) for t in session.list_tools()]
        missing = [name for name in (provider.config.get("tools") or {}).values() if name not in found]
        ok, message = (False, f"The server has no tool named {', '.join(missing)}.") if missing else (True, "Connected; every mapped tool exists.")
    except mcp_client.MCPError as exc:
        ok, message = False, exc.message
    tenant = _tenant(db, tenant_id)
    creative = _creative(tenant)
    tools = dict(creative.get("mcp_tools") or {})
    entry = dict(tools.get(tool_id) or {})
    entry["last_error"] = None if ok else message[:300]
    if ok:
        entry["last_ok_at"] = datetime.now(timezone.utc).isoformat()
    tools[tool_id] = entry
    creative["mcp_tools"] = tools
    _save_creative(tenant, creative)
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor_user_id, action="ai_model.mcp_tested", resource_type="tenant",
                    resource_id=tenant_id, metadata={"tool_id": tool_id, "ok": ok})
    return {"ok": ok, "message": message, "tools_found": found}


# ---------------------------------------------------------------------------
# Sound for AI slideshow videos (SPEC-BE-094): tenants.settings.creative.video_audio
# ---------------------------------------------------------------------------
VIDEO_AUDIO_DEFAULTS: dict[str, Any] = {"voiceover": True, "voice": "alloy", "music_media_id": None, "music_volume": 0.25}


def video_audio(db: Session, tenant_id: str) -> dict[str, Any]:
    """The company's settings (defaults filled in) plus the chosen track."""
    from app.services import media_service

    tenant = _tenant(db, tenant_id)
    cfg = {**VIDEO_AUDIO_DEFAULTS, **dict(_creative(tenant).get("video_audio") or {})}
    music = None
    if cfg.get("music_media_id"):
        try:
            music = media_service.media_dict(media_service.require(db, tenant_id, str(cfg["music_media_id"])))
        except NotFoundError:
            cfg["music_media_id"] = None  # the track was deleted from the media library
    return {**cfg, "music": music}


def set_video_audio(db: Session, tenant_id: str, actor_user_id: str, payload: Any) -> dict[str, Any]:
    from app.services import media_service

    data = payload.model_dump()
    if data.get("music_media_id"):
        media_service.media_rows(db, tenant_id, [str(data["music_media_id"])], kinds=("audio",))
    tenant = _tenant(db, tenant_id)
    creative = _creative(tenant)
    creative["video_audio"] = {k: data[k] for k in VIDEO_AUDIO_DEFAULTS}
    _save_creative(tenant, creative)
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor_user_id, action="ai_model.video_audio",
                    resource_type="tenant", resource_id=tenant_id, metadata=creative["video_audio"])
    return video_audio(db, tenant_id)
