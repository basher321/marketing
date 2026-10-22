"""Order confirmation SMS through Twilio (SPEC-BE-108).

- One PilotSonic Twilio account (`platform_settings` group `twilio`); each company
  sends from its own number (`tenants.settings.sms.number`, set only by the Super
  admin), so a reply's `To` number names the company.
- Sending moves a `pending` order to `awaiting_confirmation` (SPEC-BE-107) only
  once Twilio accepts the message.
- Replies change an order only when the order is unambiguous (FR6); anything
  else is stored, answered with a question and flagged to staff.
- Every webhook is stored in `webhook_events`; a repeated event id does nothing.
"""
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import and_, func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.config import get_settings
from app.core.audit import write_audit_log
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.integrations import twilio_sms
from app.models.conversation import Conversation, Message
from app.models.customer import Customer
from app.models.order import Order
from app.models.sms import SmsMessage
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.sms import SmsSettingsSave
from app.services import platform_service
from app.utils import phone as phone_util
from app.utils.locale_data import format_money

logger = structlog.get_logger(__name__)

MAX_PER_ORDER = 3  # confirmation + follow-ups per order
MIN_GAP = timedelta(minutes=10)
MAX_SEGMENTS = 3
DEFAULT_TEMPLATES = {
    "en": "{shop}: order #{order_number}, {total}. Reply YES {order_number} to confirm "
          "or NO {order_number} to cancel.",
    "bn": "{shop}: অর্ডার #{order_number}, {total}। নিশ্চিত করতে YES {order_number}, "
          "বাতিল করতে NO {order_number} লিখে উত্তর দিন।",
}
THANKS = {
    "confirm": {"en": "Thank you! Order #{n} is confirmed.", "bn": "ধন্যবাদ! অর্ডার #{n} নিশ্চিত হয়েছে।"},
    "cancel": {"en": "Order #{n} is cancelled.", "bn": "অর্ডার #{n} বাতিল করা হয়েছে।"},
    "ask": {"en": "Which order? Reply YES or NO with the order number, e.g. YES {n}.",
            "bn": "কোন অর্ডার? অর্ডার নম্বরসহ YES বা NO লিখুন, যেমন YES {n}।"},
}
# Reply keywords (FR6), compared after lower-casing and stripping punctuation.
CONFIRM_WORDS = {"yes", "y", "confirm", "confirmed", "ok", "okay", "1", "হ্যাঁ", "হা", "হাঁ", "জি", "জী"}
CANCEL_WORDS = {"no", "n", "cancel", "2", "না", "বাতিল"}
# Twilio's own opt-out / opt-in keywords: a message that is exactly one of these
# is handled by Twilio for the number, so we record the customer's choice too.
OPT_OUT = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit"}
OPT_IN = {"start", "unstop", "yes"}
STATUS_RANK = {"accepted": 0, "queued": 0, "sending": 1, "sent": 2, "delivered": 3, "undelivered": 3,
               "failed": 3, "read": 4}
_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_TOKEN = re.compile(r"[^\wঀ-৿]+")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def credentials(db: Session | None = None) -> tuple[str, str]:
    return (platform_service.value("twilio", "account_sid", db),
            platform_service.value("twilio", "auth_token", db))


def _tenant(db: Session, tenant_id: str) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundError("Company not found.")
    return tenant


def _config(tenant: Tenant) -> dict[str, Any]:
    return dict((tenant.settings or {}).get("sms") or {})


def _save_config(tenant: Tenant, config: dict[str, Any]) -> None:
    settings = dict(tenant.settings or {})
    settings["sms"] = config
    tenant.settings = settings
    flag_modified(tenant, "settings")


def readiness(db: Session, tenant: Tenant) -> tuple[str, str | None, str | None]:
    """(status, reason, number). status: not_configured, no_number, blocked, ready."""
    number = _config(tenant).get("number")
    sid, token = credentials(db)
    if not (sid and token):
        return "not_configured", "PilotSonic hasn't set up SMS yet.", number
    if not platform_service.allowed(str(tenant.id), "sms", db):
        return "blocked", platform_service.BLOCKED["sms"], number
    if not number:
        return "no_number", "Your company has no SMS number yet. Ask PilotSonic for one.", None
    return "ready", None, number


def _language(db: Session, tenant: Tenant, config: dict[str, Any]) -> str:
    lang = config.get("language") or "auto"
    if lang in ("en", "bn"):
        return lang
    primary = db.execute(
        text("SELECT primary_language FROM brand_settings WHERE tenant_id = :t"), {"t": str(tenant.id)}
    ).scalar()
    return "bn" if str(primary or tenant.default_language or "en").lower().startswith("bn") else "en"


def render(template: str, shop: str, order_number: str, total: str, items: str) -> str:
    out = template
    for key, val in (("{shop}", shop), ("{order_number}", order_number), ("{total}", total), ("{items}", items)):
        out = out.replace(key, val)
    return out


def _template(db: Session, tenant: Tenant) -> tuple[str, str]:
    config = _config(tenant)
    lang = _language(db, tenant, config)
    return (config.get("template") or DEFAULT_TEMPLATES[lang]), lang


def get_settings_view(db: Session, tenant_id: str) -> dict[str, Any]:
    tenant = _tenant(db, tenant_id)
    status, reason, number = readiness(db, tenant)
    config = _config(tenant)
    template, lang = _template(db, tenant)
    preview = render(template, tenant.name, "1001", format_money(150000, tenant.currency.strip()), "2 items")
    return {
        "status": status, "reason": reason, "number": number,
        # On by default once the company has a number (the user's decision, 2026-10-21).
        "auto_confirm": bool(config.get("auto_confirm", True)),
        "language": config.get("language") or "auto",
        "template": config.get("template"), "default_template": DEFAULT_TEMPLATES[lang],
        "preview": preview, "segments": twilio_sms.segments(preview),
    }


def save_settings(db: Session, tenant_id: str, actor: User, payload: SmsSettingsSave) -> dict[str, Any]:
    tenant = _tenant(db, tenant_id)
    config = _config(tenant)
    changes = payload.model_dump(exclude_unset=True)
    if "template" in changes:
        template = (changes["template"] or "").strip()
        if template:
            if "{order_number}" not in template:
                raise AppError("The text must include {order_number} so the customer can answer for that order.", 422)
            sample = render(template, tenant.name, "100001", format_money(99999900, tenant.currency.strip()),
                            "10 items")
            if twilio_sms.segments(sample) > MAX_SEGMENTS:
                raise AppError(f"The text is too long: at most {MAX_SEGMENTS} SMS parts.", 422)
            config["template"] = template
        else:
            config.pop("template", None)
    for key in ("auto_confirm", "language"):
        if changes.get(key) is not None:
            config[key] = changes[key]
    _save_config(tenant, config)
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=str(actor.id), action="sms_settings.updated",
                    resource_type="tenant", resource_id=tenant_id, metadata={"fields": sorted(changes)})
    return get_settings_view(db, tenant_id)


# ---------------------------------------------------------------------------
# Super admin: numbers
# ---------------------------------------------------------------------------
def _owners(db: Session) -> dict[str, tuple[str, str]]:
    rows = db.execute(text(
        "SELECT id, name, settings->'sms'->>'number' FROM tenants WHERE settings->'sms'->>'number' IS NOT NULL"
    )).all()
    return {num: (str(tid), name) for tid, name, num in rows}


def list_numbers(db: Session) -> list[dict[str, Any]]:
    sid, token = credentials(db)
    if not (sid and token):
        raise AppError("Save the Twilio account SID and auth token first.", 409)
    try:
        numbers = twilio_sms.numbers(sid, token)
    except twilio_sms.SmsError as exc:
        raise AppError(exc.message, 502) from None
    owners = _owners(db)
    return [{**n, "company_id": owners.get(n["number"], (None, None))[0],
             "company_name": owners.get(n["number"], (None, None))[1]} for n in numbers]


def assign_number(db: Session, company_id: str, number: str, admin: User) -> dict[str, Any]:
    tenant = _tenant(db, company_id)
    config = _config(tenant)
    if number:
        e164 = phone_util.normalize(number)
        if not e164:
            raise AppError("Write the number in international form, e.g. +14155552671.", 422)
        owner = _owners(db).get(e164)
        if owner and owner[0] != company_id:
            raise ConflictError(f"{e164} already belongs to {owner[1]}.")
        if e164 not in {n["number"] for n in list_numbers(db) if n["sms"]}:
            raise AppError("That number isn't an SMS number on PilotSonic's Twilio account.", 422)
        config["number"] = e164
    else:
        config.pop("number", None)
    _save_config(tenant, config)
    platform_service.audit(db, str(admin.tenant_id), str(admin.id), "sms_number_assigned",
                           company=company_id, number=config.get("number"))
    return {"company_id": company_id, "number": config.get("number")}


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------
def _callback_url() -> str | None:
    base = get_settings().PUBLIC_BASE_URL.rstrip("/")
    return f"{base}/api/v1/webhooks/twilio/status" if base.startswith("https://") else None


def _consented(customer: Customer) -> bool:
    return (customer.consent or {}).get("sms") is not False


def _sent_for(db: Session, tenant_id: str, order_id: str) -> list[SmsMessage]:
    return list(db.scalars(
        select(SmsMessage).where(
            SmsMessage.tenant_id == tenant_id, SmsMessage.order_id == order_id,
            SmsMessage.direction == "outbound", SmsMessage.kind.in_(("order_confirmation", "follow_up")),
        ).order_by(SmsMessage.created_at)
    ))


def _deliver(db: Session, tenant: Tenant, number: str, to: str, body: str, *, kind: str,
             order_id: str | None, customer_id: str | None, actor_id: str | None) -> SmsMessage:
    """Send one SMS and store it (sent or failed). Never raises for a Twilio error."""
    row = SmsMessage(
        tenant_id=str(tenant.id), order_id=order_id, customer_id=customer_id, direction="outbound",
        kind=kind, from_number=number, to_number=to, body=body, status="queued", sent_by=actor_id,
        created_at=datetime.now(timezone.utc),
    )
    sid, token = credentials(db)
    try:
        result = twilio_sms.send(sid, token, number, to, body, _callback_url())
        row.provider_sid, row.status = result["sid"], result["status"]
    except twilio_sms.SmsError as exc:
        row.status, row.error_code, row.error_message = "failed", exc.code, exc.message
    db.add(row)
    db.flush()
    return row


def blocked_reason(db: Session, tenant: Tenant, order: Order, customer: Customer | None) -> str | None:
    if order.status not in ("pending", "awaiting_confirmation"):
        return f"The order is already {order.status}."
    status, reason, _ = readiness(db, tenant)
    if status != "ready":
        return reason
    if customer is None or not phone_util.normalize(customer.phone, tenant.country_code):
        return "This customer has no mobile number."
    if not _consented(customer):
        return "The customer has opted out of SMS."
    sent = _sent_for(db, str(tenant.id), str(order.id))
    if len(sent) >= MAX_PER_ORDER:
        return f"Already sent {MAX_PER_ORDER} confirmation SMS for this order."
    return None


def send_confirmation(db: Session, tenant_id: str, order_id: str, actor: User | None) -> dict[str, Any]:
    from app.services import order_service

    tenant = _tenant(db, tenant_id)
    order = order_service.get_order(db, tenant_id, order_id, lock=True)
    customer = db.get(Customer, order.customer_id) if order.customer_id else None
    reason = blocked_reason(db, tenant, order, customer)
    if reason:
        code = 422 if reason.startswith("This customer has no") else 409
        raise AppError(reason, code)
    sent = _sent_for(db, tenant_id, str(order.id))
    if sent:
        wait = sent[-1].created_at.astimezone(timezone.utc) + MIN_GAP - datetime.now(timezone.utc)
        if wait.total_seconds() > 0:
            raise AppError(f"Wait {int(wait.total_seconds() // 60) + 1} minute(s) before sending another SMS.", 429)
    assert customer is not None
    to = phone_util.normalize(customer.phone, tenant.country_code) or ""
    template, _ = _template(db, tenant)
    count = db.execute(text("SELECT coalesce(sum(quantity), 0) FROM order_items WHERE tenant_id = :t AND order_id = :o"),
                       {"t": tenant_id, "o": str(order.id)}).scalar()
    body = render(template, tenant.name, order.order_number, format_money(order.total_cents, order.currency.strip()),
                  f"{count} item(s)")
    _, _, number = readiness(db, tenant)
    actor_id = str(actor.id) if actor else None
    row = _deliver(db, tenant, number or "", to, body, kind="follow_up" if sent else "order_confirmation",
                   order_id=str(order.id), customer_id=str(customer.id), actor_id=actor_id)
    if row.status == "failed":
        db.commit()  # keep the failed row so the order shows the error
        raise AppError(row.error_message or "Twilio refused the message.", 502)
    if order.status == "pending":
        order_service.change_status(db, tenant_id, str(order.id), "awaiting_confirmation", actor=actor,
                                    actor_type="user" if actor else "system", metadata={"sms_id": str(row.id)},
                                    commit=False, allow_system=True)
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor_id, action="order.confirmation_sms_sent",
                    resource_type="order", resource_id=str(order.id), metadata={"sms_id": str(row.id)})
    return {"sms_id": str(row.id), "status": row.status, "order_status": order.status}


def auto_confirm(db: Session, tenant_id: str, order_id: str, actor: User | None) -> None:
    """After POST /orders: send when the company has auto-confirm on. A failure never
    fails the order; the order shows the failed SMS."""
    tenant = _tenant(db, tenant_id)
    if readiness(db, tenant)[0] != "ready" or not _config(tenant).get("auto_confirm", True):
        return
    try:
        send_confirmation(db, tenant_id, order_id, actor)
    except AppError as exc:
        db.rollback()
        logger.info("order.auto_confirm_skipped", tenant_id=tenant_id, order_id=order_id, reason=exc.detail)


# ---------------------------------------------------------------------------
# Read model for the order / customer record (FR7)
# ---------------------------------------------------------------------------
def _brief(row: SmsMessage) -> dict[str, Any]:
    return {
        "id": str(row.id), "direction": row.direction, "kind": row.kind, "body": row.body, "status": row.status,
        "interpreted": row.interpreted, "error": row.error_message,
        "at": row.created_at.astimezone(timezone.utc),
    }


def order_confirmation(db: Session, tenant_id: str, order: Order, customer: Customer | None) -> dict[str, Any]:
    from app.services import order_service

    rows = list(db.scalars(
        select(SmsMessage).where(SmsMessage.tenant_id == tenant_id, SmsMessage.order_id == str(order.id))
        .order_by(SmsMessage.created_at)
    ))
    outbound = [r for r in rows if r.direction == "outbound" and r.kind in ("order_confirmation", "follow_up")]
    tenant = _tenant(db, tenant_id)
    reason = blocked_reason(db, tenant, order, customer)
    if reason is None and outbound:
        wait = outbound[-1].created_at.astimezone(timezone.utc) + MIN_GAP - datetime.now(timezone.utc)
        if wait.total_seconds() > 0:
            reason = f"Wait {int(wait.total_seconds() // 60) + 1} minute(s) before sending another SMS."
    return {
        "state": order_service.confirmation_state(order.status),
        "last_sms": _brief(outbound[-1]) if outbound else None,
        "sms_count": len(outbound),
        "replies": [_brief(r) for r in rows if r.direction == "inbound"],
        "can_send": reason is None,
        "send_blocked_reason": reason,
    }


def customer_sms(db: Session, tenant_id: str, customer_id: str, limit: int = 100) -> list[dict[str, Any]]:
    rows = db.execute(
        select(SmsMessage, Order.order_number)
        .outerjoin(Order, and_(Order.id == SmsMessage.order_id, Order.tenant_id == tenant_id))
        .where(SmsMessage.tenant_id == tenant_id, SmsMessage.customer_id == customer_id)
        .order_by(SmsMessage.created_at.desc()).limit(limit)
    ).all()
    return [{**_brief(r), "order_number": n} for r, n in rows]


# ---------------------------------------------------------------------------
# Webhooks (FR5, FR6)
# ---------------------------------------------------------------------------
def webhook_urls(kind: str, request_url: str) -> list[str]:
    """Twilio signs the URL it called. Behind the host's proxy the request may look
    like http, so the public address is checked as well."""
    base = get_settings().PUBLIC_BASE_URL.rstrip("/")
    urls = [f"{base}/api/v1/webhooks/twilio/{kind}", request_url]
    if request_url.startswith("http://"):
        urls.append("https://" + request_url[len("http://"):])
    return list(dict.fromkeys(urls))


def record_event(db: Session, tenant_id: str | None, event_type: str, external_id: str | None,
                 payload: dict[str, Any], signature: str | None, valid: bool,
                 provider: str = "twilio") -> bool:
    """Store the webhook; False when this event id was already stored (a retry)."""
    result = db.execute(
        text(
            "INSERT INTO webhook_events (tenant_id, provider, event_type, external_event_id, payload, "
            "signature, signature_valid) VALUES (:t, :p, :e, :x, CAST(:pl AS jsonb), :s, :v) "
            "ON CONFLICT (provider, external_event_id) WHERE external_event_id IS NOT NULL DO NOTHING RETURNING id"
        ),
        {"t": tenant_id, "p": provider, "e": event_type, "x": external_id,
         "pl": __import__("json").dumps(payload), "s": (signature or "")[:500] or None, "v": valid},
    ).scalar()
    return result is not None


def mark_processed(db: Session, provider: str, external_id: str | None, error: str | None = None) -> None:
    if external_id:
        db.execute(text("UPDATE webhook_events SET processed_at = now(), processing_error = :e "
                        "WHERE provider = :p AND external_event_id = :x"),
                   {"p": provider, "x": external_id, "e": error})


def owner_of(db: Session, number: str | None) -> Tenant | None:
    e164 = phone_util.normalize(number) if number else None
    if not e164:
        return None
    tid = db.execute(text("SELECT id FROM tenants WHERE settings->'sms'->>'number' = :n"), {"n": e164}).scalar()
    return db.get(Tenant, str(tid)) if tid else None


def handle_status(db: Session, params: dict[str, str]) -> None:
    sid = params.get("MessageSid") or params.get("SmsSid")
    new = (params.get("MessageStatus") or params.get("SmsStatus") or "").lower()
    row = db.scalars(select(SmsMessage).where(SmsMessage.provider == "twilio", SmsMessage.provider_sid == sid)).first()
    if row is None or not new:
        return
    # Statuses never move backwards (delivered beats sent beats queued).
    if STATUS_RANK.get(new, 0) >= STATUS_RANK.get(row.status, 0):
        row.status = new
        if new in ("failed", "undelivered"):
            row.error_code = params.get("ErrorCode") or row.error_code
            row.error_message = f"Twilio: the message was {new}" + (
                f" (error {params['ErrorCode']})" if params.get("ErrorCode") else "") + "."
        row.updated_at = datetime.now(timezone.utc)
    # An SMS sent from the inbox (SPEC-BE-112) is also a message row with the same sid.
    msg = db.scalars(select(Message).where(Message.tenant_id == row.tenant_id, Message.external_message_id == sid)).first()
    if msg is not None:
        now = datetime.now(timezone.utc)
        if new == "delivered":
            msg.delivered_at = msg.delivered_at or now
        elif new in ("failed", "undelivered"):
            msg.extra_metadata = {**(msg.extra_metadata or {}), "delivery": "failed", "error": row.error_message}


def _tokens(body: str) -> list[str]:
    return [t for t in _TOKEN.split(body.translate(_BN_DIGITS).lower()) if t]


def interpret(body: str) -> tuple[str | None, list[str]]:
    """(keyword, order numbers): keyword confirm / cancel / None (none or both)."""
    tokens = _tokens(body)
    has_yes = any(t in CONFIRM_WORDS for t in tokens)
    has_no = any(t in CANCEL_WORDS for t in tokens)
    numbers = [t for t in tokens if t.isdigit() and len(t) >= 3]
    if has_yes == has_no:
        return None, numbers
    return ("confirm" if has_yes else "cancel"), numbers


def _customers_by_phone(db: Session, tenant_id: str, e164: str) -> list[Customer]:
    digits = phone_util.digits(e164)
    return list(db.scalars(select(Customer).where(
        Customer.tenant_id == tenant_id, Customer.deleted_at.is_(None),
        func.regexp_replace(Customer.phone, r"\D", "", "g") == digits,
    )))


def _sms_conversation(db: Session, tenant_id: str, customer_id: str | None, phone: str) -> Conversation:
    conv = db.scalars(select(Conversation).where(
        Conversation.tenant_id == tenant_id, Conversation.channel == "sms",
        Conversation.external_thread_id == phone, Conversation.status.in_(("open", "pending")),
    ).order_by(Conversation.created_at.desc())).first()
    if conv is None:
        conv = Conversation(tenant_id=tenant_id, customer_id=customer_id, channel="sms", status="open",
                            external_thread_id=phone, topic="SMS")
        db.add(conv)
        db.flush()
    return conv


def _auto_reply(db: Session, tenant: Tenant, number: str, to: str, body: str, order_id: str | None,
                customer_id: str | None) -> None:
    _deliver(db, tenant, number, to, body, kind="auto_reply", order_id=order_id, customer_id=customer_id,
             actor_id=None)


def _recent_ask(db: Session, tenant_id: str, to: str) -> bool:
    since = datetime.now(timezone.utc) - MIN_GAP
    return db.scalars(select(SmsMessage.id).where(
        SmsMessage.tenant_id == tenant_id, SmsMessage.to_number == to, SmsMessage.kind == "auto_reply",
        SmsMessage.created_at >= since, SmsMessage.order_id.is_(None),
    )).first() is not None


def handle_inbound(db: Session, tenant: Tenant, params: dict[str, str]) -> SmsMessage:
    from app.services import order_service
    from app.workflow_engine.actions import notify_role

    tenant_id = str(tenant.id)
    sender = phone_util.normalize(params.get("From")) or (params.get("From") or "")
    number = phone_util.normalize(params.get("To")) or (params.get("To") or "")
    body = (params.get("Body") or "").strip()
    customers = _customers_by_phone(db, tenant_id, sender)
    customer = customers[0] if customers else None
    conv = _sms_conversation(db, tenant_id, str(customer.id) if customer else None, sender)
    now = datetime.now(timezone.utc)
    db.add(Message(tenant_id=tenant_id, conversation_id=conv.id, direction="inbound", sender_type="customer",
                   body=body, sent_at=now, external_message_id=params.get("MessageSid")))
    conv.last_customer_message_at = now
    row = SmsMessage(tenant_id=tenant_id, customer_id=str(customer.id) if customer else None,
                     conversation_id=str(conv.id), direction="inbound", kind="inbound", from_number=sender,
                     to_number=number, body=body, provider_sid=params.get("MessageSid"), status="received",
                     created_at=now)
    db.add(row)
    db.flush()

    word = body.lower().strip(" .!")
    if word in OPT_OUT or word in OPT_IN:
        for c in customers:
            consent = dict(c.consent or {})
            consent["sms"] = word not in OPT_OUT
            c.consent = consent
    # Candidates: this phone's customers' orders waiting for confirmation that had a
    # confirmation SMS sent to this very phone.
    candidates = list(db.scalars(
        select(Order).where(
            Order.tenant_id == tenant_id, Order.status == "awaiting_confirmation",
            Order.customer_id.in_([str(c.id) for c in customers] or [""]),
            Order.id.in_(select(SmsMessage.order_id).where(
                SmsMessage.tenant_id == tenant_id, SmsMessage.to_number == sender,
                SmsMessage.direction == "outbound",
                SmsMessage.kind.in_(("order_confirmation", "follow_up")),
            )),
        ).order_by(Order.placed_at)
    )) if customers else []
    keyword, numbers = interpret(body)
    chosen: Order | None = None
    if numbers:
        named = [o for o in candidates if o.order_number in numbers]
        chosen = named[0] if len(named) == 1 else None
    elif len(candidates) == 1:
        chosen = candidates[0]
    lang = _language(db, tenant, _config(tenant))
    opted_out = word in OPT_OUT

    if not candidates:
        row.interpreted = "unrelated"
    elif keyword and chosen is not None:
        row.interpreted, row.order_id = keyword, str(chosen.id)
        order_service.change_status(
            db, tenant_id, str(chosen.id), "confirmed" if keyword == "confirm" else "cancelled",
            actor_type="customer_sms", reason="Customer replied by SMS",
            metadata={"sms_id": str(row.id), "body": body[:160]}, commit=False,
        )
        if not opted_out:
            _auto_reply(db, tenant, number, sender, THANKS[keyword][lang].format(n=chosen.order_number),
                        str(chosen.id), row.customer_id)
    else:
        row.interpreted = "ambiguous"
        waiting = ", ".join(f"#{o.order_number}" for o in candidates)
        if not opted_out and not _recent_ask(db, tenant_id, sender):
            _auto_reply(db, tenant, number, sender, THANKS["ask"][lang].format(n=candidates[0].order_number),
                        None, row.customer_id)
        for role in ("owner", "manager"):
            notify_role(db, tenant_id, role, "sms_reply_unclear", "A customer's SMS reply needs a look",
                        f"{sender} wrote \"{body[:120]}\". Waiting orders: {waiting}.",
                        link_url=f"/orders/{candidates[0].id}")
    db.flush()
    logger.info("sms.inbound", tenant_id=tenant_id, interpreted=row.interpreted)
    return row
