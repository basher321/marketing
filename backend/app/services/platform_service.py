"""The software's own settings and API keys, managed by the Super admin (SPEC-BE-101).

PilotSonic owns every API key; companies only connect their own pages and
accounts. One row per group in `platform_settings (key, value jsonb, updated_by,
updated_at)`:

- llm_providers  the AI chain, same shape SPEC-BE-053 used per company
- socialapi      {api_key_enc} the master SocialAPI key
- zernio         {api_key_enc}
- meta_app       {app_id, app_secret_enc, login_config_id, social_login_config_id}
- tiktok_app     {client_key, client_secret_enc}
- linkedin_app   {client_id, client_secret_enc}
- company_access {tenant_id: {group: false}} which companies may use them (SPEC-BE-103)

Secrets are Fernet-encrypted (`*_enc`, utils/crypto), never returned (masked)
and never logged. A field that isn't set falls back to backend/.env, so what
worked before keeps working. Who is Super admin is a row in `platform_admins`;
no route writes it (FR1).

Reads without a session use a short process cache (CACHE_TTL_S, cleared on save);
reads with a session see that session's transaction (tests roll back).
"""
import time
from datetime import datetime, timezone
from typing import Any

import structlog
from cryptography.fernet import InvalidToken
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.audit import write_audit_log
from app.core.exceptions import AppError
from app.utils.crypto import decrypt_secret, encrypt_secret

logger = structlog.get_logger(__name__)

CACHE_TTL_S = 30.0
_cache: dict[str, tuple[float, dict[str, Any]]] = {}

# group -> field -> (label, .env setting it falls back to, secret?)
FIELDS: dict[str, dict[str, tuple[str, str | None, bool]]] = {
    "socialapi": {"api_key": ("SocialAPI master key", None, True)},
    "zernio": {"api_key": ("Zernio API key", "ZERNIO_API_KEY", True)},
    "meta_app": {
        "app_id": ("Meta app ID", "META_APP_ID", False),
        "app_secret": ("Meta app secret", "META_APP_SECRET", True),
        "login_config_id": ("Facebook Login for Business config ID (ads)", "META_LOGIN_CONFIG_ID", False),
        "social_login_config_id": ("Facebook Login config ID (pages)", "META_SOCIAL_LOGIN_CONFIG_ID", False),
    },
    "tiktok_app": {
        "client_key": ("TikTok client key", "TIKTOK_CLIENT_KEY", False),
        "client_secret": ("TikTok client secret", "TIKTOK_CLIENT_SECRET", True),
    },
    "linkedin_app": {
        "client_id": ("LinkedIn client ID", "LINKEDIN_CLIENT_ID", False),
        "client_secret": ("LinkedIn client secret", "LINKEDIN_CLIENT_SECRET", True),
    },
    # SPEC-BE-108: one Twilio account; numbers are assigned per company.
    "twilio": {
        "account_sid": ("Twilio account SID", None, False),
        "auth_token": ("Twilio auth token", None, True),
    },
    # SPEC-BE-112: WhatsApp Cloud API through the Meta app above (Embedded Signup).
    "whatsapp_app": {
        "config_id": ("WhatsApp Embedded Signup configuration ID", None, False),
        "verify_token": ("Webhook verify token", None, True),
    },
}
GROUP_LABEL = {"socialapi": "SocialAPI", "zernio": "Zernio", "meta_app": "Meta (Facebook / Instagram) app",
               "tiktok_app": "TikTok app", "linkedin_app": "LinkedIn app", "twilio": "Twilio (SMS)",
               "whatsapp_app": "WhatsApp Business (Cloud API)"}


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------
def _read(key: str, db: Session | None) -> dict[str, Any]:
    sql = text("SELECT value FROM platform_settings WHERE key = :k")
    if db is not None:
        row = db.execute(sql, {"k": key}).scalar()
    else:
        from app.db.session import engine

        with engine.connect() as conn:
            row = conn.execute(sql, {"k": key}).scalar()
    return dict(row) if isinstance(row, dict) else {}


def get(key: str, db: Session | None = None) -> dict[str, Any]:
    """A group's stored value (a copy). With `db`, read in that session (no cache)."""
    if db is not None:
        return _read(key, db)
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
        return dict(hit[1])
    try:
        value = _read(key, None)
    except Exception:  # noqa: BLE001 - a DB hiccup must not break a provider call; .env still applies
        logger.warning("platform_settings_unreadable", key=key)
        return dict(hit[1]) if hit else {}
    _cache[key] = (time.monotonic(), value)
    return dict(value)


def clear_cache() -> None:
    _cache.clear()


def put(db: Session, key: str, value: dict[str, Any], actor_user_id: str | None) -> None:
    """Upsert a group (no commit; the caller's audit write commits)."""
    import json

    db.execute(
        text("INSERT INTO platform_settings (key, value, updated_by, updated_at) VALUES (:k, CAST(:v AS jsonb), :u, now()) "
             "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by, updated_at = now()"),
        {"k": key, "v": json.dumps(value), "u": actor_user_id},
    )
    clear_cache()


def audit(db: Session, actor_tenant_id: str, actor_user_id: str, action: str, **meta: Any) -> None:
    """Audited in the Super admin's own workspace (write_audit_log commits). Never a secret."""
    write_audit_log(db, tenant_id=actor_tenant_id, actor_user_id=actor_user_id, action=f"platform.{action}",
                    resource_type="tenant", resource_id=actor_tenant_id, metadata={k: v for k, v in meta.items() if v is not None})


def decrypt(blob: Any) -> str | None:
    if not blob:
        return None
    try:
        return decrypt_secret(str(blob))
    except (InvalidToken, ValueError):
        logger.warning("platform_secret_unreadable")  # ENCRYPTION_KEY changed
        return None


def mask(secret: str | None) -> str | None:
    if not secret:
        return None
    return ("••••" + secret[-4:]) if len(secret) >= 8 else "••••"


# ---------------------------------------------------------------------------
# Super admin
# ---------------------------------------------------------------------------
def is_super_admin(db: Session, user_id: str) -> bool:
    return db.execute(text("SELECT 1 FROM platform_admins WHERE user_id = :u"), {"u": str(user_id)}).first() is not None


# ---------------------------------------------------------------------------
# Keys and app credentials: the admin screen first, then backend/.env
# ---------------------------------------------------------------------------
def _env(name: str | None) -> str:
    if not name:
        return ""
    raw = getattr(get_settings(), name, "")
    raw = raw.get_secret_value() if hasattr(raw, "get_secret_value") else raw
    raw = str(raw or "").strip()
    return "" if raw == "changeme" else raw


def value(group: str, field: str, db: Session | None = None) -> str:
    """The credential to use: the Super admin's value, else the .env setting, else ""."""
    _, env_name, secret = FIELDS[group][field]
    stored = get(group, db)
    own = decrypt(stored.get(f"{field}_enc")) if secret else (str(stored.get(field) or "").strip() or None)
    return own or _env(env_name)


def group_status(db: Session, group: str) -> dict[str, Any]:
    stored = get(group, db)
    fields = []
    for field, (label, env_name, secret) in FIELDS[group].items():
        own = decrypt(stored.get(f"{field}_enc")) if secret else (str(stored.get(field) or "").strip() or None)
        env = _env(env_name)
        current = own or env
        fields.append({
            "field": field, "label": label, "secret": secret,
            "set": bool(current), "source": "admin" if own else ("server" if env else None),
            "value": (mask(current) if secret else current) or None,
        })
    return {"group": group, "label": GROUP_LABEL[group], "fields": fields,
            "last_ok_at": stored.get("last_ok_at"), "last_error": stored.get("last_error")}


def save_group(db: Session, group: str, values: dict[str, str | None], clear: list[str], actor_tenant_id: str,
               actor_user_id: str) -> dict[str, Any]:
    """Set the given fields (a blank one is left as it is) and clear the listed ones."""
    if group not in FIELDS:
        raise AppError("Unknown setting.", 404)
    unknown = [f for f in [*values, *clear] if f not in FIELDS[group]]
    if unknown:
        raise AppError(f"Unknown field: {', '.join(unknown)}.", 422)
    stored = get(group, db)
    changed: list[str] = []
    for field, raw in values.items():
        if raw is None or not str(raw).strip():
            continue
        if FIELDS[group][field][2]:
            stored[f"{field}_enc"] = encrypt_secret(str(raw).strip())
        else:
            stored[field] = str(raw).strip()
        changed.append(field)
    for field in clear:
        stored.pop(f"{field}_enc", None)
        stored.pop(field, None)
        changed.append(field)
    if changed:
        stored.update(last_error=None)
    put(db, group, stored, actor_user_id)
    audit(db, actor_tenant_id, actor_user_id, "settings_saved", group=group, fields=sorted(set(changed)))
    return group_status(db, group)


# ---------------------------------------------------------------------------
# Which companies may use the software's keys (SPEC-BE-103)
# ---------------------------------------------------------------------------
# One row `company_access` = {tenant_id: {group: false}}. Only the Super admin
# writes it (a company can never switch itself back on). A company or group
# missing from the row is allowed, so every company keeps working by default;
# only an explicit false blocks.
ACCESS_KEY = "company_access"
ACCESS_GROUPS: dict[str, str] = {
    "ai": "AI (text, images, video, voice)",
    "socialapi": "SocialAPI",
    "zernio": "Zernio",
    "meta_app": "Meta (Facebook / Instagram) app",
    "tiktok_app": "TikTok app",
    "linkedin_app": "LinkedIn app",
    "sms": "SMS (Twilio)",
    "whatsapp": "WhatsApp Business",
}
BLOCKED: dict[str, str] = {
    "ai": "PilotSonic hasn't enabled AI for your company. Contact PilotSonic support.",
    "socialapi": "PilotSonic hasn't enabled SocialAPI for your company. Contact PilotSonic support.",
    "zernio": "PilotSonic hasn't enabled Zernio ads for your company. Contact PilotSonic support.",
    "meta_app": "PilotSonic hasn't enabled Facebook / Instagram sign-in for your company. Contact PilotSonic support.",
    "tiktok_app": "PilotSonic hasn't enabled TikTok sign-in for your company. Contact PilotSonic support.",
    "linkedin_app": "PilotSonic hasn't enabled LinkedIn sign-in for your company. Contact PilotSonic support.",
    "sms": "PilotSonic hasn't enabled SMS for your company. Contact PilotSonic support.",
    "whatsapp": "PilotSonic hasn't enabled WhatsApp for your company. Contact PilotSonic support.",
}


def allowed(tenant_id: str | None, group: str, db: Session | None = None) -> bool:
    """May this company use the software's `group` key? True without a company
    (server jobs that aren't a company's) and for anything not switched off."""
    if not tenant_id:
        return True
    return get(ACCESS_KEY, db).get(str(tenant_id), {}).get(group) is not False


def require(tenant_id: str | None, group: str, db: Session | None = None) -> None:
    if not allowed(tenant_id, group, db):
        raise AppError(BLOCKED[group], 403)


def _access_of(stored: dict[str, Any], tenant_id: str) -> dict[str, bool]:
    own = stored.get(str(tenant_id)) or {}
    return {g: own.get(g) is not False for g in ACCESS_GROUPS}


def list_companies(db: Session, q: str | None, page: int, page_size: int) -> dict[str, Any]:
    """Every company with its access switches and what it holds at the shared
    services (its SocialAPI brand, its Zernio profile)."""
    where = "WHERE (:q = '' OR t.name ILIKE :like OR t.slug ILIKE :like)"
    q = (q or "").strip()
    params: dict[str, Any] = {"q": q, "like": f"%{q}%"}
    total = db.execute(text(f"SELECT count(*) FROM tenants t {where}"), params).scalar() or 0
    rows = db.execute(
        text(f"SELECT t.id, t.name, t.slug, t.status, t.created_at, t.settings FROM tenants t {where} "
             "ORDER BY t.created_at DESC LIMIT :lim OFFSET :off"),
        {**params, "lim": page_size, "off": (page - 1) * page_size},
    ).all()
    stored = get(ACCESS_KEY, db)
    items = []
    for r in rows:
        settings = r.settings if isinstance(r.settings, dict) else {}
        sapi = settings.get("socialapi")
        sapi = sapi if isinstance(sapi, dict) else {}
        zern = settings.get("zernio")
        zern = zern if isinstance(zern, dict) else {}
        created = r.created_at.astimezone(timezone.utc) if r.created_at else None
        items.append({
            "tenant_id": str(r.id), "name": r.name, "slug": r.slug, "status": str(r.status),
            "created_at": created, "access": _access_of(stored, str(r.id)),
            "socialapi_brand": bool(sapi.get("brand_id")), "socialapi_error": sapi.get("last_error") or None,
            "zernio_profile": bool(zern.get("profile_id")),
        })
    return {"items": items, "total": int(total), "page": page, "page_size": page_size,
            "groups": [{"group": g, "label": label} for g, label in ACCESS_GROUPS.items()]}


def set_access(db: Session, tenant_id: str, changes: dict[str, bool], actor_tenant_id: str,
               actor_user_id: str) -> dict[str, bool]:
    """Switch groups on/off for one company. On = the entry is removed (the default)."""
    unknown = [g for g in changes if g not in ACCESS_GROUPS]
    if unknown:
        raise AppError(f"Unknown access: {', '.join(unknown)}.", 422)
    exists = db.execute(text("SELECT 1 FROM tenants WHERE id = CAST(:t AS uuid)"), {"t": str(tenant_id)}).first()
    if exists is None:
        raise AppError("Company not found.", 404)
    stored = get(ACCESS_KEY, db)
    own = dict(stored.get(str(tenant_id)) or {})
    for group, on in changes.items():
        if on:
            own.pop(group, None)
        else:
            own[group] = False
    if own:
        stored[str(tenant_id)] = own
    else:
        stored.pop(str(tenant_id), None)
    put(db, ACCESS_KEY, stored, actor_user_id)
    audit(db, actor_tenant_id, actor_user_id, "company_access_saved", company=str(tenant_id),
          enabled=sorted(g for g, on in changes.items() if on) or None,
          disabled=sorted(g for g, on in changes.items() if not on) or None)
    return _access_of(stored, str(tenant_id))


def record(db: Session, group: str, error: str | None) -> None:
    """Remember a test's outcome on the group (commits)."""
    stored = get(group, db)
    stored["last_error"] = error[:300] if error else None
    if error is None:
        stored["last_ok_at"] = datetime.now(timezone.utc).isoformat()
    put(db, group, stored, None)
    db.commit()



# ---------------------------------------------------------------------------
# App branding (SPEC-BE-113): the software's own name and logo, set by the Super
# admin, readable by anyone (the login page shows it). Images are data URLs.
# ---------------------------------------------------------------------------
BRANDING_KEY = "app_branding"
DEFAULT_APP_NAME = "PilotSonic"
BRANDING_SLOTS = ("logo", "logo_dark", "favicon")


def app_branding(db: Session | None = None) -> dict[str, Any]:
    stored = get(BRANDING_KEY, db)
    return {
        "app_name": str(stored.get("app_name") or DEFAULT_APP_NAME),
        "tagline": stored.get("tagline") or None,
        "logo_url": stored.get("logo") or None,
        "logo_dark_url": stored.get("logo_dark") or None,
        "favicon_url": stored.get("favicon") or None,
    }


def set_app_branding(db: Session, changes: dict[str, Any], actor_tenant_id: str, actor_user_id: str) -> dict[str, Any]:
    stored = get(BRANDING_KEY, db)
    for key, value in changes.items():
        if value is None or (isinstance(value, str) and not value.strip()):
            stored.pop(key, None)
        else:
            stored[key] = value.strip() if isinstance(value, str) else value
    put(db, BRANDING_KEY, stored, actor_user_id)
    audit(db, actor_tenant_id, actor_user_id, "app_branding_saved", fields=sorted(changes))
    clear_cache()
    return app_branding(db)


def set_app_branding_image(db: Session, slot: str, data: bytes, actor_tenant_id: str,
                           actor_user_id: str) -> dict[str, Any]:
    import base64

    from app.services.tenant_service import MAX_IMAGE_BYTES, _image_mime

    if not data:
        raise AppError("The file is empty.", 422)
    if len(data) > MAX_IMAGE_BYTES:
        raise AppError("The image must be 1 MB or smaller.", 422)
    mime = _image_mime(data)
    if mime is None:
        raise AppError("Only PNG, JPEG or WebP images are allowed.", 422)
    url = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    return set_app_branding(db, {slot: url}, actor_tenant_id, actor_user_id)


# ---------------------------------------------------------------------------
# Integration health and errors (SPEC-BE-113 FR3). Counts and messages only,
# never a credential.
# ---------------------------------------------------------------------------
HEALTH_REQUIRED: dict[str, tuple[str, ...]] = {
    "meta_app": ("app_id", "app_secret"), "tiktok_app": ("client_key", "client_secret"),
    "linkedin_app": ("client_id", "client_secret"), "socialapi": ("api_key",), "zernio": ("api_key",),
    "twilio": ("account_sid", "auth_token"), "whatsapp_app": ("config_id", "verify_token"),
}
_HEALTH_PROVIDERS: dict[str, tuple[str, ...]] = {
    "meta_app": ("meta_ads", "facebook", "instagram"), "tiktok_app": ("tiktok", "tiktok_ads"),
    "linkedin_app": ("linkedin", "linkedin_ads"), "whatsapp_app": ("whatsapp",),
}


def integration_health(db: Session) -> list[dict[str, Any]]:
    out = []
    for group, required in HEALTH_REQUIRED.items():
        stored = get(group, db)
        configured = all(value(group, f, db) for f in required)
        if group in _HEALTH_PROVIDERS:
            row = db.execute(text(
                "SELECT count(DISTINCT tenant_id) FILTER (WHERE status = 'connected'), "
                "count(DISTINCT tenant_id) FILTER (WHERE status IN ('error', 'expired') OR last_error IS NOT NULL) "
                "FROM integrations WHERE provider::text = ANY(:p)"), {"p": list(_HEALTH_PROVIDERS[group])}).one()
            connected, errors = int(row[0]), int(row[1])
        elif group == "socialapi":
            row = db.execute(text(
                "SELECT count(*) FILTER (WHERE settings->'socialapi'->>'brand_id' IS NOT NULL), "
                "count(*) FILTER (WHERE settings->'socialapi'->>'last_error' IS NOT NULL) FROM tenants")).one()
            connected, errors = int(row[0]), int(row[1])
        elif group == "zernio":
            connected = int(db.execute(text(
                "SELECT count(*) FROM tenants WHERE settings->'zernio'->>'profile_id' IS NOT NULL")).scalar() or 0)
            errors = 0
        else:  # twilio
            connected = int(db.execute(text(
                "SELECT count(*) FROM tenants WHERE settings->'sms'->>'number' IS NOT NULL")).scalar() or 0)
            errors = int(db.execute(text(
                "SELECT count(DISTINCT tenant_id) FROM sms_messages WHERE status IN ('failed', 'undelivered') "
                "AND created_at > now() - interval '7 days'")).scalar() or 0)
        out.append({"provider": group, "label": GROUP_LABEL[group], "configured": configured,
                    "last_ok_at": stored.get("last_ok_at"), "last_error": stored.get("last_error"),
                    "companies_connected": connected, "companies_with_errors": errors})
    return out


_ERRORS_SQL = """
  SELECT * FROM (
    SELECT i.updated_at AS at, i.provider::text AS provider, 'connection' AS kind, i.tenant_id, t.name,
           i.last_error AS message
      FROM integrations i JOIN tenants t ON t.id = i.tenant_id WHERE i.last_error IS NOT NULL
    UNION ALL
    SELECT w.received_at, w.provider::text, CASE WHEN w.signature_valid = false THEN 'invalid_signature'
           ELSE 'webhook' END, w.tenant_id, t.name,
           coalesce(w.processing_error, 'A webhook arrived with an invalid signature and was refused.')
      FROM webhook_events w LEFT JOIN tenants t ON t.id = w.tenant_id
     WHERE w.signature_valid = false OR w.processing_error IS NOT NULL
    UNION ALL
    SELECT s.updated_at, 'twilio', 'sms_failed', s.tenant_id, t.name,
           coalesce(s.error_message, 'SMS ' || s.status)
      FROM sms_messages s JOIN tenants t ON t.id = s.tenant_id WHERE s.status IN ('failed', 'undelivered')
  ) e
  WHERE (CAST(:p AS text) IS NULL OR e.provider = :p OR (:p = 'meta_app' AND e.provider IN ('meta_ads', 'facebook', 'instagram'))
         OR (:p = 'whatsapp_app' AND e.provider = 'whatsapp'))
  ORDER BY e.at DESC LIMIT :lim OFFSET :off
"""


def integration_errors(db: Session, provider: str | None, offset: int, limit: int = 50) -> dict[str, Any]:
    rows = db.execute(text(_ERRORS_SQL), {"p": provider, "lim": limit + 1, "off": offset}).all()
    items = [{"at": r.at.astimezone(timezone.utc), "provider": r.provider, "kind": r.kind,
              "company_id": str(r.tenant_id) if r.tenant_id else None, "company_name": r.name,
              "message": str(r.message)[:500]} for r in rows[:limit]]
    return {"items": items, "next_cursor": str(offset + limit) if len(rows) > limit else None}
