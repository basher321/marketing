"""Unified inbox (SPEC-BE-112): one list of conversations across channels.

Sources:
- local `conversations` + `messages`: WhatsApp Cloud (webhooks below), SMS (Twilio,
  SPEC-BE-108) and any website/email conversations already stored;
- SocialAPI (SPEC-BE-083) for Messenger and Instagram DMs, read live, never copied.

Keys: a channel is `local:<channel>`, `local:whatsapp:<integration id>` or
`socialapi:<account id>`; a conversation is `local:<uuid>` or
`socialapi:<account id>:<conversation id>`. Another company's key is a 404.
Demo rows (`conversations.metadata.sample = true`) are always labelled `is_sample`.
"""
import base64
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import structlog
from jose import JWTError, jwt  # type: ignore[import-untyped]
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.config import get_settings
from app.core.audit import write_audit_log
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.integrations import whatsapp_cloud as wa
from app.models.conversation import Conversation, Message
from app.models.customer import Customer
from app.models.integration import Integration
from app.models.order import Order
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.inbox import InboxPatch, InboxSend, WhatsAppCallback
from app.services import platform_service
from app.utils import phone as phone_util
from app.utils.crypto import decrypt_secret, encrypt_secret

logger = structlog.get_logger(__name__)

PAGE = 30
SOCIAL_DM_PLATFORMS = {"facebook": "messenger", "instagram": "instagram"}
LOCAL_CHANNEL_NAMES = {"web": "Website chat", "email": "Email", "sms": "SMS", "whatsapp": "WhatsApp",
                       "messenger": "Messenger (stored)", "facebook": "Facebook (stored)",
                       "instagram": "Instagram (stored)"}
CREDENTIALS_REF = "app:settings.secrets_enc"
WA_STATE_TTL = timedelta(minutes=20)


def _utc(value: datetime | None) -> datetime | None:
    return value.astimezone(timezone.utc) if value else None


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------------------
# WhatsApp connections
# ---------------------------------------------------------------------------
def _wa_integrations(db: Session, tenant_id: str, connected_only: bool = True) -> list[Integration]:
    q = select(Integration).where(Integration.tenant_id == tenant_id, Integration.provider == "whatsapp")
    if connected_only:
        q = q.where(Integration.status == "connected")
    return list(db.scalars(q.order_by(Integration.created_at)))


def _wa_fields(record: Integration) -> dict[str, Any]:
    return dict((record.settings or {}).get("fields") or {})


def _wa_token(record: Integration) -> str:
    raw = (record.settings or {}).get("secrets_enc")
    try:
        return str(json.loads(decrypt_secret(raw)).get("access_token") or "") if raw else ""
    except Exception:  # noqa: BLE001 - an unreadable secret is "not connected"
        return ""


def wa_available(db: Session, tenant_id: str) -> tuple[bool, str | None]:
    app_id = platform_service.value("meta_app", "app_id", db)
    secret = platform_service.value("meta_app", "app_secret", db)
    config_id = platform_service.value("whatsapp_app", "config_id", db)
    if not (app_id and secret and config_id):
        return False, "Not set up by PilotSonic yet."
    if not platform_service.allowed(tenant_id, "whatsapp", db):
        return False, platform_service.BLOCKED["whatsapp"]
    return True, None


def wa_status(db: Session, tenant_id: str) -> dict[str, Any]:
    ok, reason = wa_available(db, tenant_id)
    accounts = [{
        "id": str(r.id), "phone_number": _wa_fields(r).get("display_phone_number"), "name": r.account_name,
        "status": r.status, "last_error": r.last_error, "connected_at": _utc(r.connected_at),
    } for r in _wa_integrations(db, tenant_id, connected_only=False)]
    return {"available": ok, "reason": reason, "accounts": accounts}


def wa_connect(db: Session, tenant_id: str, actor: User) -> dict[str, Any]:
    ok, reason = wa_available(db, tenant_id)
    if not ok:
        raise AppError(reason or "WhatsApp isn't available.", 503 if reason and "PilotSonic yet" in reason else 403)
    s = get_settings()
    nonce = secrets.token_urlsafe(16)
    tenant = db.get(Tenant, tenant_id)
    assert tenant is not None
    settings = dict(tenant.settings or {})
    settings["whatsapp_pending"] = {"nonce": nonce, "by": str(actor.id)}
    tenant.settings = settings
    flag_modified(tenant, "settings")
    db.commit()
    claims = {"t": str(tenant_id), "u": str(actor.id), "n": nonce, "f": "whatsapp",
              "exp": datetime.now(timezone.utc) + WA_STATE_TTL}
    return {
        "app_id": platform_service.value("meta_app", "app_id", db),
        "config_id": platform_service.value("whatsapp_app", "config_id", db),
        "graph_version": s.META_GRAPH_VERSION,
        "state": jwt.encode(claims, s.SECRET_KEY.get_secret_value(), algorithm=s.JWT_ALGORITHM),
    }


def wa_callback(db: Session, tenant_id: str, actor: User, payload: WhatsAppCallback) -> dict[str, Any]:
    s = get_settings()
    try:
        claims = jwt.decode(payload.state, s.SECRET_KEY.get_secret_value(), algorithms=[s.JWT_ALGORITHM])
    except JWTError:
        raise AppError("This sign-in link has expired. Start again.", 400) from None
    tenant = db.get(Tenant, tenant_id)
    pending = (tenant.settings or {}).get("whatsapp_pending") if tenant else None
    if (claims.get("t") != str(tenant_id) or claims.get("u") != str(actor.id) or claims.get("f") != "whatsapp"
            or not pending or pending.get("nonce") != claims.get("n")):
        raise AppError("This sign-in link isn't valid. Start again.", 400)
    assert tenant is not None
    settings = dict(tenant.settings or {})
    settings.pop("whatsapp_pending", None)  # single use
    tenant.settings = settings
    flag_modified(tenant, "settings")
    try:
        token = wa.exchange_code(platform_service.value("meta_app", "app_id", db),
                                 platform_service.value("meta_app", "app_secret", db), payload.code)
        info = wa.phone_number(token, payload.phone_number_id)
        wa.subscribe(token, payload.waba_id)
    except wa.WhatsAppError as exc:
        db.commit()
        raise AppError(exc.message, 502) from None
    owner = db.execute(text(
        "SELECT tenant_id FROM integrations WHERE provider = 'whatsapp' AND settings->'fields'->>'phone_number_id' = :p "
        "AND tenant_id <> :t AND status = 'connected'"), {"p": payload.phone_number_id, "t": tenant_id}).scalar()
    if owner:
        db.commit()
        raise ConflictError("This WhatsApp number is connected to another company.")
    record = next((r for r in _wa_integrations(db, tenant_id, connected_only=False)
                   if _wa_fields(r).get("phone_number_id") == payload.phone_number_id), None)
    now = datetime.now(timezone.utc)
    if record is None:
        record = Integration(tenant_id=tenant_id, provider="whatsapp", status="connected", credentials_ref=CREDENTIALS_REF)
        db.add(record)
    record.settings = {
        "fields": {"phone_number_id": payload.phone_number_id, "waba_id": payload.waba_id,
                   "display_phone_number": info.get("display_phone_number")},
        "secrets_enc": encrypt_secret(json.dumps({"access_token": token})),
        "oauth": {"via": "embedded_signup"},
    }
    record.status, record.last_error, record.credentials_ref = "connected", None, CREDENTIALS_REF
    record.account_name = (info.get("verified_name") or info.get("display_phone_number") or "WhatsApp")[:255]
    record.connected_by, record.connected_at = str(actor.id), now
    db.flush()
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=str(actor.id), action="integration.whatsapp_connected",
                    resource_type="integration", resource_id=str(record.id),
                    metadata={"phone_number_id": payload.phone_number_id})
    return wa_status(db, tenant_id)


def wa_disconnect(db: Session, tenant_id: str, actor: User, integration_id: str) -> None:
    if not _is_uuid(integration_id):
        raise NotFoundError("Connection not found.")
    record = next((r for r in _wa_integrations(db, tenant_id, connected_only=False) if str(r.id) == integration_id), None)
    if record is None:
        raise NotFoundError("Connection not found.")
    db.delete(record)
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=str(actor.id), action="integration.whatsapp_disconnected",
                    resource_type="integration", resource_id=integration_id, metadata={})


# ---------------------------------------------------------------------------
# Channels (FR1)
# ---------------------------------------------------------------------------
def _social_accounts(db: Session, tenant_id: str) -> tuple[list[dict[str, Any]], str | None]:
    from app.services import socialapi_service

    try:
        return socialapi_service.inbox_accounts(db, tenant_id), None
    except Exception as exc:  # noqa: BLE001 - SocialAPI trouble never breaks the inbox
        logger.warning("inbox_socialapi_unavailable", tenant_id=tenant_id, error=type(exc).__name__)
        return [], "SocialAPI didn't answer; Messenger and Instagram are hidden for now."


def list_channels(db: Session, tenant_id: str) -> dict[str, Any]:
    from app.services import sms_service

    items: list[dict[str, Any]] = []
    accounts, _ = _social_accounts(db, tenant_id)
    for a in accounts:
        platform = SOCIAL_DM_PLATFORMS[a["platform"]]
        problem = a.get("reconnect_reason") and f"Reconnect it in Organic › SocialAPI ({a['reconnect_reason']})."
        items.append({
            "key": f"socialapi:{a['id']}", "platform": platform, "source": "socialapi", "account_id": a["id"],
            "name": a.get("page_name") or a.get("name") or a.get("username") or platform.title(),
            "status": "needs_attention" if problem else "connected", "problem": problem or None,
            "can_send": not problem, "can_send_media": False,
        })
    for r in _wa_integrations(db, tenant_id):
        number = _wa_fields(r).get("display_phone_number")
        items.append({
            "key": f"local:whatsapp:{r.id}", "platform": "whatsapp", "source": "whatsapp_cloud", "account_id": str(r.id),
            "name": f"WhatsApp {number}" if number else (r.account_name or "WhatsApp"),
            "status": "connected", "problem": None, "can_send": True, "can_send_media": True,
        })
    tenant = db.get(Tenant, tenant_id)
    if tenant is not None:
        status, reason, number = sms_service.readiness(db, tenant)
        if status == "ready":
            items.append({"key": "local:sms", "platform": "sms", "source": "twilio", "account_id": None,
                          "name": f"SMS {number}", "status": "connected", "problem": None,
                          "can_send": True, "can_send_media": False})
    # Other stored channels (website chat, email, older stored threads): read only.
    stored = [r[0] for r in db.execute(text(
        "SELECT DISTINCT channel::text FROM conversations WHERE tenant_id = :t AND channel::text NOT IN ('whatsapp', 'sms') "
        "ORDER BY 1"), {"t": tenant_id})]
    for ch in stored:
        items.append({"key": f"local:{ch}", "platform": ch, "source": "local", "account_id": None,
                      "name": LOCAL_CHANNEL_NAMES.get(ch, ch.title()), "status": "connected", "problem": None,
                      "can_send": False, "can_send_media": False})
    return {"items": items}


# ---------------------------------------------------------------------------
# Conversations (FR2)
# ---------------------------------------------------------------------------
def _encode(cursor: dict[str, Any]) -> str | None:
    if not cursor:
        return None
    return base64.urlsafe_b64encode(json.dumps(cursor).encode()).decode()


def _decode(cursor: str | None) -> dict[str, Any]:
    if not cursor:
        return {}
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        return data if isinstance(data, dict) else {}
    except (ValueError, json.JSONDecodeError):
        raise AppError("Invalid cursor.", 422) from None


def _names(db: Session, tenant_id: str, ids: set[str]) -> dict[str, str]:
    if not ids:
        return {}
    rows = db.query(User.id, User.first_name, User.last_name, User.email).filter(
        User.tenant_id == tenant_id, User.id.in_(ids))
    return {str(i): (" ".join(p for p in (f, ln) if p) or e) for i, f, ln, e in rows}


def _local_channel_filter(channel: str) -> Any:
    # "local:whatsapp:<integration id>" | "local:<channel>"
    parts = channel.split(":")
    if len(parts) == 3 and parts[1] == "whatsapp":
        return and_(Conversation.channel == "whatsapp",
                    Conversation.extra_metadata["integration_id"].astext == parts[2])
    return Conversation.channel == parts[1]


def _local_items(db: Session, tenant_id: str, user: User, channel: str | None, q: str | None, status: str | None,
                 unread: bool, mine: bool, offset: int) -> tuple[list[dict[str, Any]], bool]:
    last_at = (select(func.max(Message.created_at)).where(Message.conversation_id == Conversation.id)
               .correlate(Conversation).scalar_subquery())
    unread_n = (select(func.count(Message.id)).where(
        Message.conversation_id == Conversation.id, Message.direction == "inbound", Message.read_at.is_(None))
        .correlate(Conversation).scalar_subquery())
    query = (select(Conversation, Customer, last_at.label("last_at"), unread_n.label("unread"))
             .outerjoin(Customer, and_(Customer.id == Conversation.customer_id, Customer.tenant_id == tenant_id))
             .where(Conversation.tenant_id == tenant_id))
    if channel and channel != "all":
        query = query.where(_local_channel_filter(channel))
    query = query.where(Conversation.status == status) if status else query.where(Conversation.status.in_(("open", "pending")))
    if unread:
        query = query.where(unread_n > 0)
    if mine:
        query = query.where(Conversation.assigned_user_id == str(user.id))
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        like = f"%{escaped}%"
        digits = phone_util.digits(q)
        conds = [func.concat_ws(" ", Customer.first_name, Customer.last_name).ilike(like), Customer.email.ilike(like),
                 Customer.phone.ilike(like), Conversation.topic.ilike(like), Conversation.external_thread_id.ilike(like),
                 select(Message.id).where(Message.conversation_id == Conversation.id, Message.body.ilike(like))
                 .correlate(Conversation).exists()]
        if len(digits) >= 4:
            conds.append(func.regexp_replace(Customer.phone, r"\D", "", "g").contains(digits.lstrip("0") or digits))
        query = query.where(or_(*conds))
    rows = db.execute(query.order_by(func.coalesce(last_at, Conversation.updated_at).desc(), Conversation.id)
                      .limit(PAGE + 1).offset(offset)).all()
    more = len(rows) > PAGE
    rows = rows[:PAGE]
    names = _names(db, tenant_id, {str(c.assigned_user_id) for c, *_ in rows if c.assigned_user_id})
    items = []
    for conv, cust, at, n in rows:
        last = db.scalars(select(Message).where(Message.conversation_id == conv.id, Message.tenant_id == tenant_id)
                          .order_by(Message.created_at.desc()).limit(1)).first()
        meta = conv.extra_metadata or {}
        key_channel = f"local:whatsapp:{meta['integration_id']}" if conv.channel == "whatsapp" and meta.get("integration_id") \
            else f"local:{conv.channel}"
        name = (" ".join(p for p in ((cust.first_name, cust.last_name) if cust else ()) if p) or None) \
            or meta.get("profile_name")
        items.append({
            "key": f"local:{conv.id}", "channel": key_channel, "platform": conv.channel, "conversation_id": str(conv.id),
            "customer": {"id": str(cust.id) if cust else None, "name": name,
                         "handle": conv.external_thread_id, "phone": cust.phone if cust else conv.external_thread_id,
                         "email": cust.email if cust else None, "avatar": None},
            "last_message": {"preview": (last.body or "")[:160] if last else None, "at": _utc(at),
                             "direction": last.direction if last else None},
            "unread": int(n or 0), "status": conv.status,
            "assignee_id": str(conv.assigned_user_id) if conv.assigned_user_id else None,
            "assignee_name": names.get(str(conv.assigned_user_id)) if conv.assigned_user_id else None,
            "topic": conv.topic, "is_sample": bool(meta.get("sample")),
        })
    return items, more


def _social_items(db: Session, tenant_id: str, account: dict[str, Any], status: str | None, cursor: str | None,
                  q: str | None, unread: bool) -> tuple[list[dict[str, Any]], str | None]:
    from app.services import socialapi_service

    social_status = "archived" if status in ("resolved", "archived") else "active"
    out = socialapi_service.conversations(db, tenant_id, account["platform"], account["id"], social_status, cursor)
    links = _links(db, tenant_id)
    items = []
    for c in out["items"]:
        if unread and not c["unread_count"]:
            continue
        if q and q.lower() not in f"{c.get('participant_name') or ''} {c.get('last_message') or ''}".lower():
            continue
        key = f"socialapi:{account['id']}:{c['id']}"
        items.append({
            "key": key, "channel": f"socialapi:{account['id']}", "platform": SOCIAL_DM_PLATFORMS[account["platform"]],
            "conversation_id": c["id"],
            "customer": {"id": links.get(key), "name": c.get("participant_name"), "handle": None, "phone": None,
                         "email": None, "avatar": c.get("participant_picture")},
            "last_message": {"preview": (c.get("last_message") or "")[:160] or None, "at": c.get("last_message_at"),
                             "direction": None},
            "unread": c["unread_count"], "status": "open" if social_status == "active" else "archived",
            "assignee_id": None, "assignee_name": None, "topic": None, "is_sample": False,
        })
    return items, out.get("next_cursor")


def list_conversations(db: Session, tenant_id: str, user: User, channel: str | None, q: str | None,
                       status: str | None, unread: bool, mine: bool, cursor: str | None) -> dict[str, Any]:
    state = _decode(cursor)
    channel = channel or "all"
    if not (channel == "all" or channel.startswith("local:") or channel.startswith("socialapi:")):
        raise AppError("Unknown channel.", 422)
    items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    nxt: dict[str, Any] = {}
    if channel == "all" or channel.startswith("local:"):
        if state.get("o", 0) is not None:
            offset = int(state.get("o", 0))
            local, more = _local_items(db, tenant_id, user, channel, q, status, unread, mine, offset)
            items += local
            if more:
                nxt["o"] = offset + PAGE
    # SocialAPI threads can't be assigned, so "assigned to me" shows only local ones.
    if (channel == "all" or channel.startswith("socialapi:")) and not mine:
        accounts, err = _social_accounts(db, tenant_id)
        if err:
            errors.append({"channel": "socialapi", "message": err})
        wanted = [a for a in accounts if channel == "all" or channel == f"socialapi:{a['id']}"]
        if channel.startswith("socialapi:") and not wanted and not err:
            raise NotFoundError("Channel not found.")
        cursors = state.get("s") or {}
        for a in wanted:
            if cursor and a["id"] not in cursors:
                continue  # that account's pages are finished
            try:
                social, next_c = _social_items(db, tenant_id, a, status, cursors.get(a["id"]), q, unread)
            except Exception as exc:  # noqa: BLE001
                message = getattr(exc, "detail", None) or "SocialAPI didn't answer."
                errors.append({"channel": f"socialapi:{a['id']}", "message": str(message)})
                continue
            items += social
            if next_c:
                nxt.setdefault("s", {})[a["id"]] = next_c
        if "s" in nxt and "o" not in nxt and channel == "all":
            nxt["o"] = None
    floor = datetime.min.replace(tzinfo=timezone.utc)
    items.sort(key=lambda i: i["last_message"]["at"] or floor, reverse=True)
    return {"items": items, "next_cursor": _encode(nxt), "channel_errors": errors}


# ---------------------------------------------------------------------------
# One conversation (FR3-FR6)
# ---------------------------------------------------------------------------
def _parse_key(key: str) -> tuple[str, str, str | None]:
    parts = key.split(":")
    if len(parts) == 2 and parts[0] == "local" and _is_uuid(parts[1]):
        return "local", parts[1], None
    if len(parts) == 3 and parts[0] == "socialapi" and parts[1] and parts[2]:
        return "socialapi", parts[2], parts[1]
    raise NotFoundError("Conversation not found.")


def _local_conv(db: Session, tenant_id: str, conv_id: str) -> Conversation:
    conv = db.scalars(select(Conversation).where(Conversation.tenant_id == tenant_id, Conversation.id == conv_id)).first()
    if conv is None:
        raise NotFoundError("Conversation not found.")
    return conv


def _social_account(db: Session, tenant_id: str, account_id: str) -> dict[str, Any]:
    accounts, _ = _social_accounts(db, tenant_id)
    account = next((a for a in accounts if a["id"] == account_id), None)
    if account is None:
        raise NotFoundError("Conversation not found.")
    return account


def _delivery(m: Message) -> tuple[str | None, str | None]:
    meta = m.extra_metadata or {}
    if m.direction == "inbound":
        return None, None
    if meta.get("delivery") == "failed":
        return "failed", meta.get("error")
    if meta.get("delivery") == "not_sent":
        return "not_sent", meta.get("error")
    if m.read_at:
        return "read", None
    if m.delivered_at:
        return "delivered", None
    if m.sent_at or m.external_message_id:
        return "sent", None
    return "pending", None


def _message_row(m: Message, names: dict[str, str]) -> dict[str, Any]:
    delivery, error = _delivery(m)
    sender = "Customer" if m.sender_type == "customer" else (
        names.get(str(m.sender_id or m.approved_by)) if (m.sender_id or m.approved_by) else
        ("AI" if m.sender_type == "ai" else m.sender_type.title()))
    return {
        "id": str(m.id), "direction": m.direction, "sender": sender, "body": m.body,
        "attachments": [a for a in (m.attachments or []) if isinstance(a, dict)],
        "sent_at": _utc(m.sent_at or m.created_at), "delivery": delivery, "error": error,
        "is_ai_draft": bool(m.sender_type == "ai" and m.approved_by is None and m.sent_at is None),
    }


def _customer_panel(db: Session, tenant_id: str, customer_id: str | None) -> dict[str, Any] | None:
    from app.services.order_service import confirmation_state

    if not customer_id:
        return None
    c = db.scalars(select(Customer).where(Customer.tenant_id == tenant_id, Customer.id == customer_id,
                                          Customer.deleted_at.is_(None))).first()
    if c is None:
        return None
    currency = (db.scalar(select(Tenant.currency).where(Tenant.id == tenant_id)) or "USD").strip()
    orders = db.scalars(select(Order).where(Order.tenant_id == tenant_id, Order.customer_id == str(c.id))
                        .order_by(Order.placed_at.desc()).limit(5))
    return {
        "id": str(c.id), "name": " ".join(p for p in (c.first_name, c.last_name) if p) or None, "phone": c.phone,
        "email": c.email, "order_count": c.order_count or 0,
        "lifetime_value": float(Decimal(c.lifetime_value_cents or 0) / 100), "currency": currency,
        "orders": [{"id": str(o.id), "order_number": o.order_number, "status": o.status,
                    "confirmation_state": confirmation_state(o.status), "total": float(Decimal(o.total_cents) / 100),
                    "currency": o.currency.strip()} for o in orders],
    }


def _send_rules(db: Session, tenant_id: str, conv: Conversation) -> tuple[bool, bool, str | None]:
    """(can_send, can_send_media, why not)."""
    from app.services import sms_service

    if conv.channel == "whatsapp":
        record = _wa_record(db, tenant_id, conv)
        if record is None:
            return False, False, "This WhatsApp number isn't connected any more."
        last = conv.last_customer_message_at
        if last is None or datetime.now(timezone.utc) - last.astimezone(timezone.utc) > timedelta(hours=wa.SERVICE_WINDOW_HOURS):
            return False, False, ("WhatsApp allows free replies only within 24 hours of the customer's last message; "
                                  "after that Meta requires an approved template.")
        return True, True, None
    if conv.channel == "sms":
        tenant = db.get(Tenant, tenant_id)
        status, reason, _ = sms_service.readiness(db, tenant) if tenant else ("not_configured", "", None)
        if status != "ready":
            return False, False, reason
        customer = db.get(Customer, conv.customer_id) if conv.customer_id else None
        if customer is not None and (customer.consent or {}).get("sms") is False:
            return False, False, "The customer has opted out of SMS."
        return True, False, None
    return False, False, "Replies on this channel can't be sent from PilotSonic (no sending connection)."


def _wa_record(db: Session, tenant_id: str, conv: Conversation) -> Integration | None:
    integration_id = (conv.extra_metadata or {}).get("integration_id")
    return next((r for r in _wa_integrations(db, tenant_id) if str(r.id) == integration_id), None)


def get_thread(db: Session, tenant_id: str, user: User, key: str, cursor: str | None) -> dict[str, Any]:
    from app.services import socialapi_service

    source, conv_id, account_id = _parse_key(key)
    if source == "local":
        conv = _local_conv(db, tenant_id, conv_id)
        msgs = list(db.scalars(select(Message).where(Message.tenant_id == tenant_id, Message.conversation_id == conv.id)
                               .order_by(Message.created_at.desc()).limit(200)))
        msgs.reverse()
        # Opening the thread marks the customer's messages read.
        now = datetime.now(timezone.utc)
        for m in msgs:
            if m.direction == "inbound" and m.read_at is None:
                m.read_at = now
        db.commit()
        names = _names(db, tenant_id, {str(m.sender_id or m.approved_by) for m in msgs if m.sender_id or m.approved_by})
        summary = _local_summary(db, tenant_id, conv)
        can_send, media, why = _send_rules(db, tenant_id, conv)
        return {"conversation": summary, "customer": _customer_panel(db, tenant_id, conv.customer_id),
                "can_send": can_send, "can_send_media": media, "send_blocked_reason": why,
                "items": [_message_row(m, names) for m in msgs], "next_cursor": None}
    assert account_id is not None
    account = _social_account(db, tenant_id, account_id)
    out = socialapi_service.messages(db, tenant_id, conv_id, cursor)
    items = [{
        "id": m["id"], "direction": m.get("direction") or "inbound", "sender": m.get("sender_name"),
        "body": m.get("text"), "attachments": ([{"kind": m.get("attachment_type"), "url": m.get("attachment_url")}]
                                               if m.get("attachment_url") else []),
        "sent_at": m.get("created_at"), "delivery": m.get("status") if m.get("direction") == "outbound" else None,
        "error": None, "is_ai_draft": False,
    } for m in out["items"]]
    links = _links(db, tenant_id)
    first_inbound = next((m for m in items if m["direction"] == "inbound"), None)
    summary = {
        "key": key, "channel": f"socialapi:{account_id}", "platform": SOCIAL_DM_PLATFORMS[account["platform"]],
        "conversation_id": conv_id,
        "customer": {"id": links.get(key), "name": first_inbound["sender"] if first_inbound else None, "handle": None,
                     "phone": None, "email": None, "avatar": None},
        "last_message": {"preview": (items[-1]["body"] or "")[:160] if items else None,
                         "at": items[-1]["sent_at"] if items else None,
                         "direction": items[-1]["direction"] if items else None},
        "unread": 0, "status": "open", "assignee_id": None, "assignee_name": None, "topic": None, "is_sample": False,
    }
    problem = account.get("reconnect_reason")
    return {"conversation": summary, "customer": _customer_panel(db, tenant_id, links.get(key)),
            "can_send": not problem, "can_send_media": False,
            "send_blocked_reason": f"Reconnect it in Organic › SocialAPI ({problem})." if problem else None,
            "items": items, "next_cursor": out.get("next_cursor")}


def _local_summary(db: Session, tenant_id: str, conv: Conversation) -> dict[str, Any]:
    cust = db.get(Customer, conv.customer_id) if conv.customer_id else None
    last = db.scalars(select(Message).where(Message.conversation_id == conv.id, Message.tenant_id == tenant_id)
                      .order_by(Message.created_at.desc()).limit(1)).first()
    unread = db.scalar(select(func.count(Message.id)).where(
        Message.conversation_id == conv.id, Message.direction == "inbound", Message.read_at.is_(None))) or 0
    meta = conv.extra_metadata or {}
    names = _names(db, tenant_id, {str(conv.assigned_user_id)} if conv.assigned_user_id else set())
    channel = f"local:whatsapp:{meta['integration_id']}" if conv.channel == "whatsapp" and meta.get("integration_id") \
        else f"local:{conv.channel}"
    return {
        "key": f"local:{conv.id}", "channel": channel, "platform": conv.channel, "conversation_id": str(conv.id),
        "customer": {"id": str(cust.id) if cust else None,
                     "name": (" ".join(p for p in ((cust.first_name, cust.last_name) if cust else ()) if p) or None)
                     or meta.get("profile_name"),
                     "handle": conv.external_thread_id, "phone": cust.phone if cust else conv.external_thread_id,
                     "email": cust.email if cust else None, "avatar": None},
        "last_message": {"preview": (last.body or "")[:160] if last else None,
                         "at": _utc(last.created_at) if last else None, "direction": last.direction if last else None},
        "unread": int(unread), "status": conv.status,
        "assignee_id": str(conv.assigned_user_id) if conv.assigned_user_id else None,
        "assignee_name": names.get(str(conv.assigned_user_id)) if conv.assigned_user_id else None,
        "topic": conv.topic, "is_sample": bool(meta.get("sample")),
    }


def send(db: Session, tenant_id: str, user: User, key: str, payload: InboxSend) -> dict[str, Any]:
    from app.services import media_service, sms_service, socialapi_service
    from app.schemas.socialapi import SendMessage

    if not payload.body and not payload.media_ids:
        raise AppError("Write a message or attach an image.", 422)
    source, conv_id, account_id = _parse_key(key)
    now = datetime.now(timezone.utc)
    if source == "socialapi":
        assert account_id is not None
        _social_account(db, tenant_id, account_id)
        if payload.media_ids:
            raise AppError("Attachments can't be sent on this channel.", 422)
        socialapi_service.send_message(db, tenant_id, str(user.id), conv_id,
                                       SendMessage(account_id=account_id, text=payload.body))
        return {"message": {"id": f"sent-{uuid.uuid4().hex[:8]}", "direction": "outbound",
                            "sender": _names(db, tenant_id, {str(user.id)}).get(str(user.id)), "body": payload.body,
                            "attachments": [], "sent_at": now, "delivery": "sent", "error": None, "is_ai_draft": False}}
    conv = _local_conv(db, tenant_id, conv_id)
    can_send, can_media, why = _send_rules(db, tenant_id, conv)
    if not can_send:
        raise ConflictError(why or "Replies can't be sent on this channel.")
    if payload.media_ids and not can_media:
        raise AppError("Attachments can't be sent on this channel.", 422)
    assets = media_service.media_rows(db, tenant_id, payload.media_ids, kinds=("image",)) if payload.media_ids else []
    if len(assets) != len(set(payload.media_ids)):
        raise AppError("Some images aren't in your media library.", 422)
    msg = Message(tenant_id=tenant_id, conversation_id=conv.id, direction="outbound", sender_type="agent",
                  sender_id=str(user.id), body=payload.body, approved_by=str(user.id), approved_at=now,
                  attachments=[{"media_id": str(a.id), "kind": "image", "name": getattr(a, "name", None)} for a in assets],
                  extra_metadata={}, created_at=now)
    if conv.channel == "whatsapp":
        record = _wa_record(db, tenant_id, conv)
        assert record is not None
        token, pnid = _wa_token(record), _wa_fields(record).get("phone_number_id", "")
        try:
            ids = []
            for a in assets:
                ids.append(wa.send_image(token, pnid, conv.external_thread_id or "",
                                         media_service.signed_url(str(a.id), 24), payload.body or None))
            if payload.body and not assets:
                ids.append(wa.send_text(token, pnid, conv.external_thread_id or "", payload.body))
            msg.external_message_id = ids[-1] if ids else None
            msg.sent_at = now
        except wa.WhatsAppError as exc:
            msg.extra_metadata = {"delivery": "failed", "error": exc.message}
            if exc.auth:
                record.status, record.last_error = "expired", exc.message
    else:  # sms
        tenant = db.get(Tenant, tenant_id)
        assert tenant is not None
        _, _, number = sms_service.readiness(db, tenant)
        sms = sms_service._deliver(db, tenant, number or "", conv.external_thread_id or "", payload.body, kind="manual",
                                   order_id=None, customer_id=conv.customer_id, actor_id=str(user.id))
        sms.conversation_id = str(conv.id)
        msg.external_message_id = sms.provider_sid
        if sms.status == "failed":
            msg.extra_metadata = {"delivery": "failed", "error": sms.error_message}
        else:
            msg.sent_at = now
    db.add(msg)
    conv.last_agent_message_at = now
    if conv.status == "pending":
        conv.status = "open"
    db.flush()
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=str(user.id), action="inbox.message_sent",
                    resource_type="conversation", resource_id=str(conv.id),
                    metadata={"channel": conv.channel, "failed": (msg.extra_metadata or {}).get("delivery") == "failed"})
    names = _names(db, tenant_id, {str(user.id)})
    return {"message": _message_row(msg, names)}


def update(db: Session, tenant_id: str, user: User, key: str, payload: InboxPatch) -> dict[str, Any]:
    source, conv_id, _ = _parse_key(key)
    if source != "local":
        raise ConflictError("SocialAPI conversations can't be assigned or closed here.")
    conv = _local_conv(db, tenant_id, conv_id)
    changes = payload.model_dump(exclude_unset=True)
    if "assignee_id" in changes and changes["assignee_id"]:
        aid = changes["assignee_id"]
        if not _is_uuid(aid) or db.scalar(select(User.id).where(User.tenant_id == tenant_id, User.id == aid,
                                                               User.status == "active")) is None:
            raise AppError("The assignee must be an active user of your company.", 422)
    if "assignee_id" in changes:
        conv.assigned_user_id = changes["assignee_id"] or None
    if changes.get("status"):
        conv.status = changes["status"]
        if changes["status"] == "resolved":
            conv.extra_metadata = {**(conv.extra_metadata or {}), "resolved_by": str(user.id)}
    if "tags" in changes:
        conv.tags = changes["tags"] or []
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=str(user.id), action="inbox.conversation_updated",
                    resource_type="conversation", resource_id=str(conv.id), metadata={"fields": sorted(changes)})
    return _local_summary(db, tenant_id, conv)


def _links(db: Session, tenant_id: str) -> dict[str, str]:
    tenant = db.get(Tenant, tenant_id)
    return dict(((tenant.settings or {}).get("socialapi") or {}).get("links") or {}) if tenant else {}


def link(db: Session, tenant_id: str, user: User, key: str, customer_id: str) -> dict[str, Any]:
    source, conv_id, account_id = _parse_key(key)
    customer = db.scalars(select(Customer).where(Customer.tenant_id == tenant_id, Customer.id == customer_id,
                                                 Customer.deleted_at.is_(None))).first() if _is_uuid(customer_id) else None
    if customer is None:
        raise NotFoundError("Customer not found.")
    if source == "local":
        conv = _local_conv(db, tenant_id, conv_id)
        conv.customer_id = str(customer.id)
    else:
        assert account_id is not None
        _social_account(db, tenant_id, account_id)
        tenant = db.get(Tenant, tenant_id)
        assert tenant is not None
        settings = dict(tenant.settings or {})
        social = dict(settings.get("socialapi") or {})
        links = dict(social.get("links") or {})
        links[key] = str(customer.id)
        social["links"] = links
        settings["socialapi"] = social
        tenant.settings = settings
        flag_modified(tenant, "settings")
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=str(user.id), action="inbox.customer_linked",
                    resource_type="conversation", resource_id=conv_id if source == "local" else None,
                    metadata={"customer_id": str(customer.id), "key": key})
    return _customer_panel(db, tenant_id, str(customer.id)) or {}


# ---------------------------------------------------------------------------
# WhatsApp webhook (FR8)
# ---------------------------------------------------------------------------
def wa_owner(db: Session, phone_number_id: str) -> Integration | None:
    return db.scalars(select(Integration).where(
        Integration.provider == "whatsapp", Integration.status == "connected",
        Integration.settings["fields"]["phone_number_id"].astext == phone_number_id,
    )).first()


def _wa_conversation(db: Session, record: Integration, wa_id: str, profile_name: str | None) -> Conversation:
    tenant_id = str(record.tenant_id)
    e164 = phone_util.normalize("+" + wa_id.lstrip("+")) or ("+" + wa_id.lstrip("+"))
    conv = db.scalars(select(Conversation).where(
        Conversation.tenant_id == tenant_id, Conversation.channel == "whatsapp", Conversation.external_thread_id == e164,
        Conversation.extra_metadata["integration_id"].astext == str(record.id),
        Conversation.status.in_(("open", "pending")),
    ).order_by(Conversation.created_at.desc())).first()
    if conv is not None:
        return conv
    from app.services.order_service import find_customer_by_phone

    customer = find_customer_by_phone(db, tenant_id, e164)
    if customer is None:
        first, _, last = (profile_name or "").partition(" ")
        customer = Customer(tenant_id=tenant_id, phone=e164, first_name=first[:100] or None, last_name=last[:100] or None)
        db.add(customer)
        db.flush()
    conv = Conversation(tenant_id=tenant_id, customer_id=str(customer.id), channel="whatsapp", status="open",
                        external_thread_id=e164, topic="WhatsApp",
                        extra_metadata={"integration_id": str(record.id), "profile_name": profile_name})
    db.add(conv)
    db.flush()
    return conv


def handle_wa_webhook(db: Session, payload: dict[str, Any]) -> int:
    """Apply one webhook body; returns how many new events were applied. Each message /
    status is deduplicated by its id in webhook_events."""
    from app.services import sms_service

    applied = 0
    for entry in payload.get("entry") or []:
        for change in (entry or {}).get("changes") or []:
            value = (change or {}).get("value") or {}
            pnid = str(((value.get("metadata") or {}).get("phone_number_id")) or "")
            record = wa_owner(db, pnid) if pnid else None
            if record is None:
                continue
            tenant_id = str(record.tenant_id)
            names = {c.get("wa_id"): ((c.get("profile") or {}).get("name")) for c in value.get("contacts") or []}
            for m in value.get("messages") or []:
                mid = str(m.get("id") or "")
                if not mid or not sms_service.record_event(db, tenant_id, "message", mid, m, None, True, provider="whatsapp"):
                    continue
                conv = _wa_conversation(db, record, str(m.get("from") or ""), names.get(m.get("from")))
                kind = m.get("type")
                body = ((m.get("text") or {}).get("body") if kind == "text" else
                        ((m.get(kind) or {}).get("caption") if isinstance(m.get(kind), dict) else None)) or ""
                attachments = [{"kind": kind, "wa_media_id": (m.get(kind) or {}).get("id")}] \
                    if kind in ("image", "video", "audio", "document", "sticker") else []
                if not body and not attachments:
                    body = f"[{kind} message]"
                at = datetime.fromtimestamp(int(m.get("timestamp") or 0) or datetime.now(timezone.utc).timestamp(), timezone.utc)
                db.add(Message(tenant_id=tenant_id, conversation_id=conv.id, direction="inbound", sender_type="customer",
                               body=body, attachments=attachments, external_message_id=mid, sent_at=at, created_at=at,
                               extra_metadata={}))
                conv.last_customer_message_at = at
                if conv.status != "open":
                    conv.status = "open"
                applied += 1
            for st in value.get("statuses") or []:
                sid, state = str(st.get("id") or ""), str(st.get("status") or "")
                if not sid or not sms_service.record_event(db, tenant_id, "status", f"{sid}:{state}", st, None, True,
                                                           provider="whatsapp"):
                    continue
                msg = db.scalars(select(Message).where(Message.tenant_id == tenant_id,
                                                       Message.external_message_id == sid)).first()
                if msg is None:
                    continue
                at = datetime.fromtimestamp(int(st.get("timestamp") or 0) or datetime.now(timezone.utc).timestamp(), timezone.utc)
                if state == "sent":
                    msg.sent_at = msg.sent_at or at
                elif state == "delivered":
                    msg.delivered_at = msg.delivered_at or at
                elif state == "read":
                    msg.delivered_at = msg.delivered_at or at
                    msg.read_at = msg.read_at or at
                elif state == "failed":
                    err = (st.get("errors") or [{}])[0]
                    msg.extra_metadata = {**(msg.extra_metadata or {}), "delivery": "failed",
                                          "error": f"WhatsApp: {err.get('title') or err.get('message') or 'failed'}"}
                applied += 1
    db.flush()
    return applied
