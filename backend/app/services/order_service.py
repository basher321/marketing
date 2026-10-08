"""Order count metrics (SPEC-BE-006) and the orders list (SPEC-BE-041)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import String, and_, cast, func, or_
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.order import Order, OrderItem

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
        }
        for order, first, last, email, phone, item_count in rows
    ]
    logger.info("orders_listed", tenant_id=tenant_id, total=total, returned=len(items))
    return {"total": int(total), "items": items}
