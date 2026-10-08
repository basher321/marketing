"""Paid Marketing lists across campaigns (SPEC-BE-079).

Ad sets (`ad_groups`) and ads from all three builders in one list:
- Meta builder (SPEC-BE-055): campaigns.metadata has "builder", platform null/"meta";
  settings in ad_groups.metadata / ads.metadata.
- Multi-platform builder (SPEC-BE-062): campaigns.metadata.platform is one of the
  six other keys; settings in metadata.platform_fields / metadata.creative.
- Legacy wizard (SPEC-BE-047): neither key; rows created at launch.

Results come from analytics_events. Meta imports per-ad rows (entity_type
'ad', SPEC-BE-056), so an ad has its own numbers and an ad set the sum of its
ads. The other platforms import per-campaign rows only (SPEC-BE-062): their ad
sets and ads get null results with results_level "campaign". No rows -> null,
never 0 or an estimate.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import and_, not_, or_, text
from sqlalchemy.orm import Query, Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.campaign import Ad, AdGroup, Campaign
from app.services import ads_builder_service, meta_builder_service

logger = structlog.get_logger(__name__)

RANGE_DAYS = {"7d": 7, "30d": 30, "90d": 90}
TEXT_EXCERPT = 160


def _platform(c: Campaign) -> str:
    md = c.extra_metadata or {}
    platform = md.get("platform")
    if platform in ads_builder_service.BUILDER_PLATFORMS:
        return str(platform)
    return "meta" if "builder" in md else "wizard"


def _platform_filter(query: Query[Any], platform: str) -> Query[Any]:
    md = Campaign.extra_metadata
    stored = md["platform"].astext
    if platform == "meta":
        return query.filter(md.has_key("builder"), or_(stored.is_(None), stored == "meta"))  # type: ignore[attr-defined]
    if platform == "wizard":
        return query.filter(not_(md.has_key("builder")), stored.is_(None))  # type: ignore[attr-defined]
    return query.filter(stored == platform)


def _major(cents: Any) -> float | None:
    return None if cents is None else float(Decimal(int(cents)) / 100)


def _utc(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.astimezone(timezone.utc)


def _meta_ad_results(db: Session, tenant_id: str, ad_ids: list[str], days: int) -> dict[str, dict[str, float]]:
    """{ad_id: {metric: sum}} over Meta's per-ad rows in the window."""
    if not ad_ids:
        return {}
    since = datetime.now(timezone.utc) - timedelta(days=days)
    out: dict[str, dict[str, float]] = {}
    for row in db.execute(
        text(
            "SELECT entity_id::text AS id, metric, SUM(value) AS v FROM analytics_events "
            "WHERE tenant_id = :t AND source = 'meta' AND entity_type = 'ad' AND entity_id::text = ANY(:ids) "
            "AND event_time >= :since AND metric IN ('spend_cents', 'impressions', 'link_clicks', 'clicks') "
            "GROUP BY entity_id, metric"
        ),
        {"t": tenant_id, "ids": ad_ids, "since": since},
    ):
        out.setdefault(row.id, {})[row.metric] = float(row.v)
    return out


def _results(rows: list[dict[str, float]], level: str | None) -> dict[str, Any]:
    empty = {"spend": None, "impressions": None, "clicks": None, "ctr": None, "results_level": level}
    if level != "ad" or not rows:
        return empty

    def total(metric: str) -> float | None:
        vals = [r[metric] for r in rows if metric in r]
        return float(sum(vals)) if vals else None

    spend, impressions = total("spend_cents"), total("impressions")
    # CTR uses link clicks, as the campaign KPIs do (campaign_service._campaign_kpis).
    clicks = total("link_clicks")
    if clicks is None:
        clicks = total("clicks")
    return {
        "spend": round(spend / 100, 2) if spend is not None else None,
        "impressions": int(impressions) if impressions is not None else None,
        "clicks": int(clicks) if clicks is not None else None,
        "ctr": round(clicks / impressions * 100, 2) if clicks is not None and impressions else None,
        "results_level": "ad",
    }


def _level(platform: str) -> str | None:
    return "ad" if platform == "meta" else None if platform == "wizard" else "campaign"


def _base_filters(query: Query[Any], tenant_id: str, platform: str | None, status: str | None,
                  campaign_id: str | None, q: str | None, model: type[AdGroup] | type[Ad]) -> Query[Any]:
    query = query.filter(Campaign.tenant_id == tenant_id)
    if platform:
        query = _platform_filter(query, platform)
    if status:
        query = query.filter(model.status == status)
    if campaign_id:
        query = query.filter(Campaign.id == campaign_id)
    if q:
        pattern = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(model.name.ilike(f"%{pattern}%", escape="\\"))
    return query


# ---------------------------------------------------------------------------
# Ad sets
# ---------------------------------------------------------------------------
def _ad_set_fields(g: AdGroup, platform: str) -> dict[str, Any]:
    md = dict(g.extra_metadata or {})
    if platform == "meta":
        return {
            "budget": _major(g.budget_cents),
            # No ad-set budget = the campaign's budget (CBO).
            "budget_type": (md.get("budget_type") or "daily") if g.budget_cents else "campaign",
            "starts_at": _utc(md.get("starts_at")), "ends_at": _utc(md.get("ends_at")),
            "performance_goal": md.get("optimization_goal"),
            "effective_status": md.get("effective_status"), "last_error": md.get("last_error"),
        }
    if platform == "wizard":
        return {"budget": _major(g.budget_cents), "budget_type": "daily" if g.budget_cents else None,
                "starts_at": None, "ends_at": None, "performance_goal": None, "effective_status": None, "last_error": None}
    f = dict(md.get("platform_fields") or {})
    mode = f.get("budget_mode") or "none"
    fields = dict(f.get("fields") or {})
    return {
        "budget": _major(f.get("budget_cents")),
        "budget_type": mode if mode in ("daily", "lifetime") else "campaign",
        "starts_at": _utc(f.get("starts_at")), "ends_at": _utc(f.get("ends_at")),
        "performance_goal": fields.get("optimization_goal") or fields.get("bid_strategy"),
        "effective_status": None, "last_error": None,
    }


def list_ad_sets(db: Session, tenant_id: str, *, platform: str | None = None, status: str | None = None,
                 campaign_id: str | None = None, q: str | None = None, range_key: str = "30d",
                 page: int = 1, page_size: int = 50) -> dict[str, Any]:
    query = _base_filters(db.query(AdGroup).join(Campaign, Campaign.id == AdGroup.campaign_id).filter(AdGroup.tenant_id == tenant_id),
                          tenant_id, platform, status, campaign_id, q, AdGroup)
    count = query.order_by(None).count()
    groups = (
        query.order_by(Campaign.created_at.desc(), Campaign.id, AdGroup.created_at, AdGroup.id)
        .offset((page - 1) * page_size).limit(page_size).all()
    )
    ads_by_group: dict[str, list[str]] = {}
    if groups:
        for gid, aid in db.query(Ad.ad_group_id, Ad.id).filter(Ad.tenant_id == tenant_id, Ad.ad_group_id.in_([g.id for g in groups])):
            ads_by_group.setdefault(str(gid), []).append(str(aid))
    meta_ads = [a for g in groups if _platform(g.campaign) == "meta" for a in ads_by_group.get(str(g.id), [])]
    results = _meta_ad_results(db, tenant_id, meta_ads, RANGE_DAYS[range_key])
    items = []
    for g in groups:
        c = g.campaign
        p = _platform(c)
        ad_ids = ads_by_group.get(str(g.id), [])
        items.append({
            "id": str(g.id), "name": g.name, "campaign_id": str(c.id), "campaign_name": c.name, "platform": p,
            "status": g.status, "currency": c.currency.strip(), "ads_count": len(ad_ids),
            **_ad_set_fields(g, p),
            **_results([results[a] for a in ad_ids if a in results], _level(p)),
        })
    logger.info("paid_ad_sets_listed", tenant_id=tenant_id, count=count)
    return {"count": count, "items": items}


# ---------------------------------------------------------------------------
# Ads
# ---------------------------------------------------------------------------
def _ad_fields(ad: Ad, platform: str) -> dict[str, Any]:
    md = dict(ad.extra_metadata or {})
    if platform == "meta":
        media = md.get("media") or []
        first = media[0] if media and isinstance(media[0], dict) else {}
        destination = md.get("destination") or {}
        return {
            "headline": md.get("headline") or None, "text": md.get("primary_text") or None,
            "call_to_action": md.get("call_to_action"), "destination_url": destination.get("url") if isinstance(destination, dict) else None,
            "thumbnail_url": first.get("thumbnail_url"), "effective_status": md.get("effective_status"),
            "review_feedback": _feedback(md.get("review_feedback")), "last_error": md.get("last_error"),
        }
    if platform == "wizard":
        return {"headline": md.get("headline"), "text": md.get("body") or md.get("primary_text"), "call_to_action": md.get("call_to_action"),
                "destination_url": md.get("destination_url"), "thumbnail_url": None, "effective_status": None,
                "review_feedback": None, "last_error": None}
    cr = dict(md.get("creative") or {})
    return {
        "headline": cr.get("headline") or cr.get("card_headline") or cr.get("long_headline"),
        "text": cr.get("primary_text") or cr.get("text") or cr.get("intro_text") or cr.get("description"),
        "call_to_action": cr.get("cta") or cr.get("call_to_action"), "destination_url": cr.get("destination_url"),
        "thumbnail_url": cr.get("thumbnail_url"), "effective_status": None, "review_feedback": None, "last_error": cr.get("last_error"),
    }


def _feedback(value: Any) -> str | None:
    # Meta review feedback is a dict of {placement: reason}; shown as one line.
    if not value:
        return None
    if isinstance(value, dict):
        return "; ".join(f"{k}: {v}" if not isinstance(v, dict) else "; ".join(map(str, v.values())) for k, v in value.items())[:500]
    return str(value)[:500]


def list_ads(db: Session, tenant_id: str, *, platform: str | None = None, status: str | None = None,
             campaign_id: str | None = None, ad_set_id: str | None = None, q: str | None = None,
             range_key: str = "30d", page: int = 1, page_size: int = 50) -> dict[str, Any]:
    query = (
        db.query(Ad)
        .join(AdGroup, and_(AdGroup.id == Ad.ad_group_id, AdGroup.tenant_id == tenant_id))
        .join(Campaign, Campaign.id == AdGroup.campaign_id)
        .filter(Ad.tenant_id == tenant_id)
    )
    query = _base_filters(query, tenant_id, platform, status, campaign_id, q, Ad)
    if ad_set_id:
        query = query.filter(AdGroup.id == ad_set_id)
    count = query.order_by(None).count()
    ads = (
        query.order_by(Campaign.created_at.desc(), Campaign.id, AdGroup.created_at, AdGroup.id, Ad.created_at, Ad.id)
        .offset((page - 1) * page_size).limit(page_size).all()
    )
    results = _meta_ad_results(db, tenant_id, [str(a.id) for a in ads if _platform(a.ad_group.campaign) == "meta"], RANGE_DAYS[range_key])
    items = []
    for ad in ads:
        g = ad.ad_group
        c = g.campaign
        p = _platform(c)
        fields = _ad_fields(ad, p)
        text_value = fields.pop("text")
        items.append({
            "id": str(ad.id), "name": ad.name, "ad_set_id": str(g.id), "ad_set_name": g.name, "campaign_id": str(c.id),
            "campaign_name": c.name, "platform": p, "status": ad.status, "external_id": ad.external_ad_id, "currency": c.currency.strip(),
            "text": " ".join(str(text_value).split())[:TEXT_EXCERPT] if text_value else None,
            **fields,
            **_results([results[str(ad.id)]] if str(ad.id) in results else [], _level(p)),
        })
    logger.info("paid_ads_listed", tenant_id=tenant_id, count=count)
    return {"count": count, "items": items}


# ---------------------------------------------------------------------------
# Pause / resume, dispatched to the builder that made the row
# ---------------------------------------------------------------------------
def set_ad_set_status(db: Session, tenant_id: str, actor: str, ad_set_id: str, resume: bool) -> dict[str, Any]:
    g = db.query(AdGroup).filter(AdGroup.tenant_id == tenant_id, AdGroup.id == ad_set_id).first()
    if g is None or g.campaign.tenant_id != g.tenant_id:
        raise NotFoundError("Ad set not found.")
    p = _platform(g.campaign)
    if p == "wizard":
        raise ConflictError("This ad set was made with the old wizard; pause its campaign instead.")
    if p == "meta":
        result = meta_builder_service.set_status(db, tenant_id, actor, "ad_set", ad_set_id, resume)
    else:
        result = ads_builder_service.set_status(db, tenant_id, actor, "group", ad_set_id, resume)
    return {**result, "level": "ad_set"}


def set_ad_status(db: Session, tenant_id: str, actor: str, ad_id: str, resume: bool) -> dict[str, Any]:
    ad = db.query(Ad).filter(Ad.tenant_id == tenant_id, Ad.id == ad_id).first()
    if ad is None or ad.ad_group.tenant_id != ad.tenant_id:
        raise NotFoundError("Ad not found.")
    p = _platform(ad.ad_group.campaign)
    if p == "wizard":
        raise ConflictError("This ad was made with the old wizard; pause its campaign instead.")
    if p == "meta":
        result = meta_builder_service.set_status(db, tenant_id, actor, "ad", ad_id, resume)
    else:
        result = ads_builder_service.set_status(db, tenant_id, actor, "ad", ad_id, resume)
    return {**result, "level": "ad"}
