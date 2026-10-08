"""SocialAPI.ai as another way to post and answer on social media (SPEC-BE-083).

Self-contained next to the direct integrations (SPEC-BE-075/080), which are
unchanged: posts made here live in SocialAPI (not in organic_contents /
scheduled_posts), and the inbox is read live from SocialAPI (not copied into
conversations), so nothing else in the app sees or changes them.

Storage: tenants.settings["socialapi"] = {key_enc, brand_id, last_ok_at,
last_error}. The key is Fernet-encrypted (utils/crypto), never returned (only
masked) and never logged. Same pattern as the AI Models keys: no DDL needed.

Brand: SocialAPI groups connected accounts into brands. The company's
accounts are connected into one brand (found by the company name, else
created) whose id is stored; listing shows every account the key can reach.

Audit rows use resource_type "tenant" (audit_log.resource_id is a uuid; the
SocialAPI ids go into metadata). Message/comment/review text is never logged.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from cryptography.fernet import InvalidToken
from jose import JWTError, jwt  # type: ignore[import-untyped]  # no stubs (baseline)
from sqlalchemy.orm import Session

from app.ai.prompts.reply_drafter import HistoryMessage, generate_reply_draft
from app.config import get_settings
from app.core.audit import write_audit_log
from app.core.exceptions import AppError, NotFoundError
from app.integrations import socialapi as api
from app.models.tenant import Tenant
from app.schemas import socialapi as s
from app.services import media_service
from app.utils.crypto import decrypt_secret, encrypt_secret

logger = structlog.get_logger(__name__)

SETTINGS_KEY = "socialapi"
STATE_TYPE = "socialapi_connect"
STATE_TTL = timedelta(minutes=30)
BAD_STATE = "This connection link expired or is invalid; start Connect again."
NO_KEY = "Add your SocialAPI key first (Organic Marketing › SocialAPI)."
LABEL = {
    "instagram": "Instagram", "facebook": "Facebook", "threads": "Threads", "tiktok": "TikTok",
    "linkedin": "LinkedIn", "youtube": "YouTube", "twitter": "X (Twitter)", "bluesky": "Bluesky",
    "pinterest": "Pinterest", "google": "Google Business Profile", "telegram": "Telegram",
    "whatsapp": "WhatsApp", "zalo": "Zalo",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _tenant(db: Session, tenant_id: str) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant not found.")
    return tenant


def _config(tenant: Tenant) -> dict[str, Any]:
    return dict((tenant.settings or {}).get(SETTINGS_KEY) or {})


def _save(tenant: Tenant, config: dict[str, Any]) -> None:
    # Reassign a new dict so SQLAlchemy sees the jsonb change.
    settings = dict(tenant.settings or {})
    settings[SETTINGS_KEY] = config
    tenant.settings = settings


def _decrypt(config: dict[str, Any]) -> str | None:
    blob = config.get("key_enc")
    if not blob:
        return None
    try:
        return decrypt_secret(blob)
    except (InvalidToken, ValueError):
        logger.warning("socialapi_key_unreadable")  # ENCRYPTION_KEY changed
        return None


def _key(db: Session, tenant_id: str) -> str:
    key = _decrypt(_config(_tenant(db, tenant_id)))
    if key is None:
        raise AppError(NO_KEY, 409)
    return key


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ts(raw: Any) -> datetime | None:
    """SocialAPI timestamps (RFC3339) -> aware UTC; unreadable -> None."""
    if not raw or not isinstance(raw, str):
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _int(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _str(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def _record(db: Session, tenant_id: str, error: str | None) -> None:
    """Remember the key's last outcome for the key card (own commit)."""
    tenant = _tenant(db, tenant_id)
    config = _config(tenant)
    if not config.get("key_enc"):
        return
    config["last_error"] = error
    if error is None:
        config["last_ok_at"] = _now().isoformat()
    _save(tenant, config)
    db.commit()


def _call(db: Session, tenant_id: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a client call with the company's key; SocialAPI errors -> AppError
    with SocialAPI's message. A rejected key is recorded on the key card."""
    key = _key(db, tenant_id)
    try:
        return fn(key, *args, **kwargs)
    except api.SocialAPIError as exc:
        if exc.auth:
            _record(db, tenant_id, exc.message)
        logger.warning("socialapi_call_failed", tenant_id=tenant_id, call=getattr(fn, "__name__", "?"),
                       status=exc.status_code, code=exc.code)
        raise AppError(exc.message, exc.status_code) from None


def _audit(db: Session, tenant_id: str, actor: str, action: str, **meta: Any) -> None:
    # write_audit_log commits. Never any key or message text in the metadata.
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor, action=f"socialapi.{action}",
                    resource_type="tenant", resource_id=tenant_id, metadata={k: v for k, v in meta.items() if v is not None})


# ---------------------------------------------------------------------------
# Key
# ---------------------------------------------------------------------------
def key_status(db: Session, tenant_id: str, account_count: int | None = None) -> dict[str, Any]:
    config = _config(_tenant(db, tenant_id))
    key = _decrypt(config)
    status = "not_configured" if key is None else ("error" if config.get("last_error") else "connected")
    return {
        "status": status,
        "key_masked": (("••••" + key[-4:]) if len(key) >= 8 else "••••") if key else None,
        "last_ok_at": _ts(config.get("last_ok_at")) if key else None,
        "last_error": config.get("last_error") if key else None,
        "account_count": account_count,
        "docs_url": api.DOCS_URL,
    }


def save_key(db: Session, tenant_id: str, actor: str, api_key: str) -> dict[str, Any]:
    """Test first (GET /accounts): a key SocialAPI rejects is not saved (422).
    A network / SocialAPI outage still saves it, with the error shown."""
    key = api_key.strip()
    error: str | None = None
    count: int | None = None
    try:
        count = len(api.list_accounts(key))
    except api.SocialAPIError as exc:
        if exc.auth:
            raise AppError(exc.message, 422) from None
        error = exc.message
    tenant = _tenant(db, tenant_id)
    config = _config(tenant)
    if _decrypt(config) != key:
        config.pop("brand_id", None)  # another SocialAPI account: find / create its brand again
    config.update({"key_enc": encrypt_secret(key), "last_error": error})
    if error is None:
        config["last_ok_at"] = _now().isoformat()
    _save(tenant, config)
    _audit(db, tenant_id, actor, "key_saved", verified=error is None)
    logger.info("socialapi_key_saved", tenant_id=tenant_id, verified=error is None)
    return key_status(db, tenant_id, count)


def test_key(db: Session, tenant_id: str, actor: str) -> dict[str, Any]:
    key = _key(db, tenant_id)
    count: int | None = None
    try:
        count = len(api.list_accounts(key))
        error = None
    except api.SocialAPIError as exc:
        error = exc.message
    _record(db, tenant_id, error)
    _audit(db, tenant_id, actor, "key_tested", verified=error is None)
    return key_status(db, tenant_id, count)


def delete_key(db: Session, tenant_id: str, actor: str) -> None:
    tenant = _tenant(db, tenant_id)
    if not _config(tenant).get("key_enc"):
        raise NotFoundError("No SocialAPI key is saved.")
    # The accounts stay connected in SocialAPI; only this app forgets the key.
    _save(tenant, {})
    _audit(db, tenant_id, actor, "key_removed")


# ---------------------------------------------------------------------------
# Accounts and the connect flow
# ---------------------------------------------------------------------------
def _account(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(a.get("id") or ""),
        "platform": str(a.get("platform") or ""),
        "name": _str(a.get("name")),
        "username": _str(a.get("username")),
        "status": str(a.get("status") or "active"),
        "avatar_url": _str(a.get("profile_picture_url")),
        "page_name": _str(a.get("page_name")),
        "login_id": _str(a.get("login_id")),
        "reconnect_reason": _str(a.get("reconnect_reason")),
    }


def _connectable() -> list[dict[str, str]]:
    return [{"platform": p, "label": LABEL[p]} for p in api.OAUTH_PLATFORMS]


def list_accounts(db: Session, tenant_id: str) -> dict[str, Any]:
    if _decrypt(_config(_tenant(db, tenant_id))) is None:
        return {"configured": False, "items": [], "connectable": _connectable()}
    rows = _call(db, tenant_id, api.list_accounts)
    items = sorted((_account(a) for a in rows if a.get("id")), key=lambda a: (a["platform"], a["name"] or ""))
    return {"configured": True, "items": items, "connectable": _connectable()}


def _accounts_by_id(db: Session, tenant_id: str) -> dict[str, dict[str, Any]]:
    return {a["id"]: a for a in list_accounts(db, tenant_id)["items"]}


def _brand_id(db: Session, tenant_id: str, key: str) -> str:
    tenant = _tenant(db, tenant_id)
    config = _config(tenant)
    if config.get("brand_id"):
        return str(config["brand_id"])
    try:
        brand = next((b for b in api.list_brands(key) if (b.get("name") or "").strip() == tenant.name.strip()), None)
        brand = brand or api.create_brand(key, tenant.name[:100])
    except api.SocialAPIError as exc:
        raise AppError(exc.message, exc.status_code) from None
    brand_id = _str(brand.get("id") or brand.get("brand_id")) if isinstance(brand, dict) else None
    if not brand_id:
        raise AppError("SocialAPI didn't return a brand for this company.", 502)
    config["brand_id"] = brand_id
    _save(tenant, config)
    db.commit()
    return brand_id


def _redirect_uri() -> str:
    return get_settings().FRONTEND_BASE_URL.rstrip("/") + "/marketing/organic/socialapi/callback"


def _state(tenant_id: str, actor: str, platform: str) -> str:
    st = get_settings()
    claims = {"typ": STATE_TYPE, "t": str(tenant_id), "u": str(actor), "p": platform, "exp": _now() + STATE_TTL}
    return str(jwt.encode(claims, st.SECRET_KEY.get_secret_value(), algorithm=st.JWT_ALGORITHM))


def _check_state(tenant_id: str, actor: str, state: str) -> dict[str, Any]:
    st = get_settings()
    try:
        claims = jwt.decode(state, st.SECRET_KEY.get_secret_value(), algorithms=[st.JWT_ALGORITHM])
    except JWTError:
        raise AppError(BAD_STATE, 400) from None
    if claims.get("typ") != STATE_TYPE or claims.get("t") != str(tenant_id) or claims.get("u") != str(actor):
        raise AppError(BAD_STATE, 400)
    return dict(claims)


def connect(db: Session, tenant_id: str, actor: str, platform: str) -> dict[str, Any]:
    key = _key(db, tenant_id)
    brand_id = _brand_id(db, tenant_id, key)
    result = _call(db, tenant_id, api.connect, platform, brand_id, _redirect_uri(), _state(tenant_id, actor, platform))
    _audit(db, tenant_id, actor, "connect_started", platform=platform)
    auth_url = _str(result.get("auth_url")) if isinstance(result, dict) else None
    if auth_url:
        return {"auth_url": auth_url, "account": None}
    if isinstance(result, dict) and (result.get("account_id") or result.get("id")):
        return {"auth_url": None, "account": _account({**result, "id": result.get("account_id") or result.get("id"),
                                                       "name": result.get("display_name") or result.get("name")})}
    raise AppError("SocialAPI didn't return a sign-in link.", 502)


def callback(db: Session, tenant_id: str, actor: str, payload: s.CallbackRequest) -> dict[str, Any]:
    claims = _check_state(tenant_id, actor, payload.state)
    platform = payload.platform or str(claims.get("p") or "")
    if payload.status == "error":
        reason = payload.error_description or payload.error or "the sign-in was cancelled"
        raise AppError(f"{LABEL.get(platform, platform)} didn't connect: {reason}", 422)
    if payload.status == "selection_required":
        if platform not in ("facebook", "google") or not payload.connection_id:
            raise AppError("SocialAPI asked for a choice this app can't show; finish it in SocialAPI's dashboard.", 422)
        choices = _call(db, tenant_id, api.pending_choices, platform, payload.connection_id)
        return {"status": "selection_required", "platform": platform, "account_id": None,
                "connection_id": payload.connection_id, "choices": choices}
    _audit(db, tenant_id, actor, "account_connected", platform=platform, account_id=payload.account_id)
    return {"status": "connected", "platform": platform, "account_id": payload.account_id,
            "connection_id": None, "choices": []}


def select(db: Session, tenant_id: str, actor: str, payload: s.SelectRequest) -> dict[str, Any]:
    _check_state(tenant_id, actor, payload.state)
    # The brand was set when the sign-in started (connect); the pending
    # connection is promoted into an account of that brand.
    result = _call(db, tenant_id, api.select_pending, payload.platform, payload.connection_id, payload.choice_id)
    account_id = _str(result.get("account_id")) if isinstance(result, dict) else None
    _audit(db, tenant_id, actor, "account_connected", platform=payload.platform, account_id=account_id)
    return {"account_id": account_id}


def _facebook_login(db: Session, tenant_id: str, account_id: str) -> tuple[dict[str, Any], str]:
    account = _accounts_by_id(db, tenant_id).get(account_id)
    if account is None or account["platform"] != "facebook":
        raise NotFoundError("Facebook account not found.")
    if not account["login_id"]:
        raise AppError("SocialAPI didn't say which Facebook login this is; connect Facebook again.", 409)
    return account, account["login_id"]


def facebook_pages(db: Session, tenant_id: str, account_id: str) -> dict[str, Any]:
    """The Pages a connected Facebook login manages. The account's name is the
    login's own (personal) name; page_name is set only once one Page is active."""
    _, login_id = _facebook_login(db, tenant_id, account_id)
    return {"items": _call(db, tenant_id, api.login_choices, "facebook", login_id)}


def choose_facebook_page(db: Session, tenant_id: str, actor: str, account_id: str, page_id: str) -> dict[str, Any]:
    """Assign one of the login's Pages to the company's brand, so posts go to it."""
    _, login_id = _facebook_login(db, tenant_id, account_id)
    brand_id = _brand_id(db, tenant_id, _key(db, tenant_id))
    result = _call(db, tenant_id, api.assign_choice, "facebook", login_id, page_id, brand_id)
    new_id = (_str(result.get("account_id")) if isinstance(result, dict) else None) or account_id
    _audit(db, tenant_id, actor, "facebook_page_chosen", account_id=new_id, page_id=page_id)
    return {"account_id": new_id}


def disconnect(db: Session, tenant_id: str, actor: str, account_id: str) -> None:
    accounts = _accounts_by_id(db, tenant_id)
    if account_id not in accounts:
        raise NotFoundError("Account not found.")
    _call(db, tenant_id, api.disconnect, account_id)
    _audit(db, tenant_id, actor, "account_disconnected", platform=accounts[account_id]["platform"], account_id=account_id)


def boards(db: Session, tenant_id: str, account_id: str) -> dict[str, Any]:
    rows = _call(db, tenant_id, api.boards, account_id)
    return {"items": [
        {"id": str(b.get("id") or b.get("board_id")), "board_id": str(b.get("board_id") or b.get("id")),
         "name": str(b.get("name") or b.get("board_id") or ""), "privacy": _str(b.get("privacy"))}
        for b in rows if b.get("board_id") or b.get("id")
    ]}


def account_analytics(db: Session, tenant_id: str, account_id: str, days: int) -> dict[str, Any]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days - 1)
    data = _call(db, tenant_id, api.account_analytics, account_id, start.isoformat(), end.isoformat())
    series = []
    for row in data.get("series") or []:
        if not isinstance(row, dict) or not row.get("metric"):
            continue
        points = [
            # A point SocialAPI didn't report stays null - never estimated.
            {"day": str(p.get("day")), "value": float(p["value"]) if isinstance(p.get("value"), (int, float)) else None}
            for p in (row.get("points") or []) if isinstance(p, dict) and p.get("day")
        ]
        series.append({"metric": str(row["metric"]), "kind": _str(row.get("kind")), "points": points})
    return {"account_id": account_id, "start": str(data.get("from") or start), "end": str(data.get("to") or end),
            "series": series}


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------
def _target(t: dict[str, Any]) -> dict[str, Any]:
    err = t.get("error") if isinstance(t.get("error"), dict) else None
    m = t.get("metrics") if isinstance(t.get("metrics"), dict) else None
    return {
        "account_id": str(t.get("account_id") or ""),
        "platform": _str(t.get("platform")),
        "status": _str(t.get("status")),
        "permalink": _str(t.get("permalink")),
        "platform_post_id": _str(t.get("platform_post_id")),
        "published_at": _ts(t.get("published_at")),
        "scheduled_at": _ts(t.get("scheduled_at")),
        "error": _str(err.get("message")) if err else None,
        "metrics": {k: _int(m.get(k)) for k in ("likes", "comments", "shares", "saves")} if m else None,
        "metrics_synced_at": _ts(t.get("metrics_synced_at")),
    }


def _post(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(p.get("id") or ""),
        "status": str(p.get("status") or "unknown"),
        "text": _str(p.get("text")),
        "title": _str(p.get("title")),
        "media_count": len(p.get("media") or []) if isinstance(p.get("media"), list) else 0,
        "created_at": _ts(p.get("created_at")),
        "scheduled_at": _ts(p.get("scheduled_at")),
        "published_at": _ts(p.get("published_at")),
        "targets": [_target(t) for t in (p.get("targets") or []) if isinstance(t, dict)],
    }


def create_post(db: Session, tenant_id: str, actor: str, payload: s.PostCreate) -> dict[str, Any]:
    accounts = _accounts_by_id(db, tenant_id)
    unknown = [t.account_id for t in payload.targets if t.account_id not in accounts]
    if unknown:
        raise AppError("Pick accounts from the connected list (some aren't connected in SocialAPI).", 422)
    for t in payload.targets:
        if accounts[t.account_id]["platform"] == "pinterest" and not t.board_id:
            raise AppError("Pinterest needs a board: pick one for each Pinterest account.", 422)
    rows = media_service.media_rows(db, tenant_id, payload.media_ids)
    key = _key(db, tenant_id)
    media: list[dict[str, str]] = []
    for m in rows:
        # Our library file -> SocialAPI's storage (uploaded ids are safer than
        # URLs for scheduled posts, per SocialAPI's media guide).
        try:
            media_id = api.upload_media(key, m.name or f"media-{m.id}", m.mime, media_service.read_bytes(m))
        except api.SocialAPIError as exc:
            raise AppError(exc.message, exc.status_code) from None
        media.append({"source_type": "media_id", "source": media_id})
    body: dict[str, Any] = {
        "text": payload.text,
        "targets": [{k: v for k, v in {"account_id": t.account_id, "board_id": t.board_id}.items() if v} for t in payload.targets],
    }
    if payload.title:
        body["title"] = payload.title
    if media:
        body["media"] = media
    if payload.first_comment:
        body["first_comment"] = payload.first_comment
    if payload.mode == "now":
        body["publish_now"] = True
    elif payload.mode == "schedule" and payload.scheduled_at is not None:
        body["scheduled_at"] = payload.scheduled_at.isoformat().replace("+00:00", "Z")
    post = _post(_call(db, tenant_id, api.create_post, body))
    _audit(db, tenant_id, actor, "post_created", post_id=post["id"], mode=payload.mode, status=post["status"],
           platforms=sorted({accounts[t.account_id]["platform"] for t in payload.targets}), media=len(media))
    logger.info("socialapi_post_created", tenant_id=tenant_id, mode=payload.mode, targets=len(payload.targets))
    return post


def list_posts(db: Session, tenant_id: str, status: str | None, platform: str | None, q: str | None,
               cursor: str | None) -> dict[str, Any]:
    rows, nxt = _call(db, tenant_id, api.list_posts, status=status, platform=platform, search=q, cursor=cursor)
    return {"items": [_post(p) for p in rows if p.get("id")], "next_cursor": nxt}


def get_post(db: Session, tenant_id: str, post_id: str) -> dict[str, Any]:
    post = _post(_call(db, tenant_id, api.get_post, post_id))
    # Fresh per-account results (likes, comments, shares, saves) when SocialAPI has them.
    if post["status"] in ("published", "partial"):
        try:
            fresh = {str(t.get("account_id")): _target(t) for t in api.post_metrics(_key(db, tenant_id), post_id)}
        except api.SocialAPIError:
            fresh = {}
        for t in post["targets"]:
            got = fresh.get(t["account_id"])
            if got and got["metrics"] is not None:
                t["metrics"], t["metrics_synced_at"] = got["metrics"], got["metrics_synced_at"]
    return post


def publish_post(db: Session, tenant_id: str, actor: str, post_id: str) -> dict[str, Any]:
    _call(db, tenant_id, api.publish_post, post_id)
    _audit(db, tenant_id, actor, "post_published", post_id=post_id)
    return get_post(db, tenant_id, post_id)


def retry_post(db: Session, tenant_id: str, actor: str, post_id: str) -> dict[str, Any]:
    _call(db, tenant_id, api.retry_post, post_id)
    _audit(db, tenant_id, actor, "post_retried", post_id=post_id)
    return get_post(db, tenant_id, post_id)


def delete_post(db: Session, tenant_id: str, actor: str, post_id: str) -> dict[str, Any]:
    """Draft / scheduled / failed: removed. Published: deleted on every platform
    that allows it; the rest keep their copy (reported per account)."""
    body = _call(db, tenant_id, api.delete_post, post_id)
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    raw = body.get("results") or data.get("results") or []
    results = [
        {"account_id": _str(r.get("account_id")), "outcome": _str(r.get("status") or r.get("outcome")),
         "message": _str(r.get("message"))}
        for r in (raw if isinstance(raw, list) else []) if isinstance(r, dict)
    ]
    ok = bool(body.get("success", data.get("success", True)))
    _audit(db, tenant_id, actor, "post_deleted", post_id=post_id, ok=ok)
    return {"ok": ok, "results": results}


def constraints(db: Session, tenant_id: str) -> dict[str, Any]:
    data = _call(db, tenant_id, api.constraints, None)
    items = []
    for platform, c in sorted(data.items()):
        if not isinstance(c, dict):
            continue
        text_, carousel, media, sched = (_dict(c.get(k)) for k in ("text", "carousel", "media", "scheduling"))
        items.append({
            "platform": platform,
            "text_max_length": _int(text_.get("max_length")),
            "carousel_max_items": _int(carousel.get("max_items")) if carousel.get("supported") else None,
            "max_video_duration_sec": _int(media.get("max_video_duration_sec")),
            "scheduling_supported": sched.get("supported") if isinstance(sched.get("supported"), bool) else None,
        })
    return {"items": items}


# ---------------------------------------------------------------------------
# Inbox (read live from SocialAPI)
# ---------------------------------------------------------------------------
def conversations(db: Session, tenant_id: str, platform: str | None, account_id: str | None, status: str | None,
                  cursor: str | None) -> dict[str, Any]:
    out = _call(db, tenant_id, api.conversations, platform=platform, account_id=account_id, status=status, cursor=cursor)
    items = [
        {
            "id": str(c["id"]),
            "account_id": _str(c.get("account_id")),
            "platform": _str(c.get("platform")),
            "participant_name": _str(c.get("participant_name")),
            "participant_picture": _str(c.get("participant_picture")),
            "last_message": _str(c.get("last_message")),
            "last_message_at": _ts(c.get("last_message_at")),
            "unread_count": _int(c.get("unread_count")) or 0,
            "status": _str(c.get("status")),
        }
        for c in out["items"] if c.get("id")
    ]
    return {"items": items, "next_cursor": out["next_cursor"], "sync_state": _str(out.get("sync_state"))}


def messages(db: Session, tenant_id: str, conversation_id: str, cursor: str | None) -> dict[str, Any]:
    out = _call(db, tenant_id, api.messages, conversation_id, cursor)
    items = [
        {
            "id": str(m["id"]),
            "text": _str(m.get("text")),
            "direction": _str(m.get("direction")),
            "sender_name": _str(m.get("sender_name")),
            "status": _str(m.get("status")),
            "created_at": _ts(m.get("created_at")),
            "attachment_type": _str(m.get("attachment_type")),
            "attachment_url": _str(m.get("attachment_url")),
        }
        for m in out["items"] if m.get("id")
    ]
    # Oldest first, as a chat reads.
    items.sort(key=lambda m: m["created_at"] or datetime.min.replace(tzinfo=timezone.utc))
    return {"items": items, "next_cursor": out["next_cursor"]}


def send_message(db: Session, tenant_id: str, actor: str, conversation_id: str, payload: s.SendMessage) -> dict[str, Any]:
    # Instagram / Facebook only allow replies within 24 h of the customer's
    # last message; SocialAPI's "messaging window closed" error is shown as is.
    out = _call(db, tenant_id, api.send_message, conversation_id, payload.account_id, payload.text)
    _audit(db, tenant_id, actor, "message_sent", conversation_id=conversation_id, account_id=payload.account_id)
    return {"ok": bool(out.get("success", True)), "message": None}


def commented_posts(db: Session, tenant_id: str, platform: str | None, account_id: str | None,
                    cursor: str | None) -> dict[str, Any]:
    out = _call(db, tenant_id, api.commented_posts, platform=platform, account_id=account_id, cursor=cursor)
    items = [
        {
            "id": str(p.get("id") or p.get("platform_id")),
            "platform_id": str(p.get("platform_id") or p.get("id")),
            "account_id": _str(p.get("account_id")),
            "platform": _str(p.get("platform")),
            "content": _str(p.get("content")),
            "permalink": _str(p.get("permalink")),
            "thumbnail": _str(p.get("thumbnail")),
            "comment_count": _int(p.get("comment_count")) or 0,
            "published_at": _ts(p.get("published_at")),
        }
        for p in out["items"] if p.get("id") or p.get("platform_id")
    ]
    return {"items": items, "next_cursor": out["next_cursor"]}


def comments(db: Session, tenant_id: str, post_id: str, account_id: str, cursor: str | None) -> dict[str, Any]:
    out = _call(db, tenant_id, api.comments, post_id, account_id, cursor)
    items = []
    for c in out["items"]:
        if not c.get("id"):
            continue
        caps = c.get("capabilities") if isinstance(c.get("capabilities"), dict) else {}
        items.append({
            "id": str(c["id"]),
            "text": _str(c.get("text")),
            "author_name": _str(c.get("author_name")),
            "author_username": _str(c.get("author_username")),
            "author_picture": _str(c.get("author_picture")),
            "created_at": _ts(c.get("created_at")),
            "like_count": _int(c.get("like_count")) or 0,
            "reply_count": _int(c.get("reply_count")) or 0,
            "parent_id": _str(c.get("parent_id")),
            "is_hidden": bool(c.get("is_hidden")),
            "is_owner": bool(c.get("is_owner")),
            # Missing capabilities = allowed: SocialAPI answers 501 if not.
            "can_reply": bool(caps.get("can_reply", True)),
            "can_delete": bool(caps.get("can_delete", True)),
            "can_hide": bool(caps.get("can_hide", True)),
        })
    return {"items": items, "next_cursor": out["next_cursor"]}


def reply_comment(db: Session, tenant_id: str, actor: str, post_id: str, payload: s.CommentReply) -> dict[str, Any]:
    _call(db, tenant_id, api.reply_comment, post_id, payload.account_id, payload.comment_id, payload.text)
    _audit(db, tenant_id, actor, "comment_replied", post_id=post_id, comment_id=payload.comment_id, account_id=payload.account_id)
    return {"ok": True, "message": None}


def moderate_comment(db: Session, tenant_id: str, actor: str, post_id: str, comment_id: str,
                     payload: s.CommentAction) -> dict[str, Any]:
    _call(db, tenant_id, api.moderate_comment, post_id, comment_id, payload.account_id, payload.action)
    _audit(db, tenant_id, actor, f"comment_{payload.action}", post_id=post_id, comment_id=comment_id, account_id=payload.account_id)
    return {"ok": True, "message": None}


def reviews(db: Session, tenant_id: str, account_id: str, cursor: str | None) -> dict[str, Any]:
    out = _call(db, tenant_id, api.reviews, account_id, cursor)
    items = []
    for r in out["items"]:
        if not r.get("id"):
            continue
        author = r.get("author") if isinstance(r.get("author"), dict) else {}
        reply = r.get("reply") if isinstance(r.get("reply"), dict) else {}
        items.append({
            "id": str(r["id"]),
            "author_name": _str(author.get("name") or author.get("username")),
            "author_avatar": _str(author.get("avatar_url")),
            "rating": _int(r.get("rating")),
            "text": _str(r.get("text")),
            "created_at": _ts(r.get("created_at")),
            "reply_text": _str(reply.get("text")),
            "reply_state": _str(reply.get("state")),
        })
    summary = out.get("summary") or {}
    avg = summary.get("average_rating")
    return {"items": items, "next_cursor": out["next_cursor"],
            "average_rating": float(avg) if isinstance(avg, (int, float)) else None,
            "total_count": _int(summary.get("total_count"))}


def reply_review(db: Session, tenant_id: str, actor: str, review_id: str, payload: s.ReviewReply) -> dict[str, Any]:
    out = _call(db, tenant_id, api.reply_review, review_id, payload.account_id, payload.text)
    _audit(db, tenant_id, actor, "review_replied", review_id=review_id, account_id=payload.account_id)
    state = _str(out.get("state"))
    # Google moderates review replies: PENDING until it approves them.
    return {"ok": True, "message": f"Google shows the reply once it approves it ({state})." if state == "PENDING" else None}


def draft_reply(db: Session, tenant_id: str, payload: s.DraftRequest) -> dict[str, Any]:
    """The Customer Service reply drafter (SPEC-BE-027): brand voice, grounded
    in the KB / FAQs / policies, moderated. A draft only; never sent here."""
    history = [HistoryMessage(sender_type=t.role, body=t.text) for t in payload.history]
    draft = generate_reply_draft(db, tenant_id, history)
    return {
        "body": draft.body,
        "confidence": draft.confidence,
        "fallback": draft.fallback,
        "sources": [{"kind": src.kind, "title": src.title} for src in draft.sources],
    }
