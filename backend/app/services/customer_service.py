"""Customer profile management (SPEC-BE-007) and the customer record (SPEC-BE-109)."""
import uuid
from datetime import timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models.conversation import Conversation, Message
from app.models.customer import Customer
from app.models.order import Order
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.customer import CustomerCreate, CustomerPatch
from app.utils import phone as phone_util

logger = structlog.get_logger(__name__)

CUSTOMERS_EMAIL_UNIQUE = "customers_tenant_email_unique"


def _to_read(customer: Customer) -> dict[str, Any]:
    return {
        "id": str(customer.id),
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "email": customer.email,
        "phone": customer.phone,
        "created_at": customer.created_at.astimezone(timezone.utc),
        "order_count": customer.order_count or 0,
        "lifetime_value": float(Decimal(customer.lifetime_value_cents or 0) / 100),
        "last_order_at": customer.last_order_at.astimezone(timezone.utc) if customer.last_order_at else None,
    }


def _search(q: str) -> Any:
    escaped = q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    like = f"%{escaped}%"
    conditions: list[Any] = [
        func.concat_ws(" ", Customer.first_name, Customer.last_name).ilike(like),
        cast(Customer.email, String).ilike(like),
        Customer.phone.ilike(like),
    ]
    digits = phone_util.digits(q)
    if len(digits) >= 4:
        # "01712 345" finds +8801712345678: compared as digits, without a leading 0.
        conditions.append(
            func.regexp_replace(Customer.phone, r"\D", "", "g").contains(digits.lstrip("0") or digits)
        )
    return or_(*conditions)


def list_customers(
    db: Session, tenant_id: str, q: str | None = None, limit: int | None = None, offset: int = 0
) -> tuple[list[dict[str, Any]], int]:
    # Soft-deleted customers (deleted_at set) are excluded. Without q/limit this is
    # the full SPEC-BE-007 list, in creation order.
    filters: list[Any] = [Customer.tenant_id == tenant_id, Customer.deleted_at.is_(None)]
    if q:
        filters.append(_search(q))
    total = db.scalar(select(func.count(Customer.id)).where(*filters)) or 0
    query = select(Customer).where(*filters).order_by(Customer.created_at, Customer.id).offset(offset)
    if limit:
        query = query.limit(limit)
    currency = (db.scalar(select(Tenant.currency).where(Tenant.id == tenant_id)) or "USD").strip()
    return [{**_to_read(c), "currency": currency} for c in db.scalars(query).all()], int(total)


def get_customer(db: Session, tenant_id: str, customer_id: str) -> Customer:
    try:
        uuid.UUID(str(customer_id))
    except ValueError:
        raise NotFoundError("Customer not found.") from None
    customer = db.scalars(
        select(Customer).where(
            Customer.tenant_id == tenant_id,
            Customer.id == customer_id,
            Customer.deleted_at.is_(None),
        )
    ).first()
    if customer is None:
        raise NotFoundError("Customer not found.")
    return customer


def create_customer(db: Session, tenant_id: str, payload: CustomerCreate) -> dict[str, Any]:
    customer = Customer(tenant_id=tenant_id, **payload.model_dump())
    try:
        db.add(customer)
        db.commit()
    except IntegrityError as exc:
        # Live UNIQUE (tenant_id, email); email is citext, so this is case-insensitive.
        db.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == CUSTOMERS_EMAIL_UNIQUE:
            raise ConflictError("A customer with this email already exists.") from exc
        raise
    db.refresh(customer)
    logger.info("customer.created", tenant_id=tenant_id, customer_id=str(customer.id))
    return _to_read(customer)


# ---- SPEC-BE-109: the customer record -----------------------------------
FINAL_STATUSES = ("delivered", "cancelled", "returned", "refunded")


def _name(c: Customer) -> str | None:
    return " ".join(p for p in (c.first_name, c.last_name) if p).strip() or None


def _order_row(o: Order) -> dict[str, Any]:
    from app.services.order_service import confirmation_state

    return {
        "id": str(o.id), "order_number": o.order_number, "status": o.status,
        "confirmation_state": confirmation_state(o.status), "total": float(Decimal(o.total_cents) / 100),
        "currency": o.currency.strip(), "placed_at": o.placed_at.astimezone(timezone.utc),
        "tracking_number": o.tracking_number, "tracking_url": o.tracking_url,
    }


def customer_record(db: Session, tenant_id: str, customer_id: str) -> dict[str, Any]:
    from app.services import order_service, sms_service

    c = get_customer(db, tenant_id, customer_id)
    currency = (db.scalar(select(Tenant.currency).where(Tenant.id == tenant_id)) or "USD").strip()
    orders = list(db.scalars(
        select(Order).where(Order.tenant_id == tenant_id, Order.customer_id == str(c.id))
        .order_by(Order.placed_at.desc(), Order.order_number.desc())
    ))
    # The current order = the newest one that isn't final.
    current = next((o for o in orders if o.status not in FINAL_STATUSES), None)
    history = order_service.status_history(
        db, tenant_id, [str(o.id) for o in orders], newest_first=True, limit=100
    )
    convs = list(db.scalars(
        select(Conversation).where(Conversation.tenant_id == tenant_id, Conversation.customer_id == str(c.id))
        .order_by(Conversation.updated_at.desc()).limit(50)
    ))
    conversations = []
    for conv in convs:
        last = db.scalars(
            select(Message).where(Message.tenant_id == tenant_id, Message.conversation_id == conv.id)
            .order_by(Message.created_at.desc()).limit(1)
        ).first()
        unread = db.scalar(select(func.count(Message.id)).where(
            Message.tenant_id == tenant_id, Message.conversation_id == conv.id,
            Message.direction == "inbound", Message.read_at.is_(None),
        )) or 0
        conversations.append({
            "id": str(conv.id), "channel": conv.channel, "status": conv.status, "topic": conv.topic,
            "last_message": (last.body or "")[:200] if last else None,
            "last_message_at": last.created_at.astimezone(timezone.utc) if last else None,
            "unread": int(unread),
        })
    return {
        "customer": {
            "id": str(c.id), "name": _name(c), "first_name": c.first_name, "last_name": c.last_name,
            "phone": c.phone, "email": c.email, "address": c.default_address, "city": c.city,
            "country_code": (c.country_code or "").strip() or None, "tags": list(c.tags or []),
            "accepts_marketing": bool(c.accepts_marketing),
            "sms_opt_out": (c.consent or {}).get("sms") is False,
            "order_count": c.order_count or 0,
            "lifetime_value": float(Decimal(c.lifetime_value_cents or 0) / 100),
            "currency": currency, "created_at": c.created_at.astimezone(timezone.utc),
        },
        "current_order": _order_row(current) if current else None,
        "orders": [_order_row(o) for o in orders],
        "status_history": history,
        "sms": sms_service.customer_sms(db, tenant_id, str(c.id)),
        "conversations": conversations,
    }


def update_customer(
    db: Session, tenant_id: str, actor: User, customer_id: str, payload: CustomerPatch
) -> dict[str, Any]:
    c = get_customer(db, tenant_id, customer_id)
    changes = payload.model_dump(exclude_unset=True)
    if "phone" in changes:
        if changes["phone"]:
            country = db.scalar(select(Tenant.country_code).where(Tenant.id == tenant_id))
            normalized = phone_util.normalize(changes["phone"], country)
            if normalized is None:
                raise AppError("That phone number isn't valid.", 422)
            changes["phone"] = normalized
        else:
            changes["phone"] = None
    if "email" in changes:
        changes["email"] = str(changes["email"]) if changes["email"] else None
    if not (changes.get("email", c.email) or changes.get("phone", c.phone)):
        raise AppError("A customer needs an email or a phone number.", 422)
    if "address" in changes:
        changes["default_address"] = changes.pop("address")
    for field, value in changes.items():
        setattr(c, field, value)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == CUSTOMERS_EMAIL_UNIQUE:
            raise ConflictError("A customer with this email already exists.") from exc
        raise
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=str(actor.id), action="customer.updated",
                    resource_type="customer", resource_id=str(c.id), metadata={"fields": sorted(changes)})
    return customer_record(db, tenant_id, str(c.id))
