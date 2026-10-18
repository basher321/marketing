"""Analytics: Sales tab (SPEC-BE-015/016), activity feed (SPEC-BE-022) and the Ads /
Engagement / Customer Service reports (SPEC-BE-050)."""
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.integrations.base_adapter import AD_RESULT_SOURCES
from app.models.approval import ApprovalQueue
from app.models.audit_log import AuditLog
from app.models.conversation import Conversation, Message
from app.models.customer import Customer
from app.models.order import Order, OrderItem
from app.models.product import Product, ProductVariant
from app.models.scheduled_post import ScheduledPost
from app.services import order_service

logger = structlog.get_logger(__name__)

# "Refunded" = orders.status == 'refunded' - the only refund value in the live
# order_status enum (pending, confirmed, processing, shipped, delivered,
# cancelled, refunded). There is no refunds table and no refunded_at column, so
# a refund is attributed to the window its order was *placed* in (placed_at),
# not to when the refund happened.
REFUNDED_STATUSES = ("refunded",)

# Top Products (SPEC-BE-016) returns at most this many rows - a fixed limit,
# never every product unranked.
TOP_PRODUCTS_LIMIT = 10

# Top Products counts only order items whose order status is one of these.
# The live order_status enum has no 'completed' or 'paid' value (and
# orders.payment_status is never populated), so "completed/paid" means
# confirmed or further along. Excluded: pending (not yet confirmed),
# cancelled, refunded.
QUALIFYING_ORDER_STATUSES = ("confirmed", "processing", "shipped", "delivered")


def _major_units(cents: int | Decimal | None) -> float:
    return float(Decimal(cents or 0) / 100)


def _rate_pct(part: int, whole: int) -> float:
    return round(part / whole * 100, 1) if whole else 0.0


def get_sales_summary(db: Session, tenant_id: str) -> dict[str, Any]:
    # One shared moment for every figure, including the reused SPEC-BE-006
    # order count, so all windows line up exactly. Windows match SPEC-BE-006:
    # current = [now-7d, now], previous = [now-14d, now-7d), on placed_at (UTC).
    # Revenue sums orders.total_cents across every order status.
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    in_current = (Order.placed_at >= week_ago) & (Order.placed_at <= now)
    in_previous = (Order.placed_at >= two_weeks_ago) & (Order.placed_at < week_ago)
    refunded = Order.status.in_(REFUNDED_STATUSES)

    rev_cur, rev_prev, all_cur, all_prev, ref_cur, ref_prev = (
        db.query(
            func.coalesce(func.sum(Order.total_cents).filter(in_current), 0),
            func.coalesce(func.sum(Order.total_cents).filter(in_previous), 0),
            func.count(Order.id).filter(in_current),
            func.count(Order.id).filter(in_previous),
            func.count(Order.id).filter(in_current & refunded),
            func.count(Order.id).filter(in_previous & refunded),
        )
        .filter(Order.tenant_id == tenant_id, Order.placed_at >= two_weeks_ago)
        .one()
    )

    # Orders (7d) is SPEC-BE-006's function, not a separate count.
    orders_7d = int(order_service.get_order_metrics(db, tenant_id, now=now)["last_7d"])

    revenue_7d = _major_units(rev_cur)
    revenue_prev = _major_units(rev_prev)
    refund_rate = _rate_pct(int(ref_cur), int(all_cur))
    refund_rate_prev = _rate_pct(int(ref_prev), int(all_prev))

    # Revenue by day: one total per UTC calendar day, today and the 6 days
    # before it, oldest -> newest (the HTML's last bar is "today"). Days are
    # bucketed with placed_at AT TIME ZONE 'UTC' because the Postgres server
    # runs in Asia/Dhaka. The series starts at 00:00 UTC six days ago, so its
    # sum can differ from the rolling revenue_7d above.
    today = now.date()
    first_day = today - timedelta(days=6)
    utc_day = func.date(func.timezone("UTC", Order.placed_at))
    by_day: dict[date, int] = {
        day: int(cents)
        for day, cents in (
            db.query(utc_day, func.sum(Order.total_cents))
            .filter(
                Order.tenant_id == tenant_id,
                Order.placed_at >= datetime.combine(first_day, datetime.min.time(), timezone.utc),
                Order.placed_at <= now,
            )
            .group_by(utc_day)
            .all()
        )
    }

    summary: dict[str, Any] = {
        "revenue_7d": revenue_7d,
        "revenue_7d_delta_pct": order_service.pct_delta(revenue_7d, revenue_prev),
        "orders_7d": orders_7d,
        "aov_7d": round(revenue_7d / orders_7d, 2) if orders_7d else 0.0,
        "refund_rate_7d_pct": refund_rate,
        "refund_rate_7d_delta_pp": round(refund_rate - refund_rate_prev, 1),
        "revenue_by_day": [
            {"date": d, "revenue": _major_units(by_day.get(d, 0))}
            for d in (first_day + timedelta(days=i) for i in range(7))
        ],
    }
    logger.info(
        "sales_summary_computed",
        tenant_id=tenant_id,
        revenue_7d=revenue_7d,
        orders_7d=orders_7d,
        refund_rate_7d_pct=refund_rate,
    )
    return summary


def get_top_products(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    # Windows match get_sales_summary, on the order's placed_at (UTC):
    # current = [now-7d, now], previous = [now-14d, now-7d). Revenue =
    # SUM(order_items.line_total_cents); units = SUM(order_items.quantity).
    # The product is reached via order_items.variant_id -> product_variants ->
    # products; items whose variant was deleted (variant_id NULL) cannot be
    # attributed to a product and are excluded. Order-level discounts and
    # shipping are not allocated to items.
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    in_current = (Order.placed_at >= week_ago) & (Order.placed_at <= now)
    in_previous = (Order.placed_at >= two_weeks_ago) & (Order.placed_at < week_ago)

    revenue_cur = func.coalesce(func.sum(OrderItem.line_total_cents).filter(in_current), 0)
    revenue_prev = func.coalesce(func.sum(OrderItem.line_total_cents).filter(in_previous), 0)
    units_cur = func.coalesce(func.sum(OrderItem.quantity).filter(in_current), 0)

    rows = (
        db.query(Product.id, Product.title, units_cur, revenue_cur, revenue_prev)
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .join(ProductVariant, ProductVariant.id == OrderItem.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(
            OrderItem.tenant_id == tenant_id,
            Order.tenant_id == tenant_id,
            Product.tenant_id == tenant_id,
            Order.status.in_(QUALIFYING_ORDER_STATUSES),
            Order.placed_at >= two_weeks_ago,
            Order.placed_at <= now,
        )
        .group_by(Product.id, Product.title)
        .having(func.count(OrderItem.id).filter(in_current) > 0)
        .order_by(revenue_cur.desc(), units_cur.desc(), Product.title, Product.id)
        .limit(TOP_PRODUCTS_LIMIT)
        .all()
    )

    top = [
        {
            "product_id": str(product_id),
            "product": title,
            "units_sold": int(units),
            "revenue": _major_units(cur),
            # Trend = order_service.pct_delta (same rule as SPEC-BE-006/015):
            # (current - previous) / previous * 100, 1 decimal. A product with
            # revenue this week but none in the previous 7 days gets 100.0;
            # 0 in both windows gets 0.0 - never a division-by-zero error.
            "trend_pct": order_service.pct_delta(_major_units(cur), _major_units(prev)),
        }
        for product_id, title, units, cur, prev in rows
    ]
    logger.info("top_products_computed", tenant_id=tenant_id, count=len(top))
    return top


# ---------------------------------------------------------------------------
# Dashboard "Recent Activity" (SPEC-BE-022). Every item traces to a real row; nothing is
# synthesized. Sources (all filtered by tenant_id, last 24 hours, most recent first):
#   1. audit_log (core/audit.write_audit_log) - only the "significant" actions in
#      ACTIVITY_TEMPLATES below. Excluded as low-level/administrative: tenant.registered,
#      user.*, content.variant_selected, and conversation.draft_generated (a pending draft is
#      already reported by source 2, from the draft row itself). An action without a
#      template is excluded, never shown with a guessed message.
#   2. messages - pending AI reply drafts (outbound, sender 'ai', sent_at NULL, SPEC-BE-026's
#      rule) created in the window: "AI drafted a reply for <customer>".
#   3. scheduled_posts - posts with status 'published' and published_at in the window.
# Messages use only values present on the source rows (approval titles, customer names,
# stock numbers, channels); a missing value falls back to generic wording.
# ---------------------------------------------------------------------------
ACTIVITY_WINDOW = timedelta(hours=24)
ACTIVITY_LIMIT = 20
# action -> (dot kind, message template). Placeholders are filled from real row data.
ACTIVITY_TEMPLATES: dict[str, tuple[str, str]] = {
    "conversation.reply_sent": ("success", "Reply sent to a customer conversation."),
    "conversation.handoff": ("warning", "Conversation handed off to a human agent."),
    "approval.approve": ("success", "Approved: {title}"),
    "approval.reject": ("warning", "Rejected: {title}"),
    "orchestrator.plan_created": ("info", "AI proposed a plan with {actions} action(s)."),
    "content.creative_generated": ("info", "AI generated {variants} creative variant(s)."),
    "inventory.adjust": ("info", "Stock adjusted from {previous} to {new} units."),
    "faq.created": ("info", "New FAQ added to the knowledge base."),
    "brand.updated": ("info", "Brand settings updated."),
}
CHANNEL_NAMES = {
    "facebook": "Facebook", "instagram": "Instagram", "tiktok": "TikTok", "whatsapp": "WhatsApp",
    "messenger": "Messenger", "email": "Email", "sms": "SMS", "web": "Web",
}


def _audit_message(action: str, meta: dict[str, Any], title: str | None) -> tuple[str, str]:
    kind, template = ACTIVITY_TEMPLATES[action]
    if action.startswith("approval."):
        if not title:
            return kind, f"An approval request was {'approved' if action.endswith('approve') else 'rejected'}."
        return kind, template.format(title=title)
    if action == "orchestrator.plan_created":
        return kind, template.format(actions=len(meta.get("approval_ids") or []))
    if action == "content.creative_generated":
        return kind, template.format(variants=meta.get("variant_count", 0))
    if action == "inventory.adjust":
        if meta.get("previous_on_hand") is None or meta.get("new_on_hand") is None:
            return kind, "Stock level adjusted."
        return kind, template.format(previous=meta["previous_on_hand"], new=meta["new_on_hand"])
    return kind, template


def get_recent_activity(
    db: Session, tenant_id: str, now: datetime | None = None
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    since = now - ACTIVITY_WINDOW
    items: list[dict[str, Any]] = []

    audits = db.execute(
        select(AuditLog.id, AuditLog.occurred_at, AuditLog.action, AuditLog.resource_id,
               AuditLog.extra_metadata)
        .where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.occurred_at >= since,
            AuditLog.occurred_at <= now,
            AuditLog.action.in_(tuple(ACTIVITY_TEMPLATES)),
        )
        .order_by(AuditLog.occurred_at.desc())
        .limit(ACTIVITY_LIMIT)
    ).all()
    approval_ids = [a.resource_id for a in audits if a.action.startswith("approval.") and a.resource_id]
    titles = (
        {
            str(i): t
            for i, t in db.execute(
                select(ApprovalQueue.id, ApprovalQueue.title).where(
                    ApprovalQueue.tenant_id == tenant_id, ApprovalQueue.id.in_(approval_ids)
                )
            ).all()
        }
        if approval_ids
        else {}
    )
    for a in audits:
        meta = a.extra_metadata if isinstance(a.extra_metadata, dict) else {}
        kind, message = _audit_message(a.action, meta, titles.get(str(a.resource_id)))
        items.append({"id": f"audit:{a.id}", "occurred_at": a.occurred_at, "kind": kind, "message": message})

    drafts = db.execute(
        select(Message.id, Message.created_at, Customer.first_name, Customer.last_name)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .outerjoin(
            Customer,
            (Customer.id == Conversation.customer_id) & (Customer.tenant_id == tenant_id),
        )
        .where(
            Message.tenant_id == tenant_id,
            Conversation.tenant_id == tenant_id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
            Message.sent_at.is_(None),
            Message.created_at >= since,
            Message.created_at <= now,
        )
        .order_by(Message.created_at.desc())
        .limit(ACTIVITY_LIMIT)
    ).all()
    for d in drafts:
        name = " ".join(p for p in (d.first_name, d.last_name) if p) or "a customer"
        items.append({
            "id": f"draft:{d.id}",
            "occurred_at": d.created_at,
            "kind": "info",
            "message": f"AI drafted a reply for {name} — awaiting your approval.",
        })

    posts = db.execute(
        select(ScheduledPost.id, ScheduledPost.published_at, ScheduledPost.channel)
        .where(
            ScheduledPost.tenant_id == tenant_id,
            ScheduledPost.status == "published",
            ScheduledPost.published_at >= since,
            ScheduledPost.published_at <= now,
        )
        .order_by(ScheduledPost.published_at.desc())
        .limit(ACTIVITY_LIMIT)
    ).all()
    for p in posts:
        items.append({
            "id": f"post:{p.id}",
            "occurred_at": p.published_at,
            "kind": "success",
            "message": f"{CHANNEL_NAMES.get(p.channel, p.channel)} post published.",
        })

    items.sort(key=lambda i: i["occurred_at"], reverse=True)
    items = items[:ACTIVITY_LIMIT]
    for i in items:
        i["occurred_at"] = i["occurred_at"].astimezone(timezone.utc)
    logger.info("recent_activity_computed", tenant_id=tenant_id, count=len(items))
    return {"items": items}


# ---------------------------------------------------------------------------
# Ads / Engagement / Customer Service reports (SPEC-BE-050)
# ---------------------------------------------------------------------------
# Rule: a metric with no source data is None (shown as "—" with a reason),
# never estimated. Every query is tenant-scoped; days are the tenant's local
# calendar days (tenants.timezone), and every day of the window is present
# (zero-filled). Window = the last `days` local days, today included.
RANGE_DAYS = {"7d": 7, "30d": 30, "90d": 90}
ADS_MISSING = "No impression, click or revenue data yet — connect an ads account in Integrations."
ENGAGEMENT_MISSING = (
    "Post engagement isn't imported yet — connect Facebook, Instagram or TikTok in Integrations."
)


def _window(db: Session, tenant_id: str, days: int) -> tuple[str, date, date, datetime]:
    tz: str = db.execute(text("SELECT timezone FROM tenants WHERE id = :t"), {"t": tenant_id}).scalar() or "UTC"
    today: date = db.execute(text("SELECT (now() AT TIME ZONE :tz)::date"), {"tz": tz}).scalar_one()
    start = today - timedelta(days=days - 1)
    start_utc: datetime = db.execute(
        text("SELECT (CAST(:d AS timestamp) AT TIME ZONE :tz)"), {"d": start, "tz": tz}
    ).scalar_one()
    return tz, start, today, start_utc


def _half_up(value: Any, places: int) -> float:
    # Decimal half-up (4.625 -> 4.63), matching SQL round(); float round() would
    # give 4.62 because 4.625 isn't exact in binary.
    return float(Decimal(str(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def _series(
    start: date, end: date, values: dict[date, Any], fields: tuple[str, ...]
) -> list[dict[str, Any]]:
    out, day = [], start
    while day <= end:
        row = values.get(day, {})
        out.append({"date": day, **{f: row.get(f, 0) for f in fields}})
        day += timedelta(days=1)
    return out


# Spend = analytics_events metric 'spend_cents' (the SPEC-BE-019 source) on
# entity 'campaign', or on 'ad' mapped ad -> ad_group -> campaign.
_SPEND_CTE = """
    WITH spend AS (
      SELECT e.event_time, e.value,
             CASE WHEN e.entity_type = 'campaign' THEN e.entity_id ELSE g.campaign_id END
               AS campaign_id
      FROM analytics_events e
      LEFT JOIN ads a ON e.entity_type = 'ad' AND a.id = e.entity_id AND a.tenant_id = e.tenant_id
      LEFT JOIN ad_groups g ON g.id = a.ad_group_id AND g.tenant_id = e.tenant_id
      WHERE e.tenant_id = :t AND e.metric = 'spend_cents' AND e.entity_type IN ('campaign', 'ad')
    )"""


def get_ads_report(db: Session, tenant_id: str, range_key: str) -> dict[str, Any]:
    days = RANGE_DAYS[range_key]
    tz, start, today, start_utc = _window(db, tenant_id, days)
    p = {"t": tenant_id, "tz": tz, "since": start_utc}
    by_day: dict[Any, dict[str, Any]] = {
        r.d: {"spend": _major_units(r.cents)}
        for r in db.execute(
            text(
                _SPEND_CTE
                + " SELECT (event_time AT TIME ZONE :tz)::date AS d, SUM(value) AS cents"
                " FROM spend WHERE event_time >= :since GROUP BY 1"
            ),
            p,
        )
    }
    currency = (db.execute(text("SELECT currency FROM tenants WHERE id = :t"), p).scalar() or "USD").strip()
    campaigns = db.execute(
        text(
            _SPEND_CTE
            + """
            SELECT c.id, c.name, c.status::text AS status, c.channels::text[] AS channels,
                   c.budget_cents, c.starts_at, c.ends_at,
                   COALESCE(SUM(s.value) FILTER (WHERE s.event_time >= :since), 0) AS window_cents,
                   COALESCE(SUM(s.value), 0) AS total_cents
            FROM campaigns c LEFT JOIN spend s ON s.campaign_id = c.id
            WHERE c.tenant_id = :t AND c.status IN ('running', 'scheduled', 'paused')
            GROUP BY c.id ORDER BY window_cents DESC, c.name"""
        ),
        p,
    ).all()
    now = datetime.now(timezone.utc)
    rows = []
    for c in campaigns:
        # Pacing = lifetime spend / (budget x elapsed share of the schedule);
        # None without dates/budget or before the start.
        pacing = None
        if c.starts_at and c.ends_at and c.budget_cents and c.ends_at > c.starts_at:
            share = min(1.0, max(0.0, (now - c.starts_at) / (c.ends_at - c.starts_at)))
            if share > 0:
                pacing = round(float(c.total_cents) / (c.budget_cents * share) * 100, 1)
        rows.append(
            {
                "id": str(c.id),
                "name": c.name,
                "status": c.status,
                "channels": list(c.channels or []),
                "budget": _major_units(c.budget_cents),
                "spend": _major_units(c.window_cents),
                "pacing_pct": pacing,
                "starts_at": c.starts_at.astimezone(timezone.utc) if c.starts_at else None,
                "ends_at": c.ends_at.astimezone(timezone.utc) if c.ends_at else None,
            }
        )
    budget_total = sum(r["budget"] for r in rows)
    lifetime = sum(_major_units(c.total_cents) for c in campaigns)
    # Ad results: imported analytics_events rows from every ad platform
    # (source in AD_RESULT_SOURCES: Meta SPEC-BE-056, others SPEC-BE-062).
    # A metric Meta didn't report stays None; CTR = link clicks / impressions,
    # ROAS = purchase value / spend; conversions = purchases + leads + installs.
    meta_rows = db.execute(
        text(
            "SELECT (event_time AT TIME ZONE :tz)::date AS d, metric, SUM(value) AS v FROM analytics_events "
            "WHERE tenant_id = :t AND source = ANY(:sources) AND event_time >= :since GROUP BY 1, 2"
        ),
        {**p, "sources": list(AD_RESULT_SOURCES)},
    ).all()
    sources = [r[0] for r in db.execute(
        text("SELECT DISTINCT source FROM analytics_events WHERE tenant_id = :t AND source = ANY(:sources) AND event_time >= :since ORDER BY 1"),
        {**p, "sources": list(AD_RESULT_SOURCES)},
    ).all()]
    meta_day: dict[Any, dict[str, float]] = {}
    meta_tot: dict[str, float] = {}
    for r in meta_rows:
        meta_day.setdefault(r.d, {})[r.metric] = float(r.v)
        meta_tot[r.metric] = meta_tot.get(r.metric, 0.0) + float(r.v)

    def _ratio(num: float | None, den: float | None, scale: float = 1.0, places: int = 2) -> float | None:
        return round(num / den * scale, places) if num is not None and den else None

    for day_row in _series(start, today, by_day, ("spend",)):
        m = meta_day.get(day_row["date"], {})
        by_day.setdefault(day_row["date"], {"spend": 0})
        by_day[day_row["date"]].update(
            impressions=int(m["impressions"]) if "impressions" in m else None,
            clicks=int(m["link_clicks"]) if "link_clicks" in m else None,
            ctr=_ratio(m.get("link_clicks"), m.get("impressions"), 100),
            roas=_ratio(m.get("purchase_value_cents"), m.get("spend_cents")),
        )
    conversions = [meta_tot[k] for k in ("purchases", "leads", "app_installs") if k in meta_tot]
    return {
        "currency": currency,
        "range": range_key,
        "totals": {
            "spend": round(sum(v["spend"] for v in by_day.values()), 2),
            "active_campaigns": sum(1 for r in rows if r["status"] == "running"),
            "budget_total": budget_total,
            # Lifetime spend of the listed campaigns / their total budget.
            "budget_used_pct": round(lifetime / budget_total * 100, 1) if budget_total else None,
            "impressions": int(meta_tot["impressions"]) if "impressions" in meta_tot else None,
            "clicks": int(meta_tot["link_clicks"]) if "link_clicks" in meta_tot else None,
            "ctr": _ratio(meta_tot.get("link_clicks"), meta_tot.get("impressions"), 100),
            "roas": _ratio(meta_tot.get("purchase_value_cents"), meta_tot.get("spend_cents")),
            "reach": int(meta_tot["reach"]) if "reach" in meta_tot else None,
            "conversions": int(sum(conversions)) if conversions else None,
            "missing_reason": "" if meta_rows else ADS_MISSING,
            # Which platforms the results came from, e.g. "meta" or "meta, tiktok".
            "source": ", ".join(sources) if sources else None,
        },
        "spend_by_day": [
            {**row, **{k: by_day.get(row["date"], {}).get(k) for k in ("impressions", "clicks", "ctr", "roas")}}
            for row in _series(start, today, by_day, ("spend",))
        ],
        "campaigns": rows,
    }


def get_engagement_report(db: Session, tenant_id: str, range_key: str) -> dict[str, Any]:
    days = RANGE_DAYS[range_key]
    tz, start, today, start_utc = _window(db, tenant_id, days)
    p = {"t": tenant_id, "tz": tz, "since": start_utc}
    # Published / failed are counted in the window (published_at / updated_at);
    # scheduled / pending are the current pipeline (upcoming, any date).
    counts = db.execute(
        text(
            """
            SELECT
              COUNT(*) FILTER (WHERE status = 'published' AND published_at >= :since) AS published,
              COUNT(*) FILTER (WHERE status = 'failed' AND updated_at >= :since) AS failed,
              COUNT(*) FILTER (WHERE status = 'scheduled') AS scheduled,
              COUNT(*) FILTER (WHERE status = 'pending') AS pending
            FROM scheduled_posts WHERE tenant_id = :t"""
        ),
        p,
    ).one()
    by_channel = [
        {"channel": r.channel, "published": int(r.published), "scheduled": int(r.scheduled)}
        for r in db.execute(
            text(
                """
                SELECT channel::text AS channel,
                  COUNT(*) FILTER (WHERE status = 'published' AND published_at >= :since) AS published,
                  COUNT(*) FILTER (WHERE status IN ('scheduled', 'pending')) AS scheduled
                FROM scheduled_posts WHERE tenant_id = :t GROUP BY 1 ORDER BY 1"""
            ),
            p,
        )
        if r.published or r.scheduled
    ]
    # Chart: the look-back window plus the next 7 days, so upcoming posts show.
    end = today + timedelta(days=7)
    by_day: dict[date, dict[str, int]] = {}
    for r in db.execute(
        text(
            """
            SELECT (COALESCE(published_at, scheduled_at) AT TIME ZONE :tz)::date AS d,
              COUNT(*) FILTER (WHERE status = 'published') AS published,
              COUNT(*) FILTER (WHERE status IN ('scheduled', 'pending')) AS scheduled
            FROM scheduled_posts
            WHERE tenant_id = :t AND COALESCE(published_at, scheduled_at) >= :since
            GROUP BY 1"""
        ),
        p,
    ):
        if r.d <= end:
            by_day[r.d] = {"published": int(r.published), "scheduled": int(r.scheduled)}
    content: dict[str, int] = {
        str(status): int(n)
        for status, n in db.execute(
            text("SELECT status::text, COUNT(*) FROM content_assets WHERE tenant_id = :t GROUP BY 1"), p
        ).all()
    }
    return {
        "range": range_key,
        "posts": {k: int(getattr(counts, k)) for k in ("published", "scheduled", "pending", "failed")},
        "posts_by_channel": by_channel,
        "posts_by_day": _series(start, end, by_day, ("published", "scheduled")),
        "content": {
            k: int(content.get(k, 0)) for k in ("draft", "pending_approval", "approved", "published")
        },
        "likes": None,
        "comments": None,
        "shares": None,
        "reach": None,
        "missing_reason": ENGAGEMENT_MISSING,
    }


def get_service_report(db: Session, tenant_id: str, range_key: str) -> dict[str, Any]:
    days = RANGE_DAYS[range_key]
    tz, start, today, start_utc = _window(db, tenant_id, days)
    p = {"t": tenant_id, "tz": tz, "since": start_utc}
    # Conversations created in the window. There is no 'escalated' status in
    # the live conversation_status enum (open, pending, resolved, archived):
    # escalated = metadata.handed_off_at is set (the SPEC-BE-007 inbox rule).
    c = db.execute(
        text(
            """
            SELECT COUNT(*) AS total,
              COUNT(*) FILTER (WHERE status = 'open') AS open,
              COUNT(*) FILTER (WHERE status = 'pending') AS pending,
              COUNT(*) FILTER (WHERE status = 'resolved') AS resolved,
              COUNT(*) FILTER (WHERE metadata ? 'handed_off_at') AS escalated,
              AVG(csat_score) AS csat_avg, COUNT(csat_score) AS csat_n,
              AVG(EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600)
                FILTER (WHERE resolved_at IS NOT NULL) AS resolution_h
            FROM conversations WHERE tenant_id = :t AND created_at >= :since"""
        ),
        p,
    ).one()
    by_channel = [
        {"channel": r.channel, "total": int(r.total), "resolved": int(r.resolved)}
        for r in db.execute(
            text(
                """
                SELECT channel::text AS channel, COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE status = 'resolved') AS resolved
                FROM conversations WHERE tenant_id = :t AND created_at >= :since
                GROUP BY 1 ORDER BY 2 DESC, 1"""
            ),
            p,
        )
    ]
    by_day: dict[date, dict[str, int]] = {}
    for r in db.execute(
        text(
            "SELECT (created_at AT TIME ZONE :tz)::date AS d, COUNT(*) AS n FROM conversations"
            " WHERE tenant_id = :t AND created_at >= :since GROUP BY 1"
        ),
        p,
    ):
        by_day.setdefault(r.d, {})["new"] = int(r.n)
    for r in db.execute(
        text(
            "SELECT (resolved_at AT TIME ZONE :tz)::date AS d, COUNT(*) AS n FROM conversations"
            " WHERE tenant_id = :t AND resolved_at >= :since GROUP BY 1"
        ),
        p,
    ):
        by_day.setdefault(r.d, {})["resolved"] = int(r.n)
    # First response = first *sent* outbound message (sent_at, so a pending AI
    # draft - sent_at NULL - never counts) after the conversation's first inbound
    # message (conversations.first_response_at is empty live).
    first_resp = db.execute(
        text(
            """
            WITH first_in AS (
              SELECT m.conversation_id, MIN(m.created_at) AS t_in
              FROM messages m
              JOIN conversations cv ON cv.id = m.conversation_id AND cv.tenant_id = m.tenant_id
              WHERE m.tenant_id = :t AND m.direction = 'inbound' AND cv.created_at >= :since
              GROUP BY 1
            ), first_out AS (
              SELECT f.conversation_id, MIN(m.sent_at) - f.t_in AS gap
              FROM first_in f
              JOIN messages m ON m.conversation_id = f.conversation_id AND m.tenant_id = :t
              WHERE m.direction = 'outbound' AND m.sent_at >= f.t_in
              GROUP BY f.conversation_id, f.t_in
            )
            SELECT AVG(EXTRACT(EPOCH FROM gap) / 60) FROM first_out"""
        ),
        p,
    ).scalar()
    # Replies = outbound messages actually sent in the window, by sender; pending
    # AI drafts (sent_at NULL) aren't replies yet.
    replies: dict[str, int] = {
        str(sender): int(n)
        for sender, n in db.execute(
            text(
                """
                SELECT sender_type::text, COUNT(*) FROM messages
                WHERE tenant_id = :t AND direction = 'outbound' AND sent_at >= :since
                  AND sender_type IN ('ai', 'agent')
                GROUP BY 1"""
            ),
            p,
        ).all()
    }
    ai, agent = int(replies.get("ai", 0)), int(replies.get("agent", 0))
    # Deflection = resolved conversations with no agent-sent message / resolved.
    deflected = db.execute(
        text(
            """
            SELECT COUNT(*) FROM conversations cv
            WHERE cv.tenant_id = :t AND cv.created_at >= :since AND cv.status = 'resolved'
              AND NOT EXISTS (
                SELECT 1 FROM messages m
                WHERE m.conversation_id = cv.id AND m.tenant_id = :t AND m.sender_type = 'agent')"""
        ),
        p,
    ).scalar() or 0
    resolved = int(c.resolved)
    return {
        "range": range_key,
        "conversations": {
            k: int(getattr(c, k)) for k in ("total", "open", "pending", "resolved", "escalated")
        },
        "by_channel": by_channel,
        "by_day": _series(start, today, by_day, ("new", "resolved")),
        "first_response_minutes_avg": _half_up(first_resp, 1) if first_resp is not None else None,
        "resolution_hours_avg": _half_up(c.resolution_h, 1) if c.resolution_h is not None else None,
        "csat_avg": _half_up(c.csat_avg, 2) if c.csat_avg is not None else None,
        "csat_responses": int(c.csat_n),
        "replies": {
            "ai": ai,
            "agent": agent,
            "ai_share_pct": _half_up(Decimal(ai) / (ai + agent) * 100, 1) if ai + agent else None,
        },
        "deflection_pct": _half_up(Decimal(int(deflected)) / resolved * 100, 1) if resolved else None,
    }


# ---------------------------------------------------------------------------
# Organic analytics (SPEC-BE-078 Part A)
# ---------------------------------------------------------------------------
# Rows: analytics_events event_type 'organic_post_metrics', entity
# 'scheduled_post' = our post id, source 'organic_<platform>' (never in
# AD_RESULT_SOURCES, so ad reports don't read them), one row per metric. Each
# value is the post's lifetime total at import time (a snapshot); an import
# replaces that post's snapshot of the same tenant-local day. The report uses
# each post's latest snapshot and attributes it to the post's publish day.
# A metric the platform didn't give is absent -> null, never estimated.
ORGANIC_EVENT = "organic_post_metrics"
ORGANIC_METRICS = ("impressions", "reach", "likes", "comments", "shares", "saves", "clicks", "video_views")
ENGAGEMENT_METRICS = ("likes", "comments", "shares", "saves")
ORGANIC_IMPORT_DAYS = 30
ORGANIC_THROTTLE = timedelta(minutes=5)
ORGANIC_MISSING = "No post results imported yet — results arrive a few hours after posts are published (or press Import now)."


def import_organic_metrics(db: Session, tenant_id: str, actor_user_id: str | None = None, throttle: bool = True) -> dict[str, Any]:
    from sqlalchemy import column, delete, insert, table
    from sqlalchemy.dialects.postgresql import JSONB

    from app.core.audit import write_audit_log
    from app.core.exceptions import AppError
    from app.integrations.social_base import PLATFORMS, SocialError, adapter
    from app.services import social_account_service

    now = datetime.now(timezone.utc)
    if throttle:
        last = db.execute(text("SELECT MAX(created_at) FROM analytics_events WHERE tenant_id = :t AND event_type = :e"),
                          {"t": tenant_id, "e": ORGANIC_EVENT}).scalar()
        if last is not None and now - last.astimezone(timezone.utc) < ORGANIC_THROTTLE:
            wait = int((ORGANIC_THROTTLE - (now - last.astimezone(timezone.utc))).total_seconds() // 60) + 1
            raise AppError(f"Results were imported moments ago; try again in {wait} min.", 429)
    events = table("analytics_events", column("tenant_id"), column("event_time"), column("event_type"), column("entity_type"),
                   column("entity_id"), column("metric"), column("value"), column("dimensions", JSONB), column("source"))
    tz = db.execute(text("SELECT timezone FROM tenants WHERE id = :t"), {"t": tenant_id}).scalar() or "UTC"
    day_start = db.execute(text("SELECT date_trunc('day', now() AT TIME ZONE :tz) AT TIME ZONE :tz"), {"tz": tz}).scalar_one()
    stats: dict[str, Any] = {"posts": 0, "rows": 0, "platforms": {}, "errors": []}
    for platform in PLATFORMS:
        posts = (
            db.query(ScheduledPost)
            .filter(ScheduledPost.tenant_id == tenant_id, ScheduledPost.channel == platform, ScheduledPost.status == "published",
                    ScheduledPost.external_post_id.isnot(None), ScheduledPost.published_at >= now - timedelta(days=ORGANIC_IMPORT_DAYS))
            .all()
        )
        if not posts:
            continue
        try:
            conn = social_account_service.connection(db, tenant_id, platform)
            # SPEC-BE-104: only posts published the way the account is connected now
            # (a SocialAPI post's external id is SocialAPI's post id, not the platform's).
            via = conn.get("via") or "direct"
            posts = [p for p in posts if ((p.extra_metadata or {}).get("via") or "direct") == via]
            if not posts:
                continue
            metrics = adapter(platform, via).metrics(conn["fields"], [str(p.external_post_id) for p in posts])
        except (SocialError, AppError) as exc:
            stats["errors"].append(f"{platform}: {getattr(exc, 'message', None) or getattr(exc, 'detail', str(exc))}")
            continue
        ids = [str(p.id) for p in posts]
        db.execute(delete(events).where(events.c.tenant_id == tenant_id, events.c.event_type == ORGANIC_EVENT,
                                        events.c.entity_id.in_(ids), events.c.event_time >= day_start))
        rows = []
        for p in posts:
            for metric, value in (metrics.get(str(p.external_post_id)) or {}).items():
                if value is None or metric not in ORGANIC_METRICS:
                    continue
                rows.append({"tenant_id": tenant_id, "event_time": now, "event_type": ORGANIC_EVENT, "entity_type": "scheduled_post",
                             "entity_id": str(p.id), "metric": metric, "value": value,
                             "dimensions": {"platform": platform, "integration_id": conn["integration_id"]}, "source": f"organic_{platform}"})
        if rows:
            db.execute(insert(events), rows)
        # SPEC-BE-080: the Accounts page shows this as "last results sync".
        db.execute(text("UPDATE integrations SET last_sync_at = :now WHERE id = :i AND tenant_id = :t"),
                   {"now": now, "i": conn["integration_id"], "t": tenant_id})
        stats["posts"] += len(posts)
        stats["rows"] += len(rows)
        stats["platforms"][platform] = len(posts)
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor_user_id, action="analytics.organic_import", resource_type="tenant",
                    resource_id=tenant_id, metadata={"posts": stats["posts"], "rows": stats["rows"], "errors": len(stats["errors"])})
    logger.info("organic_metrics_imported", tenant_id=tenant_id, posts=stats["posts"], rows=stats["rows"])
    return stats


def get_organic_report(db: Session, tenant_id: str, range_key: str) -> dict[str, Any]:
    days = RANGE_DAYS[range_key]
    tz, start, today, start_utc = _window(db, tenant_id, days)
    p = {"t": tenant_id, "tz": tz, "since": start_utc, "e": ORGANIC_EVENT}
    published = db.execute(
        text(
            """
            SELECT sp.id::text AS id, sp.channel::text AS platform, sp.external_url, sp.published_at,
                   (sp.published_at AT TIME ZONE :tz)::date AS d, ca.variants, ca.selected_variant_index
            FROM scheduled_posts sp JOIN content_assets ca ON ca.id = sp.content_asset_id AND ca.tenant_id = sp.tenant_id
            WHERE sp.tenant_id = :t AND sp.status = 'published' AND ca.format = 'organic_post' AND sp.published_at >= :since"""
        ),
        p,
    ).all()
    published = list(published)
    ids = [r.id for r in published]
    latest: dict[str, dict[str, float]] = {}
    if ids:
        for r in db.execute(
            text(
                """
                SELECT DISTINCT ON (entity_id, metric) entity_id::text AS id, metric, value
                FROM analytics_events
                WHERE tenant_id = :t AND event_type = :e AND entity_id::text = ANY(:ids)
                ORDER BY entity_id, metric, event_time DESC"""
            ),
            {**p, "ids": ids},
        ):
            latest.setdefault(r.id, {})[r.metric] = float(r.value)

    def total(rows: list[Any], metric: str) -> float | None:
        vals = [latest[r.id][metric] for r in rows if metric in latest.get(r.id, {})]
        return float(sum(vals)) if vals else None

    def engagement(rows: list[Any]) -> float | None:
        parts = [total(rows, m) for m in ENGAGEMENT_METRICS]
        known = [x for x in parts if x is not None]
        return float(sum(known)) if known else None

    def rate(eng: float | None, impressions: float | None) -> float | None:
        if eng is None or not impressions:
            return None
        return _half_up(eng * 100 / impressions, 2)

    totals = {m: total(published, m) for m in ORGANIC_METRICS}
    totals["engagements"] = engagement(published)
    by_platform = []
    for platform in ("facebook", "instagram", "tiktok", "linkedin"):
        rows = [r for r in published if r.platform == platform]
        impressions = total(rows, "impressions")
        eng = engagement(rows)
        by_platform.append({"platform": platform, "posts_published": len(rows), "impressions": impressions,
                            "engagements": eng, "engagement_rate": rate(eng, impressions)})
    daily_values: dict[date, dict[str, Any]] = {}
    for d in {r.d for r in published}:
        rows = [r for r in published if r.d == d]
        daily_values[d] = {"posts": len(rows), "impressions": total(rows, "impressions"), "engagements": engagement(rows)}
    daily = []
    day = start
    while day <= today:
        row = daily_values.get(day, {})
        daily.append({"date": day, "posts": int(row.get("posts", 0)), "impressions": row.get("impressions"), "engagements": row.get("engagements")})
        day += timedelta(days=1)
    top = []
    for r in published:
        eng = engagement([r])
        if eng is None:
            continue
        variants = r.variants or [{}]
        idx = r.selected_variant_index if r.selected_variant_index is not None and r.selected_variant_index < len(variants) else 0
        caption = " ".join(str((variants[idx] or {}).get("caption") or "").split())
        top.append({"post_id": r.id, "platform": r.platform, "excerpt": caption[:120], "external_url": r.external_url,
                    "published_at": r.published_at.astimezone(timezone.utc), "engagements": eng,
                    "impressions": latest.get(r.id, {}).get("impressions")})
    top.sort(key=lambda x: -x["engagements"])
    last_import = db.execute(text("SELECT MAX(created_at) FROM analytics_events WHERE tenant_id = :t AND event_type = :e"), p).scalar()
    return {
        "range": range_key,
        "timezone": tz,
        "posts_published": len(published),
        "totals": totals,
        "engagement_rate": rate(totals["engagements"], totals["impressions"]),
        "by_platform": by_platform,
        "daily": daily,
        "top_posts": top[:10],
        "last_import_at": last_import.astimezone(timezone.utc) if last_import else None,
        "missing_reason": None if latest else ORGANIC_MISSING,
    }
