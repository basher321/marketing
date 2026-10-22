"""Order count metrics (SPEC-BE-006), the orders list (SPEC-BE-041) and the
order lifecycle (SPEC-BE-107: create, allowed status changes, status history)."""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import (
    BigInteger, Boolean, Integer, String, and_, cast, column, func, or_, select, table, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.exceptions import AppError, ConflictError, ForbiddenError, NotFoundError
from app.core.permissions import Role, role_at_least
from app.models.customer import Customer
from app.models.order import Order, OrderItem, OrderStatusEvent
from app.models.product import Product
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.order import OrderCreate, OrderCustomerIn, OrderPatch
from app.utils import phone as phone_util

logger = structlog.get_logger(__name__)


def pct_delta(current: float, previous: float) -> float:
    # Percentage change of `current` vs `previous`, rounded to 1 decimal:
    # (current - previous) / previous * 100. Both 0 -> 0.0. previous 0 with
    # current > 0 -> 100.0 (growth from nothing is reported as +100%, never a
    # division-by-zero error). Reused by SPEC-BE-015's revenue delta.
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round((current - previous) / previous * 100, 1)


def get_order_metrics(db: Session, tenant_id: str, now: datetime | None = None) -> dict[str, int | float]:
    # Counts use orders.placed_at (TIMESTAMPTZ) in UTC and every order status,
    # including cancelled/refunded. Windows: last_24h = [now-24h, now];
    # last_7d = [now-7d, now]; previous 7d = [now-14d, now-7d). `now` is
    # injectable so callers (SPEC-BE-015) can share the exact same moment.
    now = now or datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    total, last_24h, last_7d, prev_7d = (
        db.query(
            func.count(Order.id),
            func.count(Order.id).filter(Order.placed_at >= day_ago, Order.placed_at <= now),
            func.count(Order.id).filter(Order.placed_at >= week_ago, Order.placed_at <= now),
            func.count(Order.id).filter(
                Order.placed_at >= two_weeks_ago, Order.placed_at < week_ago
            ),
        )
        .filter(Order.tenant_id == tenant_id)
        .one()
    )
    metrics: dict[str, int | float] = {
        "total": int(total),
        "last_24h": int(last_24h),
        "last_7d": int(last_7d),
        "last_7d_delta_pct": pct_delta(last_7d, prev_7d),
    }
    logger.info("order_metrics_computed", tenant_id=tenant_id, **metrics)
    return metrics


def get_revenue_24h(db: Session, tenant_id: str, now: datetime | None = None) -> dict[str, float]:
    # Revenue (24h) (SPEC-BE-018) = SUM(orders.total_cents) for the tenant,
    # every order status incl. cancelled/refunded (same inclusion as the
    # SPEC-BE-006 counts and SPEC-BE-015 revenue_7d), converted to major units
    # via Decimal. The sum ignores orders.currency (no currency field, like
    # SPEC-BE-015); a tenant with mixed-currency orders gets a mixed sum.
    # Windows on placed_at (UTC), same as SPEC-BE-006's last_24h:
    # current = [now-24h, now]; previous = [now-48h, now-24h).
    # Delta = pct_delta: both 0 -> 0.0; previous 0 and current > 0 -> 100.0.
    now = now or datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)
    two_days_ago = now - timedelta(hours=48)

    current_cents, previous_cents = (
        db.query(
            func.coalesce(
                func.sum(Order.total_cents).filter(
                    Order.placed_at >= day_ago, Order.placed_at <= now
                ),
                0,
            ),
            func.coalesce(
                func.sum(Order.total_cents).filter(
                    Order.placed_at >= two_days_ago, Order.placed_at < day_ago
                ),
                0,
            ),
        )
        .filter(Order.tenant_id == tenant_id, Order.placed_at >= two_days_ago)
        .one()
    )
    current = float(Decimal(current_cents) / 100)
    previous = float(Decimal(previous_cents) / 100)
    revenue = {"revenue_24h": current, "revenue_24h_delta_pct": pct_delta(current, previous)}
    logger.info("revenue_24h_computed", tenant_id=tenant_id, **revenue)
    return revenue


def _customer_name(
    first_name: str | None, last_name: str | None, email: str | None, phone: str | None
) -> str | None:
    # "First Last" (trimmed), else email, else phone. None only for a guest order
    # (no customer row); the frontend shows "Guest".
    full = " ".join(p for p in (first_name, last_name) if p).strip()
    return full or email or phone


def list_orders(
    db: Session,
    tenant_id: str,
    status: str | None = None,
    q: str | None = None,
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    # E-Commerce Orders tab (SPEC-BE-041). Tenant-scoped on orders, and on the
    # joined customers/order_items too. item_count = SUM(order_items.quantity)
    # from one grouped subquery (no per-row queries); orders without items -> 0.
    # Soft-deleted customers still name their historical orders.
    item_counts = (
        db.query(
            OrderItem.order_id.label("order_id"),
            func.sum(OrderItem.quantity).label("item_count"),
        )
        .filter(OrderItem.tenant_id == tenant_id)
        .group_by(OrderItem.order_id)
        .subquery()
    )
    customer_join = and_(Customer.id == Order.customer_id, Customer.tenant_id == tenant_id)

    filters = [Order.tenant_id == tenant_id]
    if status:
        filters.append(Order.status == status)
    if q:
        # Case-insensitive substring match; LIKE wildcards in the input are literal.
        escaped = q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        pattern = f"%{escaped}%"
        full_name = func.concat_ws(" ", Customer.first_name, Customer.last_name)
        filters.append(
            or_(
                Order.order_number.ilike(pattern),
                full_name.ilike(pattern),
                cast(Customer.email, String).ilike(pattern),
                Customer.phone.ilike(pattern),
            )
        )

    total = (
        db.query(func.count(Order.id)).outerjoin(Customer, customer_join).filter(*filters).scalar()
    )
    rows = (
        db.query(
            Order,
            Customer.first_name,
            Customer.last_name,
            cast(Customer.email, String),
            Customer.phone,
            func.coalesce(item_counts.c.item_count, 0),
        )
        .outerjoin(Customer, customer_join)
        .outerjoin(item_counts, item_counts.c.order_id == Order.id)
        .filter(*filters)
        .order_by(Order.placed_at.desc(), Order.order_number.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    items = [
        {
            "id": str(order.id),
            "order_number": order.order_number,
            "placed_at": order.placed_at.astimezone(timezone.utc),
            "customer_name": _customer_name(first, last, email, phone),
            "channel": order.channel,
            "item_count": int(item_count),
            # total_cents -> major units via Decimal; currency from the order row.
            "total": float(Decimal(order.total_cents) / 100),
            "currency": order.currency,
            "payment_method": order.payment_method,
            "payment_status": order.payment_status,
            "status": order.status,
            "tracking_number": order.tracking_number,
            "confirmation_state": confirmation_state(order.status),
        }
        for order, first, last, email, phone, item_count in rows
    ]
    logger.info("orders_listed", tenant_id=tenant_id, total=total, returned=len(items))
    return {"total": int(total), "items": items}


# ---- SPEC-BE-107: order lifecycle ----------------------------------------

# Allowed status changes. awaiting_confirmation is set only by SPEC-BE-108 when a
# confirmation SMS is accepted by Twilio (never by hand); cancelled and refunded are final.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "pending": ("awaiting_confirmation", "confirmed", "cancelled"),
    "awaiting_confirmation": ("confirmed", "cancelled"),
    "confirmed": ("processing", "cancelled"),
    "processing": ("shipped", "cancelled"),
    "shipped": ("delivered", "returned"),
    "delivered": ("returned", "refunded"),
    "returned": ("refunded",),
    "cancelled": (),
    "refunded": (),
}
SYSTEM_ONLY = {"awaiting_confirmation"}
REASON_REQUIRED = {"cancelled", "returned"}
# Statuses that don't count towards a customer's lifetime value / order count.
NOT_COUNTED = ("cancelled", "returned", "refunded")


def _needs_manager(from_status: str, to_status: str) -> bool:
    # Cancelling after the customer confirmed, returns and refunds are manager+.
    if to_status in ("returned", "refunded"):
        return True
    return to_status == "cancelled" and from_status in ("confirmed", "processing")


def confirmation_state(status: str) -> str:
    # The order's SMS reply position (SPEC-BE-107 FR7 / SPEC-BE-108 FR7):
    # pending = not sent yet, awaiting_confirmation = waiting, cancelled = cancelled,
    # any status after confirmation = confirmed (whether by SMS reply or by staff).
    if status == "pending":
        return "not_sent"
    if status == "awaiting_confirmation":
        return "waiting"
    if status == "cancelled":
        return "cancelled"
    return "confirmed"


def allowed_next(status: str, role: str) -> list[str]:
    if not role_at_least(role, Role.AGENT):
        return []
    manager = role_at_least(role, Role.MANAGER)
    return [
        to for to in TRANSITIONS.get(status, ())
        if to not in SYSTEM_ONLY and (manager or not _needs_manager(status, to))
    ]


def _major(cents: int | None) -> float:
    return float(Decimal(cents or 0) / 100)


def _cents(amount: Decimal | None) -> int:
    return int((amount or Decimal(0)) * 100)


def _utc(value: datetime | None) -> datetime | None:
    return value.astimezone(timezone.utc) if value else None


# product_variants through a Core table of the live columns (the ORM model is misaligned).
_variants = table(
    "product_variants",
    column("id", String),
    column("tenant_id", String),
    column("product_id", String),
    column("sku", String),
    column("attributes", JSONB),
    column("price_cents", BigInteger),
    column("cost_cents", BigInteger),
    column("is_default", Boolean),
    column("display_order", Integer),
)
_product_cost = table("products", column("id", String), column("cost_cents", BigInteger))


def _variant_label(attributes: Any) -> str | None:
    if isinstance(attributes, dict) and attributes:
        return " / ".join(str(v) for v in attributes.values() if v not in (None, "")) or None
    return None


def _split_name(name: str | None) -> tuple[str | None, str | None]:
    parts = (name or "").split()
    if not parts:
        return None, None
    return parts[0][:100], (" ".join(parts[1:])[:100] or None)


def _is_uuid(value: str | None) -> bool:
    try:
        uuid.UUID(str(value))
    except ValueError:
        return False
    return True


def find_customer_by_phone(db: Session, tenant_id: str, e164: str, raw: str | None = None) -> Customer | None:
    # Match on digits so "01712-345678" and "+8801712345678" are the same customer.
    wanted = {phone_util.digits(e164)}
    if raw:
        wanted.add(phone_util.digits(raw))
    return db.scalars(
        select(Customer).where(
            Customer.tenant_id == tenant_id,
            Customer.deleted_at.is_(None),
            func.regexp_replace(Customer.phone, r"\D", "", "g").in_(wanted),
        ).order_by(Customer.created_at)
    ).first()


def _find_or_create_customer(db: Session, tenant: Tenant, data: OrderCustomerIn) -> Customer:
    tenant_id = str(tenant.id)
    if data.id:
        found = None
        if _is_uuid(data.id):
            found = db.scalars(
                select(Customer).where(
                    Customer.tenant_id == tenant_id, Customer.id == data.id, Customer.deleted_at.is_(None)
                )
            ).first()
        if found is None:
            raise NotFoundError("Customer not found.")
        return found
    normalized = phone_util.normalize(data.phone, tenant.country_code) if data.phone else None
    if data.phone and normalized is None:
        raise AppError("That phone number isn't valid.", status_code=422)
    found = find_customer_by_phone(db, tenant_id, normalized, data.phone) if normalized else None
    if found is None and data.email:
        found = db.scalars(
            select(Customer).where(
                Customer.tenant_id == tenant_id, Customer.deleted_at.is_(None),
                Customer.email == str(data.email),
            )
        ).first()
    if found is not None:
        if normalized and not found.phone:
            found.phone = normalized
        return found
    first, last = _split_name(data.name)
    customer = Customer(
        tenant_id=tenant_id, first_name=first, last_name=last, phone=normalized,
        email=str(data.email) if data.email else None, default_address=data.address,
        country_code=tenant.country_code,
    )
    db.add(customer)
    db.flush()
    return customer


def _resolve_line(
    db: Session, tenant_id: str, index: int, variant_id: str | None, product_id: str | None
) -> dict[str, Any]:
    missing = AppError(f"Line {index + 1}: product not found.", status_code=422)
    if not _is_uuid(variant_id or product_id):
        raise missing
    q = (
        select(Product, _variants.c.id, _variants.c.sku, _variants.c.attributes,
               _variants.c.price_cents, _variants.c.cost_cents)
        .select_from(Product)
        .outerjoin(_variants, and_(_variants.c.product_id == Product.id, _variants.c.tenant_id == tenant_id))
        .where(Product.tenant_id == tenant_id, Product.deleted_at.is_(None))
    )
    if variant_id:
        q = q.where(_variants.c.id == variant_id)
    else:
        # A product line uses its default variant (else the first), or none when it has no variants.
        q = q.where(Product.id == product_id).order_by(
            _variants.c.is_default.desc().nulls_last(), _variants.c.display_order.asc().nulls_last()
        )
    row = db.execute(q.limit(1)).first()
    if row is None:
        raise missing
    product, v_id, v_sku, v_attr, v_price, v_cost = row
    if product.status == "archived":
        raise AppError(f"Line {index + 1}: {product.title} is archived.", status_code=422)
    cost = v_cost if v_cost is not None else db.execute(
        select(_product_cost.c.cost_cents).where(_product_cost.c.id == product.id)
    ).scalar()
    return {
        "variant_id": str(v_id) if v_id else None,
        "price_cents": v_price if v_price is not None else product.default_price_cents,
        # The snapshot keeps the cost at order time for SPEC-BE-110's cost of goods.
        "snapshot": {
            "product_id": str(product.id), "sku": v_sku or product.sku, "title": product.title,
            "variant": _variant_label(v_attr), "cost_cents": cost,
        },
    }


def refresh_customer_stats(db: Session, tenant_id: str, customer_id: str | None) -> None:
    # Recomputed from the orders (never incremented), so cancellations and returns
    # can't leave the record out of step with the orders (SPEC-BE-109 FR4).
    if not customer_id:
        return
    count, value = (
        db.query(func.count(Order.id), func.coalesce(func.sum(Order.total_cents), 0))
        .filter(Order.tenant_id == tenant_id, Order.customer_id == customer_id,
                Order.status.notin_(NOT_COUNTED))
        .one()
    )
    first, last = (
        db.query(func.min(Order.placed_at), func.max(Order.placed_at))
        .filter(Order.tenant_id == tenant_id, Order.customer_id == customer_id)
        .one()
    )
    customer = db.get(Customer, customer_id)
    if customer is None:
        return
    customer.order_count = int(count)
    customer.lifetime_value_cents = int(value)
    customer.first_order_at, customer.last_order_at = first, last


def _next_number(db: Session, tenant_id: str) -> str:
    # Per-company sequence starting at 1001, serialised by a transaction-scoped advisory lock.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"order_number:{tenant_id}"})
    current = db.execute(
        text(
            "SELECT max(order_number::bigint) FROM orders "
            "WHERE tenant_id = :t AND order_number ~ '^[0-9]{1,15}$'"
        ),
        {"t": tenant_id},
    ).scalar()
    return str(max(int(current or 0) + 1, 1001))


def add_event(
    db: Session, tenant_id: str, order_id: str, from_status: str | None, to_status: str,
    actor_type: str, actor_user_id: str | None, reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    db.add(OrderStatusEvent(
        tenant_id=tenant_id, order_id=order_id, from_status=from_status, to_status=to_status,
        actor_type=actor_type, actor_user_id=actor_user_id, reason=reason, extra_metadata=metadata or {},
        # The clock, not now(): several changes in one transaction must keep their order.
        created_at=datetime.now(timezone.utc),
    ))


def _by_idempotency(db: Session, tenant_id: str, key: str) -> Order | None:
    return db.scalars(
        select(Order).where(
            Order.tenant_id == tenant_id, Order.extra_metadata["idempotency_key"].astext == key
        )
    ).first()


def create_order(
    db: Session, tenant_id: str, actor: User, payload: OrderCreate, idempotency_key: str | None = None
) -> tuple[str, bool]:
    """(order id, created). The same Idempotency-Key again returns the first order."""
    key = (idempotency_key or "").strip()[:200] or None
    if key:
        existing = _by_idempotency(db, tenant_id, key)
        if existing is not None:
            return str(existing.id), False
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundError("Company not found.")
    customer = _find_or_create_customer(db, tenant, payload.customer)
    lines = []
    for i, item in enumerate(payload.items):
        resolved = _resolve_line(db, tenant_id, i, item.variant_id, item.product_id)
        unit = _cents(item.unit_price) if item.unit_price is not None else int(resolved["price_cents"] or 0)
        lines.append((resolved, item.quantity, unit))
    # Totals are computed here; the client never sends a total.
    subtotal = sum(q * unit for _, q, unit in lines)
    discount, shipping, tax = _cents(payload.discount), _cents(payload.shipping), _cents(payload.tax)
    if discount > subtotal:
        raise AppError("The discount can't be more than the order's subtotal.", status_code=422)
    metadata: dict[str, Any] = {"created_by": str(actor.id)}
    if key:
        metadata["idempotency_key"] = key
    order = Order(
        tenant_id=tenant_id, customer_id=str(customer.id), order_number=_next_number(db, tenant_id),
        channel=payload.channel, status="pending", subtotal_cents=subtotal, discount_cents=discount,
        shipping_cents=shipping, tax_cents=tax, total_cents=subtotal - discount + shipping + tax,
        currency=(tenant.currency or "USD").strip(), payment_method=payload.payment_method,
        payment_status=payload.payment_status, notes=payload.notes,
        shipping_address=payload.shipping_address or payload.customer.address or {},
        extra_metadata=metadata, placed_at=datetime.now(timezone.utc),
    )
    db.add(order)
    try:
        db.flush()
    except IntegrityError:
        # A concurrent request with the same Idempotency-Key won the race.
        db.rollback()
        existing = _by_idempotency(db, tenant_id, key) if key else None
        if existing is None:
            raise
        return str(existing.id), False
    for line_no, (resolved, quantity, unit) in enumerate(lines):
        db.add(OrderItem(
            tenant_id=tenant_id, order_id=order.id, variant_id=resolved["variant_id"],
            # "line" keeps the lines in the order they were entered (created_at is equal).
            product_snapshot={**resolved["snapshot"], "line": line_no}, quantity=quantity, unit_price_cents=unit,
            discount_cents=0, line_total_cents=quantity * unit,
        ))
        # One row per flush: batched inserts can't match String(36) ids to the
        # native uuids Postgres returns (insertmanyvalues sentinel KeyError).
        db.flush()
    add_event(db, tenant_id, str(order.id), None, "pending", "user", str(actor.id))
    db.flush()
    refresh_customer_stats(db, tenant_id, str(customer.id))
    write_audit_log(
        db, tenant_id=tenant_id, actor_user_id=str(actor.id), action="order.created",
        resource_type="order", resource_id=str(order.id),
        metadata={"order_number": order.order_number, "total_cents": order.total_cents},
    )
    logger.info("order.created", tenant_id=tenant_id, order_id=str(order.id))
    return str(order.id), True


def get_order(db: Session, tenant_id: str, order_id: str, lock: bool = False) -> Order:
    if not _is_uuid(order_id):
        raise NotFoundError("Order not found.")
    q = select(Order).where(Order.tenant_id == tenant_id, Order.id == order_id)
    if lock:
        q = q.with_for_update()
    order = db.scalars(q).first()
    if order is None:
        raise NotFoundError("Order not found.")
    return order


def get_by_number(db: Session, tenant_id: str, number: str) -> Order:
    order = db.scalars(
        select(Order).where(Order.tenant_id == tenant_id, Order.order_number == number.strip().lstrip("#"))
    ).first()
    if order is None:
        raise NotFoundError(f"Order {number} not found.")
    return order


def change_status(
    db: Session,
    tenant_id: str,
    order_id: str,
    to_status: str,
    *,
    actor: User | None = None,
    actor_type: str = "user",
    reason: str | None = None,
    tracking_number: str | None = None,
    tracking_url: str | None = None,
    metadata: dict[str, Any] | None = None,
    commit: bool = True,
    allow_system: bool = False,
) -> Order:
    """Apply one allowed change (FR1/FR2/FR5). Row-locked, so two clicks can't both apply."""
    order = get_order(db, tenant_id, order_id, lock=True)
    current = order.status
    if to_status == current:
        raise ConflictError(f"The order is already {current}.")
    if to_status not in TRANSITIONS.get(current, ()):
        raise ConflictError(f"An order that is {current} can't become {to_status}.")
    if actor_type == "user":
        if to_status in SYSTEM_ONLY and not allow_system:
            raise ConflictError("Send the confirmation SMS to move an order to awaiting confirmation.")
        role = actor.role if actor else "viewer"
        if not role_at_least(role, Role.AGENT):
            raise ForbiddenError("Insufficient permissions.")
        if _needs_manager(current, to_status) and not role_at_least(role, Role.MANAGER):
            raise ForbiddenError(f"Only a manager can change a {current} order to {to_status}.")
        if to_status in REASON_REQUIRED and not (reason or "").strip():
            raise AppError(f"Say why the order is {to_status}.", status_code=422)
    now = datetime.now(timezone.utc)
    order.status = to_status
    if to_status == "shipped":
        order.fulfilled_at = now
    elif to_status == "delivered":
        order.delivered_at = now
    elif to_status == "cancelled":
        order.cancelled_at = now
    if tracking_number is not None:
        order.tracking_number = tracking_number or None
    if tracking_url is not None:
        order.tracking_url = tracking_url or None
    actor_id = str(actor.id) if actor else None
    add_event(db, tenant_id, str(order.id), current, to_status, actor_type, actor_id, reason, metadata)
    db.flush()
    refresh_customer_stats(db, tenant_id, order.customer_id)
    if commit:
        write_audit_log(
            db, tenant_id=tenant_id, actor_user_id=actor_id, action="order.status_changed",
            resource_type="order", resource_id=str(order.id),
            metadata={"from": current, "to": to_status, "actor_type": actor_type, "reason": reason},
        )
    logger.info("order.status_changed", tenant_id=tenant_id, order_id=str(order.id), to=to_status)
    return order


def update_order(db: Session, tenant_id: str, actor: User, order_id: str, payload: OrderPatch) -> None:
    order = get_order(db, tenant_id, order_id, lock=True)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(order, field, value)
    write_audit_log(
        db, tenant_id=tenant_id, actor_user_id=str(actor.id), action="order.updated",
        resource_type="order", resource_id=str(order.id), metadata={"fields": sorted(changes)},
    )


def _actor_names(db: Session, tenant_id: str, ids: set[str]) -> dict[str, str]:
    if not ids:
        return {}
    rows = db.query(User.id, User.first_name, User.last_name, User.email).filter(
        User.tenant_id == tenant_id, User.id.in_(ids)
    )
    return {str(i): (" ".join(p for p in (f, ln) if p) or e) for i, f, ln, e in rows}


ACTOR_LABELS = {"customer_sms": "Customer (SMS reply)", "system": "System", "store_sync": "Store sync"}


def status_history(
    db: Session, tenant_id: str, order_ids: list[str], newest_first: bool = False, limit: int | None = None
) -> list[dict[str, Any]]:
    if not order_ids:
        return []
    q = (
        db.query(OrderStatusEvent, Order.order_number)
        .join(Order, and_(Order.id == OrderStatusEvent.order_id, Order.tenant_id == tenant_id))
        .filter(OrderStatusEvent.tenant_id == tenant_id, OrderStatusEvent.order_id.in_(order_ids))
    )
    when = OrderStatusEvent.created_at.desc() if newest_first else OrderStatusEvent.created_at.asc()
    q = q.order_by(when, OrderStatusEvent.id)
    if limit:
        q = q.limit(limit)
    rows = q.all()
    names = _actor_names(db, tenant_id, {str(e.actor_user_id) for e, _ in rows if e.actor_user_id})
    return [
        {
            "id": str(e.id), "order_id": str(e.order_id), "order_number": number,
            "from_status": e.from_status, "to_status": e.to_status, "actor_type": e.actor_type,
            "actor_name": names.get(str(e.actor_user_id)) if e.actor_user_id else ACTOR_LABELS.get(e.actor_type),
            "reason": e.reason, "at": _utc(e.created_at),
        }
        for e, number in rows
    ]


def get_order_detail(db: Session, tenant_id: str, order_id: str, role: str) -> dict[str, Any]:
    from app.services import sms_service

    order = get_order(db, tenant_id, order_id)
    customer = db.get(Customer, order.customer_id) if order.customer_id else None
    items = (
        db.query(OrderItem)
        .filter(OrderItem.tenant_id == tenant_id, OrderItem.order_id == order.id)
        .order_by(OrderItem.created_at, OrderItem.product_snapshot["line"].as_integer(), OrderItem.id)
    )
    lines = []
    for it in items:
        snap = it.product_snapshot or {}
        cost = snap.get("cost_cents")
        lines.append({
            "id": str(it.id), "variant_id": str(it.variant_id) if it.variant_id else None,
            "product_id": snap.get("product_id"), "sku": snap.get("sku"), "title": snap.get("title"),
            "variant": snap.get("variant"), "quantity": it.quantity,
            "unit_price": _major(it.unit_price_cents), "line_total": _major(it.line_total_cents),
            "unit_cost": _major(cost) if cost is not None else None,
        })
    return {
        "id": str(order.id), "order_number": order.order_number, "status": order.status,
        "channel": order.channel, "placed_at": _utc(order.placed_at), "currency": order.currency.strip(),
        "subtotal": _major(order.subtotal_cents), "discount": _major(order.discount_cents),
        "shipping": _major(order.shipping_cents), "tax": _major(order.tax_cents),
        "total": _major(order.total_cents), "payment_method": order.payment_method,
        "payment_status": order.payment_status, "tracking_number": order.tracking_number,
        "tracking_url": order.tracking_url, "shipping_address": order.shipping_address or {},
        "notes": order.notes, "tags": list(order.tags or []), "fulfilled_at": _utc(order.fulfilled_at),
        "delivered_at": _utc(order.delivered_at), "cancelled_at": _utc(order.cancelled_at),
        "customer": None if customer is None else {
            "id": str(customer.id),
            "name": _customer_name(customer.first_name, customer.last_name, None, None),
            "phone": customer.phone, "email": customer.email,
        },
        "items": lines,
        "status_history": status_history(db, tenant_id, [str(order.id)]),
        "confirmation": sms_service.order_confirmation(db, tenant_id, order, customer),
        "allowed_next": allowed_next(order.status, role),
    }
