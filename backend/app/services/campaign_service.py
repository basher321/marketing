"""Campaign metrics (SPEC-BE-009), lists (SPEC-BE-038) and wizard drafts (SPEC-BE-044)."""
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from sqlalchemy import column, func, select, table
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.ai.prompts.planner import _spend_decision
from app.ai.retrieval import get_tenant_limits
from app.core.audit import write_audit_log
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.integrations import meta_ads
from app.integrations.base_adapter import AD_RESULT_SOURCES
from app.integrations import verify as verifier
from app.models.campaign import AdGroup, Ad, Campaign
from app.models.content import ContentAsset
from app.models.tenant import Tenant
from app.schemas.campaign import CampaignDraftCreate, CampaignDraftUpdate
from app.services import integration_service
from app.services.audience_service import get_audience
from app.utils.locale_data import format_money

logger = structlog.get_logger(__name__)

# campaign_status values that count as "active": only 'running'. The live enum is draft,
# scheduled, running, paused, completed, failed - it has no 'active' value, and scheduled/paused
# campaigns are not currently serving.
ACTIVE_CAMPAIGN_STATUSES = ("running",)


def get_campaign_metrics(db: Session, tenant_id: str) -> dict[str, int | float | None]:
    """Active campaign count and avg ROAS for one tenant - the single computation behind both the
    Marketing page cards and the Dashboard Marketing engine card."""
    active_count = (
        db.query(func.count(Campaign.id))
        .filter(
            Campaign.tenant_id == tenant_id,
            Campaign.status.in_(ACTIVE_CAMPAIGN_STATUSES),
        )
        .scalar()
    )
    # Avg ROAS (SPEC-BE-056): purchase value / spend over the last 30 days of
    # imported Meta results; None when nothing was imported or no purchase
    # value was reported - never an estimated figure.
    avg_roas = roas_30d(db, tenant_id)
    logger.info(
        "campaign_metrics_computed",
        tenant_id=tenant_id,
        active_campaigns=int(active_count or 0),
        avg_roas=avg_roas,
    )
    return {"active_campaigns": int(active_count or 0), "avg_roas": avg_roas}


# Marketing "Active Campaigns" table (SPEC-BE-038): campaigns that are live or about to be -
# running, scheduled, or paused. draft / completed / failed are not "active".
LISTED_CAMPAIGN_STATUSES = ("running", "scheduled", "paused")


def list_campaigns(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    campaigns = (
        db.query(Campaign)
        .filter(Campaign.tenant_id == tenant_id, Campaign.status.in_(LISTED_CAMPAIGN_STATUSES))
        .order_by(Campaign.starts_at.desc().nulls_last(), Campaign.name)
        .all()
    )
    logger.info("campaigns_listed", tenant_id=tenant_id, count=len(campaigns))
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "objective": c.objective,
            "channels": list(c.channels or []),
            "budget": float(Decimal(c.budget_cents) / 100),
            "currency": c.currency,
            "duration_days": (
                (c.ends_at - c.starts_at).days if c.starts_at and c.ends_at else None
            ),
            # Per-campaign ROAS (SPEC-BE-056): lifetime imported Meta purchase value /
            # spend; null without imported data - never estimated.
            "roas": _campaign_kpis(db, tenant_id, str(c.id), 3650)["roas"],
            "status": c.status,
            "spent": float(Decimal(c.spent_cents or 0) / 100),
            # SPEC-BE-055: opens in the Ads Manager-style builder; Meta's own status.
            "builder": "builder" in (c.extra_metadata or {}),
            "effective_status": ((c.extra_metadata or {}).get("meta") or {}).get("effective_status"),
        }
        for c in campaigns
    ]


# Ad spend (SPEC-BE-019). campaigns.spent_cents is a lifetime running total with no time
# dimension, so it cannot answer "spend in the trailing 24 hours". The only time-stamped spend
# source in the live schema is analytics_events: rows with metric 'spend_cents' (value = integer
# cents spent) on entity_type 'campaign' or 'ad', at event_time. Nothing writes these yet (ad
# platform ingestion is a later spec), so a tenant without them gets 0 - never an estimate.
# Read through a lightweight table() because the AnalyticsEvent model doesn't match the live
# table (CLAUDE.md).
_analytics_events = table(
    "analytics_events",
    column("tenant_id"),
    column("event_time"),
    column("entity_type"),
    column("metric"),
    column("value"),
)
SPEND_METRIC = "spend_cents"
SPEND_ENTITY_TYPES = ("campaign", "ad")


def get_ad_spend_24h(
    db: Session, tenant_id: str, now: datetime | None = None
) -> dict[str, float | str | None]:
    now = now or datetime.now(timezone.utc)
    cents = db.execute(
        select(func.coalesce(func.sum(_analytics_events.c.value), 0)).where(
            _analytics_events.c.tenant_id == tenant_id,
            _analytics_events.c.metric == SPEND_METRIC,
            _analytics_events.c.entity_type.in_(SPEND_ENTITY_TYPES),
            _analytics_events.c.event_time >= now - timedelta(hours=24),
            _analytics_events.c.event_time <= now,
        )
    ).scalar()
    currency = db.execute(select(Tenant.currency).where(Tenant.id == tenant_id)).scalar() or "USD"
    # ROAS comes from SPEC-BE-009's function itself, never recomputed here.
    avg_roas = get_campaign_metrics(db, tenant_id)["avg_roas"]
    spend = float(Decimal(cents or 0) / 100)
    logger.info("ad_spend_computed", tenant_id=tenant_id, ad_spend_24h=spend)
    return {"ad_spend_24h": spend, "currency": currency, "avg_roas": float(avg_roas) if avg_roas is not None else None}


# ---------------------------------------------------------------------------
# Campaign Wizard drafts (SPEC-BE-044)
# ---------------------------------------------------------------------------
# The wizard's audience / creative choice and a pending launch approval live in
# campaigns.metadata["wizard"]: the live table has no columns for them, and the
# real ad_groups / ads rows are only created at launch (SPEC-BE-047).
MAX_DURATION_DAYS = 365
# A start this far in the past still counts as "now" (clock skew, slow forms).
START_TOLERANCE = timedelta(minutes=1)


def _wizard(campaign: Campaign) -> dict[str, Any]:
    return dict((campaign.extra_metadata or {}).get("wizard") or {})


def _set_wizard(campaign: Campaign, **changes: Any) -> None:
    # Reassign a new dict so SQLAlchemy sees the jsonb change.
    meta = dict(campaign.extra_metadata or {})
    wizard = dict(meta.get("wizard") or {})
    for key, value in changes.items():
        if value is None:
            wizard.pop(key, None)
        else:
            wizard[key] = value
    meta["wizard"] = wizard
    campaign.extra_metadata = meta


def _tenant_zone(db: Session, tenant_id: str) -> ZoneInfo:
    tz = db.query(Tenant.timezone).filter(Tenant.id == tenant_id).scalar() or "UTC"
    try:
        return ZoneInfo(tz)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _duration_days(starts_at: datetime, ends_at: datetime, zone: ZoneInfo) -> int:
    # Calendar days in the tenant's timezone, counting both the start and the
    # end day: Oct 1 10:00 -> Oct 7 23:59 is 7 days; same-day start/end is 1.
    return (ends_at.astimezone(zone).date() - starts_at.astimezone(zone).date()).days + 1


def _daily_cap_cents(budget_cents: int, days: int) -> int:
    return int((Decimal(budget_cents) / days).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _budget_complete(c: Campaign) -> bool:
    return c.budget_cents > 0 and c.starts_at is not None and c.ends_at is not None


def missing_steps(c: Campaign) -> list[str]:
    wizard = _wizard(c)
    missing = []
    if not wizard.get("audience_id"):
        missing.append("audience")
    if not wizard.get("creative_asset_id"):
        missing.append("creative")
    if not _budget_complete(c):
        missing.append("budget")
    if not c.channels:
        missing.append("channels")
    return missing


def approval_decision(db: Session, c: Campaign) -> tuple[bool, str]:
    # SPEC-BE-032's launch_ad rule, reused as-is (never a new threshold):
    # approval when the daily spend exceeds tenants.ad_daily_cap_cents or the
    # currency is not the tenant currency.
    limits = get_tenant_limits(db, c.tenant_id)
    return _spend_decision(c.daily_cap_cents, c.currency.strip(), limits)


def _utc(value: datetime | None) -> datetime | None:
    return value.astimezone(timezone.utc) if value else None


def campaign_detail(db: Session, c: Campaign) -> dict[str, Any]:
    wizard = _wizard(c)
    days = (
        _duration_days(c.starts_at, c.ends_at, _tenant_zone(db, c.tenant_id))
        if c.starts_at and c.ends_at
        else None
    )
    approval = None
    if _budget_complete(c):
        required, reason = approval_decision(db, c)
        approval = {"required": required, "reason": reason}
    return {
        "id": c.id,
        "name": c.name,
        "objective": c.objective,
        "description": c.description,
        "status": c.status,
        "channels": list(c.channels or []),
        "currency": c.currency.strip(),
        "total_budget": float(Decimal(c.budget_cents) / 100),
        "daily_budget": float(Decimal(c.daily_cap_cents) / 100),
        "duration_days": days,
        "starts_at": _utc(c.starts_at),
        "ends_at": _utc(c.ends_at),
        "audience_id": wizard.get("audience_id"),
        "creative_asset_id": wizard.get("creative_asset_id"),
        "approval": approval,
        "pending_approval_id": wizard.get("pending_approval_id"),
        "missing": missing_steps(c),
        "created_at": _utc(c.created_at),
        "updated_at": _utc(c.updated_at),
        "launched_at": _utc(c.launched_at),
        "destination_url": wizard.get("destination_url"),
        "call_to_action": wizard.get("call_to_action"),
        "meta": _meta_info(c),
        "published_channels": (
            _meta_channels(c) if (c.extra_metadata or {}).get("meta", {}).get("campaign_id") else []
        ),
        "builder": "builder" in (c.extra_metadata or {}),
    }


def _meta_info(c: Campaign) -> dict[str, Any] | None:
    meta = dict((c.extra_metadata or {}).get("meta") or {})
    if not meta:
        return None
    published = bool(meta.get("campaign_id"))
    return {
        "published": published,
        "campaign_id": meta.get("campaign_id"),
        "adset_id": meta.get("adset_id"),
        "ad_id": meta.get("ad_id"),
        "ads_manager_url": (
            meta_ads.ads_manager_url(meta["ad_account_id"], meta["campaign_id"]) if published else None
        ),
        "last_error": meta.get("last_error"),
    }


def get_campaign_row(db: Session, tenant_id: str, campaign_id: str, lock: bool = False) -> Campaign:
    query = db.query(Campaign).filter(Campaign.tenant_id == tenant_id, Campaign.id == campaign_id)
    if lock:
        query = query.with_for_update()
    campaign = query.first()
    if campaign is None:
        # Same 404 for a missing campaign and another tenant's campaign.
        raise NotFoundError("Campaign not found.")
    return campaign


def get_campaign(db: Session, tenant_id: str, campaign_id: str) -> dict[str, Any]:
    return campaign_detail(db, get_campaign_row(db, tenant_id, campaign_id))


def list_drafts(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    drafts = (
        db.query(Campaign)
        .filter(Campaign.tenant_id == tenant_id, Campaign.status == "draft")
        .order_by(Campaign.updated_at.desc(), Campaign.id)
        .all()
    )
    return [campaign_detail(db, c) for c in drafts]


def create_draft(
    db: Session, tenant_id: str, actor_user_id: str, payload: CampaignDraftCreate
) -> dict[str, Any]:
    currency = db.query(Tenant.currency).filter(Tenant.id == tenant_id).scalar() or "USD"
    campaign = Campaign(
        tenant_id=tenant_id,
        name=payload.name,
        objective=payload.objective,
        description=payload.description,
        status="draft",
        channels=[],
        budget_cents=0,
        daily_cap_cents=0,
        spent_cents=0,
        currency=currency.strip(),
        extra_metadata={"wizard": {}},
        created_by=actor_user_id,
    )
    db.add(campaign)
    db.flush()
    # write_audit_log commits: the draft and its audit row land together.
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="campaign.create",
        resource_type="campaign",
        resource_id=campaign.id,
        metadata={"name": campaign.name, "objective": campaign.objective},
    )
    db.refresh(campaign)
    logger.info("campaign_draft_created", tenant_id=tenant_id, campaign_id=str(campaign.id))
    return campaign_detail(db, campaign)


def update_draft(
    db: Session,
    tenant_id: str,
    actor_user_id: str,
    campaign_id: str,
    payload: CampaignDraftUpdate,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    campaign = get_campaign_row(db, tenant_id, campaign_id, lock=True)
    if campaign.status != "draft":
        raise ConflictError(f"Only draft campaigns can be edited (this one is {campaign.status}).")
    sent = payload.model_fields_set

    if "name" in sent and payload.name is not None:
        campaign.name = payload.name
    if "objective" in sent and payload.objective is not None:
        campaign.objective = payload.objective
    if "description" in sent:
        campaign.description = payload.description or None
    if "channels" in sent and payload.channels is not None:
        campaign.channels = list(payload.channels)

    if "audience_id" in sent:
        audience_id = str(payload.audience_id) if payload.audience_id else None
        if audience_id and get_audience(db, tenant_id, audience_id) is None:
            raise AppError("Unknown audience.", status_code=422)
        _set_wizard(campaign, audience_id=audience_id)

    if "creative_asset_id" in sent:
        asset_id = str(payload.creative_asset_id) if payload.creative_asset_id else None
        if asset_id:
            asset = (
                db.query(ContentAsset)
                .filter(ContentAsset.tenant_id == tenant_id, ContentAsset.id == asset_id)
                .first()
            )
            if asset is None:
                raise AppError("Unknown creative.", status_code=422)
            if asset.selected_variant_index is None:
                raise AppError("Select a creative variant first.", status_code=422)
            # Link the creative to this campaign (content_assets.campaign_id has no FK).
            asset.campaign_id = campaign.id
        _set_wizard(campaign, creative_asset_id=asset_id)

    # The ad's link and button (SPEC-BE-054). The schema checked https; the
    # host must also be public (the SPEC-BE-052 server-side request forgery rule).
    if "destination_url" in sent:
        url = payload.destination_url
        if url:
            try:
                verifier._require_public_host(urlparse(url).hostname or "")
            except verifier.VerifyError as exc:
                raise AppError(f"Destination link: {exc}", 422) from None
        _set_wizard(campaign, destination_url=url)
    if "call_to_action" in sent:
        _set_wizard(campaign, call_to_action=payload.call_to_action)

    # Budget & schedule: lifetime budget + start/end; the daily cap is derived.
    if "total_budget" in sent and payload.total_budget is not None:
        campaign.budget_cents = int(payload.total_budget * 100)
    if "starts_at" in sent and payload.starts_at is not None:
        if payload.starts_at < now - START_TOLERANCE:
            raise AppError("The start can't be in the past.", status_code=422)
        campaign.starts_at = payload.starts_at
    if "ends_at" in sent and payload.ends_at is not None:
        campaign.ends_at = payload.ends_at
    if campaign.starts_at and campaign.ends_at:
        if campaign.ends_at <= campaign.starts_at:
            raise AppError("The end must be after the start.", status_code=422)
        days = _duration_days(campaign.starts_at, campaign.ends_at, _tenant_zone(db, tenant_id))
        if days > MAX_DURATION_DAYS:
            raise AppError(f"A campaign can run at most {MAX_DURATION_DAYS} days.", status_code=422)
        campaign.daily_cap_cents = (
            _daily_cap_cents(campaign.budget_cents, days) if campaign.budget_cents else 0
        )
    else:
        campaign.daily_cap_cents = 0

    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="campaign.update",
        resource_type="campaign",
        resource_id=campaign.id,
        metadata={"fields": sorted(sent)},
    )
    db.refresh(campaign)
    logger.info("campaign_draft_updated", tenant_id=tenant_id, campaign_id=str(campaign.id))
    return campaign_detail(db, campaign)


# ---------------------------------------------------------------------------
# Launch / approval / pause / resume (SPEC-BE-047)
# ---------------------------------------------------------------------------
# Launching records the campaign as live in this system only: the ad-platform
# adapters are stubs, so nothing is published to Facebook/Instagram/TikTok and
# ads.external_ad_id stays NULL until an integration spec exists.
#
# approval_queue is written through a Core table: the ApprovalQueue model does
# not map the NOT NULL requested_by_type column (nor summary/payload/requested_by).
_approval_queue = table(
    "approval_queue",
    column("id"),
    column("tenant_id"),
    column("subject_type"),
    column("subject_id"),
    column("title"),
    column("summary"),
    column("payload", JSONB),
    column("requested_by_type"),
    column("requested_by"),
)


def _money(cents: int, currency: str) -> str:
    # SPEC-BE-072: the currency's own symbol and decimals ("৳1,850.00", "¥1,500").
    return format_money(cents, currency)


# ---------------------------------------------------------------------------
# Publishing to Meta (SPEC-BE-054)
# ---------------------------------------------------------------------------
# Only facebook / instagram / messenger publish (meta_ads.META_PLATFORMS); other
# channels stay internal. Meta objects are created BEFORE any DB row: campaign
# (PAUSED) -> ad set -> creative -> ad, then the campaign is switched ACTIVE.
# The ad set and ad are created ACTIVE under the PAUSED campaign, so nothing
# delivers until that last switch (one activate call). Any Meta failure deletes
# what was created (campaign first, which cascades; then the creative) and the
# caller rolls the DB back: never half-launched.
class MetaPublishError(AppError):
    """A launch that can't be published to Meta. `audit` = a Meta call failed
    (write campaign.publish_failed); `expired` = Meta rejected the token (190)."""

    def __init__(self, detail: str, status_code: int, audit: bool = False, expired: bool = False):
        super().__init__(detail, status_code)
        self.audit = audit
        self.expired = expired


def _meta_channels(c: Campaign) -> list[str]:
    return [ch for ch in c.channels or [] if ch in meta_ads.META_PLATFORMS]


def _set_meta(campaign: Campaign, values: dict[str, Any]) -> None:
    meta = dict(campaign.extra_metadata or {})
    meta["meta"] = values
    campaign.extra_metadata = meta


def _meta_preflight(db: Session, campaign: Campaign) -> dict[str, str] | None:
    """Checks that need no Meta call; run before a launch is queued or published.
    Returns the connection, or None when the campaign has no Meta channel."""
    channels = _meta_channels(campaign)
    if not channels:
        return None
    conn = integration_service.meta_publish_credentials(db, campaign.tenant_id)
    if conn is None or not conn["access_token"]:
        raise MetaPublishError("Connect Meta in Integrations to run on Facebook/Instagram.", 409)
    if conn["status"] != "connected":
        raise MetaPublishError("Reconnect Meta in Integrations; the connection has expired or failed.", 409)
    if not conn["ad_account_id"] or not conn["page_id"]:
        raise MetaPublishError("Choose a Meta ad account and Facebook Page in Integrations.", 409)
    if campaign.objective not in meta_ads.OBJECTIVES:
        raise MetaPublishError("Messages campaigns aren't supported on Meta yet.", 422)
    if campaign.objective == "conversions" and not conn["pixel_id"]:
        raise MetaPublishError("Select a Meta Pixel to run a Conversions campaign.", 422)
    if "instagram" in channels and not conn["instagram_id"]:
        raise MetaPublishError("Connect an Instagram account to run on Instagram.", 422)
    if set(channels) == {"messenger"}:
        # Meta has no Messenger-only placement.
        raise MetaPublishError("Messenger needs Facebook too: add the Facebook channel.", 422)
    if not _wizard(campaign).get("destination_url"):
        raise MetaPublishError("Add the link your ad sends people to (destination URL).", 422)
    return conn


def _resolve_targeting(
    client: meta_ads.MetaClient, targeting: dict[str, Any], platforms: list[str]
) -> dict[str, Any]:
    """Audience -> Meta targeting. Regions/cities, interests and languages need
    Meta ids: each is matched by exact name (languages: by name prefix, e.g.
    "English" -> English (US), English (UK)) through Meta's targeting search.
    Any unmatched term blocks the launch (422) - never silently dropped."""
    spec = meta_ads.base_targeting(targeting, platforms)
    unresolved: list[str] = []
    regions: list[dict[str, str]] = []
    cities: list[dict[str, str]] = []
    covered: set[str] = set()
    for name in targeting.get("regions") or []:
        hits = client.search("adgeolocation", name, location_types=["region", "city"])
        hit = next((h for h in hits if str(h.get("name", "")).lower() == name.lower()), None)
        if hit is None:
            unresolved.append(name)
            continue
        (regions if hit.get("type") == "region" else cities).append({"key": str(hit["key"])})
        covered.add(str(hit.get("country_code") or "").upper())
    # Meta rejects overlapping locations: a country is dropped when a region or
    # city inside it is targeted.
    geo: dict[str, Any] = {}
    countries = [c for c in spec["geo_locations"]["countries"] if c not in covered]
    if countries:
        geo["countries"] = countries
    if regions:
        geo["regions"] = regions
    if cities:
        geo["cities"] = cities
    spec["geo_locations"] = geo

    interests: list[dict[str, str]] = []
    for name in targeting.get("interests") or []:
        hits = client.search("adinterest", name)
        hit = next((h for h in hits if str(h.get("name", "")).lower() == name.lower()), None)
        if hit is None:
            unresolved.append(name)
        else:
            interests.append({"id": str(hit["id"]), "name": str(hit["name"])})
    if interests:
        spec["flexible_spec"] = [{"interests": interests}]

    locales: list[int] = []
    for code in targeting.get("languages") or []:
        label = meta_ads.language_label(code)
        hits = client.search("adlocale", label)
        keys = [int(h["key"]) for h in hits if str(h.get("name", "")).lower().startswith(label.lower())]
        if keys:
            locales.extend(keys)
        else:
            unresolved.append(code)
    if locales:
        spec["locales"] = sorted(set(locales))

    if unresolved:
        raise MetaPublishError(
            f"Meta doesn't recognise these audience terms: {', '.join(unresolved)}. Edit the audience.",
            422,
        )
    return spec


def _publish_to_meta(
    campaign: Campaign,
    conn: dict[str, str],
    targeting: dict[str, Any],
    variant: dict[str, Any],
    now: datetime,
) -> dict[str, str]:
    client = meta_ads.MetaClient(conn["access_token"])
    act = conn["ad_account_id"]
    wizard = _wizard(campaign)
    url = str(wizard["destination_url"])
    cta = str(wizard.get("call_to_action") or "LEARN_MORE")
    platforms = meta_ads.meta_platforms(_meta_channels(campaign))
    objective, goal = meta_ads.OBJECTIVES[campaign.objective]
    created: list[str] = []  # deleted in this order if a later step fails
    try:
        account = client.get_ad_account(act)
        currency = str(account.get("currency") or "").upper()
        if currency != campaign.currency.strip().upper():
            raise MetaPublishError(
                f"Your Meta ad account bills in {currency or 'another currency'}, but this campaign "
                f"is in {campaign.currency.strip()}. Use the same currency.",
                422,
            )
        account_status = int(account.get("account_status") or 0)
        if account_status != 1:
            status_text = meta_ads.ACCOUNT_STATUS.get(account_status, "not active")
            raise MetaPublishError(f"Your Meta ad account is {status_text}; fix it in Ads Manager.", 422)
        meta_targeting = _resolve_targeting(client, targeting, platforms)

        campaign_id = client.create(
            act,
            "campaigns",
            {
                "name": campaign.name,
                "objective": objective,
                "status": "PAUSED",
                # Required by Meta; housing/employment/credit/politics are out of scope.
                "special_ad_categories": [],
                "buying_type": "AUCTION",
                # One ad set with a lifetime budget: no budget sharing.
                "is_adset_budget_sharing_enabled": False,
            },
        )
        created.append(campaign_id)
        start = max(campaign.starts_at or now, now)
        adset: dict[str, Any] = {
            "name": f"{campaign.name} — Ad set"[:255],
            "campaign_id": campaign_id,
            "lifetime_budget": meta_ads.to_meta_amount(campaign.budget_cents, currency),
            "start_time": start.astimezone(timezone.utc).isoformat(),
            "end_time": campaign.ends_at.astimezone(timezone.utc).isoformat() if campaign.ends_at else None,
            "billing_event": "IMPRESSIONS",
            "optimization_goal": goal,
            "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            "targeting": meta_targeting,
            "status": "ACTIVE",
        }
        if campaign.objective == "conversions":
            adset["promoted_object"] = {"pixel_id": conn["pixel_id"], "custom_event_type": "PURCHASE"}
        adset_id = client.create(act, "adsets", adset)

        headline = str(variant.get("headline") or campaign.name)
        creative: dict[str, Any] = {
            "name": f"{campaign.name} — Creative"[:255],
            "object_story_spec": {
                "page_id": conn["page_id"],
                "link_data": {
                    "link": url,
                    "name": headline,
                    "message": str(variant.get("description") or headline),
                    "call_to_action": {"type": cta, "value": {"link": url}},
                },
            },
        }
        if "instagram" in platforms:
            creative["instagram_user_id"] = conn["instagram_id"]
        creative_id = client.create(act, "adcreatives", creative)
        created.append(creative_id)
        ad_id = client.create(
            act,
            "ads",
            {
                "name": f"{campaign.name} — Ad"[:255],
                "adset_id": adset_id,
                "creative": {"creative_id": creative_id},
                "status": "ACTIVE",
            },
        )
        client.set_status(campaign_id, "ACTIVE")
    except meta_ads.MetaError as exc:
        for object_id in created:
            try:
                client.delete(object_id)
            except meta_ads.MetaError:
                logger.warning("meta_cleanup_failed", campaign_id=str(campaign.id), object_id=object_id)
        status_code = 409 if exc.expired else 502
        detail = "Reconnect Meta in Integrations; Meta rejected the saved access." if exc.expired else f"Meta: {exc.message}"
        raise MetaPublishError(detail, status_code, audit=True, expired=exc.expired) from None
    return {
        "campaign_id": campaign_id,
        "adset_id": adset_id,
        "creative_id": creative_id,
        "ad_id": ad_id,
        "ad_account_id": act,
        "published_at": now.isoformat(),
    }


def _record_publish_failure(
    db: Session, tenant_id: str, actor_user_id: str, campaign_id: str, exc: MetaPublishError
) -> None:
    """Owner launch failed on Meta: drop the launch's DB changes, then record
    the failure in its own commit (write_audit_log commits)."""
    db.rollback()
    if exc.expired:
        integration_service.mark_meta_expired(db, tenant_id, exc.detail)
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="campaign.publish_failed",
        resource_type="campaign",
        resource_id=campaign_id,
        metadata={"error": exc.detail[:300], "expired": exc.expired},
    )


def _go_live(
    db: Session, campaign: Campaign, approver_id: str | None, now: datetime
) -> None:
    """Publish to Meta when the campaign has a Meta channel (SPEC-BE-054), then
    create the ad set + ad and set the campaign live. No commit here: the
    caller's audit write commits everything together."""
    wizard = _wizard(campaign)
    audience = get_audience(db, campaign.tenant_id, wizard["audience_id"])
    asset = (
        db.query(ContentAsset)
        .filter(
            ContentAsset.tenant_id == campaign.tenant_id,
            ContentAsset.id == wizard["creative_asset_id"],
        )
        .first()
    )
    if audience is None or asset is None or asset.selected_variant_index is None:
        raise AppError("The audience or creative no longer exists; edit the draft.", 422)
    variants = asset.variants or []
    index = asset.selected_variant_index
    variant = variants[index] if index < len(variants) else {}

    status = "scheduled" if campaign.starts_at and campaign.starts_at > now else "running"
    # Meta first, before any DB row (SPEC-BE-054); raises MetaPublishError.
    conn = _meta_preflight(db, campaign)
    meta_ids = (
        _publish_to_meta(campaign, conn, dict(audience.targeting or {}), variant, now) if conn else None
    )
    ad_group = AdGroup(
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        name=f"{campaign.name} — Ad set"[:255],
        audience_id=audience.id,
        targeting=dict(audience.targeting or {}),
        budget_cents=campaign.budget_cents,
        status=status,
        external_id=meta_ids["adset_id"] if meta_ids else None,
    )
    db.add(ad_group)
    db.flush()
    if meta_ids:
        _set_meta(campaign, meta_ids)
    db.add(
        Ad(
            tenant_id=campaign.tenant_id,
            ad_group_id=ad_group.id,
            content_asset_id=asset.id,
            name=f"{campaign.name} — Ad"[:255],
            status=status,
            external_ad_id=meta_ids["ad_id"] if meta_ids else None,
            external_url=(
                meta_ads.ads_manager_url(meta_ids["ad_account_id"], meta_ids["campaign_id"])
                if meta_ids
                else None
            ),
            extra_metadata={
                "variant_index": asset.selected_variant_index,
                "headline": variant.get("headline", ""),
                "description": variant.get("description", ""),
                "channels": list(campaign.channels or []),
            },
        )
    )
    campaign.status = status
    campaign.launched_at = now
    _set_wizard(campaign, pending_approval_id=None)
    asset.status = "approved"
    if approver_id:
        campaign.owner_approved_at = now
        campaign.owner_approved_by = approver_id
        asset.owner_approved_at = now
        asset.owner_approved_by = approver_id


def launch(
    db: Session,
    tenant_id: str,
    actor_user_id: str,
    actor_is_owner: bool,
    campaign_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    campaign = get_campaign_row(db, tenant_id, campaign_id, lock=True)
    if campaign.status != "draft":
        raise ConflictError(
            f"Only draft campaigns can be launched (this one is {campaign.status})."
        )
    if _wizard(campaign).get("pending_approval_id"):
        raise ConflictError("This campaign is already waiting for owner approval.")
    missing = missing_steps(campaign)
    if missing:
        raise AppError(f"Complete these steps first: {', '.join(missing)}.", 422)
    if campaign.ends_at and campaign.ends_at <= now:
        raise AppError("The schedule has already ended; pick new dates.", 422)
    # Meta checks that need no network (SPEC-BE-054), before queueing or publishing.
    _meta_preflight(db, campaign)

    required, reason = approval_decision(db, campaign)
    if required and not actor_is_owner:
        # Over the tenant's daily cap (or foreign currency): queue for the owner.
        currency = campaign.currency.strip()
        approval_id = db.execute(
            _approval_queue.insert()
            .values(
                tenant_id=tenant_id,
                subject_type="campaign",
                subject_id=campaign.id,
                title=campaign.name[:255],
                summary=(
                    f"Launch {campaign.name}: budget {_money(campaign.budget_cents, currency)}, "
                    f"daily {_money(campaign.daily_cap_cents, currency)} on "
                    f"{', '.join(campaign.channels or [])}. Needs approval: {reason}."
                ),
                payload={
                    "campaign_id": str(campaign.id),
                    "budget_cents": campaign.budget_cents,
                    "daily_cap_cents": campaign.daily_cap_cents,
                    "currency": currency,
                    "channels": list(campaign.channels or []),
                    "reason": reason,
                },
                requested_by_type="human",
                requested_by=actor_user_id,
            )
            .returning(_approval_queue.c.id)
        ).scalar_one()
        _set_wizard(campaign, pending_approval_id=str(approval_id))
        write_audit_log(
            db,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="campaign.submit_for_approval",
            resource_type="campaign",
            resource_id=campaign.id,
            metadata={"approval_id": str(approval_id), "reason": reason},
        )
        logger.info(
            "campaign_submitted_for_approval", tenant_id=tenant_id, campaign_id=campaign_id
        )
    else:
        # An owner's own launch counts as the owner's approval.
        try:
            _go_live(db, campaign, actor_user_id if actor_is_owner else None, now)
        except MetaPublishError as exc:
            if exc.audit:
                _record_publish_failure(db, tenant_id, actor_user_id, campaign_id, exc)
            raise
        meta_ids = (campaign.extra_metadata or {}).get("meta") or {}
        write_audit_log(
            db,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="campaign.launch",
            resource_type="campaign",
            resource_id=campaign.id,
            metadata={
                "status": campaign.status,
                "approval_rule": reason,
                "by_owner": actor_is_owner,
                "meta_campaign_id": meta_ids.get("campaign_id"),
            },
        )
        if meta_ids.get("campaign_id"):
            write_audit_log(
                db,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                action="campaign.published",
                resource_type="campaign",
                resource_id=campaign.id,
                metadata={"platform": "meta", "meta_campaign_id": meta_ids["campaign_id"]},
            )
        logger.info("campaign_launched", tenant_id=tenant_id, campaign_id=campaign_id)
    db.refresh(campaign)
    return campaign_detail(db, campaign)


def apply_approval_decision(
    db: Session,
    tenant_id: str,
    approval_id: str,
    campaign_id: str,
    decider_id: str,
    decision: str,
    now: datetime,
) -> None:
    """Called by approval_service when a `campaign` approval is decided. Only
    acts when the campaign is still a draft waiting on this approval; no
    commit (the caller's audit write commits)."""
    campaign = (
        db.query(Campaign)
        .filter(Campaign.tenant_id == tenant_id, Campaign.id == campaign_id)
        .with_for_update()
        .first()
    )
    if campaign is None or campaign.status != "draft":
        return
    from app.services import ads_builder_service

    if ads_builder_service.is_platform_campaign(campaign):
        # A TikTok/Google/LinkedIn/X/Snapchat/Pinterest campaign (SPEC-BE-062).
        ads_builder_service.apply_approval_decision(db, tenant_id, approval_id, campaign, decider_id, decision)
        return
    if "builder" in (campaign.extra_metadata or {}):
        # A Meta builder campaign (SPEC-BE-055) publishes its whole tree.
        from app.services import meta_builder_service

        meta_builder_service.apply_approval_decision(db, tenant_id, approval_id, campaign, decider_id, decision, now)
        return
    if _wizard(campaign).get("pending_approval_id") != approval_id:
        return
    if decision == "approved":
        try:
            _go_live(db, campaign, decider_id, now)
        except MetaPublishError as exc:
            # SPEC-BE-054 decision 4: the approval stays approved; the campaign
            # stays a draft carrying the error, and the owner's next Launch
            # publishes it (an owner's launch counts as the approval). _go_live
            # wrote no DB row before failing; Meta objects were cleaned up.
            _set_wizard(campaign, pending_approval_id=None)
            _set_meta(campaign, {"last_error": exc.detail})
            if exc.expired:
                integration_service.mark_meta_expired(db, tenant_id, exc.detail)
            logger.warning("campaign_publish_failed_after_approval", campaign_id=campaign_id)
            return
        meta_ids = (campaign.extra_metadata or {}).get("meta") or {}
        if meta_ids.get("campaign_id"):
            logger.info("campaign_published", campaign_id=campaign_id, platform="meta")
    else:
        # Rejected: back to an editable draft.
        _set_wizard(campaign, pending_approval_id=None)


def _set_children_status(db: Session, campaign: Campaign, status: str) -> None:
    for group in campaign.ad_groups:
        group.status = status
        for ad in group.ads:
            ad.status = status


def _sync_meta_status(db: Session, campaign: Campaign, status: str) -> None:
    """A published campaign is paused/resumed on Meta first (SPEC-BE-054); if
    Meta fails, our status is not changed."""
    meta_campaign_id = ((campaign.extra_metadata or {}).get("meta") or {}).get("campaign_id")
    if not meta_campaign_id:
        return
    conn = integration_service.meta_publish_credentials(db, campaign.tenant_id)
    if conn is None or not conn["access_token"]:
        raise ConflictError("Reconnect Meta in Integrations to change this campaign on Facebook/Instagram.")
    try:
        meta_ads.MetaClient(conn["access_token"]).set_status(meta_campaign_id, status)
    except meta_ads.MetaError as exc:
        if exc.expired:
            integration_service.mark_meta_expired(db, campaign.tenant_id, exc.message)
            db.commit()
            raise ConflictError("Reconnect Meta in Integrations; Meta rejected the saved access.") from None
        raise AppError(f"Meta: {exc.message}", 502) from None


def pause(db: Session, tenant_id: str, actor_user_id: str, campaign_id: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    campaign = get_campaign_row(db, tenant_id, campaign_id, lock=True)
    from app.services import ads_builder_service

    if ads_builder_service.is_platform_campaign(campaign):
        # SPEC-BE-062: pause on the ad platform first, through its own builder.
        ads_builder_service.set_status(db, tenant_id, actor_user_id, "campaign", campaign_id, resume=False)
        db.refresh(campaign)
        return campaign_detail(db, campaign)
    if campaign.status not in ("running", "scheduled"):
        raise ConflictError(
            f"Only running or scheduled campaigns can be paused (this one is {campaign.status})."
        )
    _sync_meta_status(db, campaign, "PAUSED")
    campaign.status = "paused"
    campaign.paused_at = now
    _set_children_status(db, campaign, "paused")
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="campaign.pause",
        resource_type="campaign",
        resource_id=campaign.id,
        metadata={},
    )
    db.refresh(campaign)
    return campaign_detail(db, campaign)


def resume(db: Session, tenant_id: str, actor_user_id: str, campaign_id: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    campaign = get_campaign_row(db, tenant_id, campaign_id, lock=True)
    from app.services import ads_builder_service

    if ads_builder_service.is_platform_campaign(campaign):
        # SPEC-BE-062: resume on the ad platform first, through its own builder.
        ads_builder_service.set_status(db, tenant_id, actor_user_id, "campaign", campaign_id, resume=True)
        db.refresh(campaign)
        return campaign_detail(db, campaign)
    if campaign.status != "paused":
        raise ConflictError(
            f"Only paused campaigns can be resumed (this one is {campaign.status})."
        )
    if campaign.ends_at and campaign.ends_at <= now:
        raise ConflictError("This campaign has ended; it can't be resumed.")
    status = "scheduled" if campaign.starts_at and campaign.starts_at > now else "running"
    _sync_meta_status(db, campaign, "ACTIVE")
    campaign.status = status
    _set_children_status(db, campaign, status)
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="campaign.resume",
        resource_type="campaign",
        resource_id=campaign.id,
        metadata={"status": status},
    )
    db.refresh(campaign)
    return campaign_detail(db, campaign)


# ---------------------------------------------------------------------------
# Meta results import + status sync (SPEC-BE-056)
# ---------------------------------------------------------------------------
# Rows go to the live analytics_events table (the SPEC-BE-019/050 reports read
# it): source 'meta', event_type 'meta_insights', entity 'ad' = our ads.id,
# event_time = that day 00:00 in the ad account's timezone, one row per metric
# (names in meta_ads.insight_metrics). Each import deletes the meta rows of the
# campaign's ads in the imported window and inserts the new ones in the same
# transaction, so re-running is idempotent and Meta's revisions of recent days
# replace the old values. Every run re-imports the last 3 days plus any days
# never imported (from the publish date, capped at 90 days).
MANUAL_SYNC_THROTTLE = timedelta(minutes=5)
REIMPORT_DAYS = 3
MAX_IMPORT_DAYS = 90
_events = table(
    "analytics_events",
    column("tenant_id"), column("event_time"), column("event_type"), column("entity_type"), column("entity_id"),
    column("metric"), column("value"), column("dimensions", JSONB), column("source"),
)


def _meta_record(db: Session, tenant_id: str) -> Any:
    from app.models.integration import Integration

    return (
        db.query(Integration)
        .filter(Integration.tenant_id == tenant_id, Integration.provider == "meta_ads", Integration.status != "disconnected")
        .order_by(Integration.updated_at.desc())
        .first()
    )


def _import_campaign(db: Session, c: Campaign, client: meta_ads.MetaClient, account_tz: str, today: Any) -> int:
    from sqlalchemy import delete, text

    meta = dict((c.extra_metadata or {}).get("meta") or {})
    zone = ZoneInfo(account_tz)
    published = datetime.fromisoformat(meta["published_at"]).astimezone(zone).date() if meta.get("published_at") else today
    last = datetime.fromisoformat(meta["insights_until"]).date() if meta.get("insights_until") else None
    since = min(today - timedelta(days=REIMPORT_DAYS - 1), (last + timedelta(days=1)) if last else published)
    since = max(since, published, today - timedelta(days=MAX_IMPORT_DAYS - 1))
    rows = meta_ads.insights(client, meta["campaign_id"], since.isoformat(), today.isoformat())
    ads = {
        a.external_ad_id: a
        for g in c.ad_groups if g.tenant_id == c.tenant_id
        for a in g.ads if a.external_ad_id and a.tenant_id == c.tenant_id
    }
    window_start = datetime.combine(since, datetime.min.time(), zone)
    window_end = datetime.combine(today + timedelta(days=1), datetime.min.time(), zone)
    if ads:
        db.execute(
            delete(_events).where(
                _events.c.tenant_id == c.tenant_id, _events.c.source == "meta", _events.c.entity_type == "ad",
                _events.c.entity_id.in_([a.id for a in ads.values()]),
                _events.c.event_time >= window_start, _events.c.event_time < window_end,
            )
        )
    written = 0
    for row in rows:
        ad = ads.get(str(row.get("ad_id")))
        if ad is None:
            continue
        day = datetime.fromisoformat(str(row["date_start"])).date()
        when = datetime.combine(day, datetime.min.time(), zone).astimezone(timezone.utc)
        dims = {"campaign_id": str(c.id), "ad_group_id": str(ad.ad_group_id), "meta_ad_id": ad.external_ad_id,
                "date": day.isoformat(), "currency": c.currency.strip()}
        for metric, value in meta_ads.insight_metrics(row).items():
            db.execute(_events.insert().values(
                tenant_id=c.tenant_id, event_time=when, event_type="meta_insights", entity_type="ad",
                entity_id=ad.id, metric=metric, value=value, dimensions=dims, source="meta",
            ))
            written += 1
    if ads:
        # Running total from everything imported for this campaign's ads.
        total = db.execute(
            text("SELECT COALESCE(SUM(value), 0) FROM analytics_events WHERE tenant_id = :t AND source = 'meta' "
                 "AND metric = 'spend_cents' AND entity_type = 'ad' AND entity_id::text = ANY(:ids)"),
            {"t": c.tenant_id, "ids": [str(a.id) for a in ads.values()]},
        ).scalar_one()
        c.spent_cents = int(total)
    _set_meta(c, {**dict((c.extra_metadata or {}).get("meta") or {}), "insights_until": today.isoformat()})
    return written


def _campaign_kpis(db: Session, tenant_id: str, campaign_id: str, days: int) -> dict[str, float | None]:
    from sqlalchemy import text

    rows = {
        m: v
        for m, v in db.execute(
            # Every ad platform's imported results (SPEC-BE-062), not only Meta's.
            text("SELECT metric, SUM(value) FROM analytics_events WHERE tenant_id = :t AND source = ANY(:sources) "
                 "AND dimensions->>'campaign_id' = :c AND event_time >= now() - make_interval(days => :d) GROUP BY metric"),
            {"t": tenant_id, "c": campaign_id, "d": days, "sources": list(AD_RESULT_SOURCES)},
        ).all()
    }
    spend = float(rows.get("spend_cents") or 0)
    impressions = float(rows.get("impressions") or 0)
    clicks = float(rows.get("link_clicks") or 0)
    value = rows.get("purchase_value_cents")
    return {
        "ctr": round(clicks / impressions * 100, 2) if impressions else None,
        "cpc": round(spend / 100 / clicks, 2) if clicks else None,
        "roas": round(float(value) / spend, 2) if value is not None and spend else None,
        "daily_spend": round(spend / 100 / days, 2),
    }


def sync_meta_results(
    db: Session, tenant_id: str, actor_user_id: str | None, campaign_id: str | None = None, manual: bool = True
) -> dict[str, Any]:
    """Imports insights + statuses for one or all published campaigns."""
    from app.services import meta_builder_service
    from app.workflow_engine.dispatcher import fire

    conn = integration_service.meta_publish_credentials(db, tenant_id)
    if conn is None or not conn["access_token"] or conn["status"] != "connected":
        raise ConflictError("Connect Meta in Integrations to import results.")
    record = _meta_record(db, tenant_id)
    now = datetime.now(timezone.utc)
    state = dict(((record.extra_metadata or {}) if record else {}).get("insights_sync") or {})
    if manual and state.get("last_manual_at"):
        waited = now - datetime.fromisoformat(state["last_manual_at"])
        if waited < MANUAL_SYNC_THROTTLE:
            seconds = int((MANUAL_SYNC_THROTTLE - waited).total_seconds())
            raise ConflictError(f"Results were synced moments ago; try again in {seconds // 60}m {seconds % 60}s.")
    query = db.query(Campaign).filter(Campaign.tenant_id == tenant_id)
    if campaign_id:
        query = query.filter(Campaign.id == campaign_id)
    campaigns = [
        c for c in query.all()
        if ((c.extra_metadata or {}).get("meta") or {}).get("campaign_id")
        and (c.status in ("running", "scheduled", "paused") or (c.ends_at and c.ends_at >= now - timedelta(days=30)))
    ]
    if campaign_id and not campaigns:
        raise NotFoundError("Campaign not found or not published on Meta.")
    client = meta_ads.MetaClient(conn["access_token"])
    errors: list[dict[str, Any]] = []
    rows = synced = 0
    try:
        account = client.get(f"act_{conn['ad_account_id']}", fields="timezone_name")
        account_tz = str(account.get("timezone_name") or "UTC")
        today = now.astimezone(ZoneInfo(account_tz)).date()
        for c in campaigns:
            try:
                with db.begin_nested():
                    rows += _import_campaign(db, c, client, account_tz, today)
                    meta_builder_service.refresh_statuses(db, c)
                synced += 1
            except meta_ads.MetaError as exc:
                kind, _status, message = meta_ads.classify(exc)
                errors.append({"campaign_id": str(c.id), "message": message, "at": now.isoformat()})
                if kind in ("auth", "rate_limit"):
                    if kind == "auth":
                        integration_service.mark_meta_expired(db, tenant_id, exc.message)
                    break
            except AppError as exc:
                errors.append({"campaign_id": str(c.id), "message": str(exc.detail), "at": now.isoformat()})
    except meta_ads.MetaError as exc:
        kind, _status, message = meta_ads.classify(exc)
        errors.append({"campaign_id": None, "message": message, "at": now.isoformat()})
        if kind == "auth":
            integration_service.mark_meta_expired(db, tenant_id, exc.message)
    if record is not None:
        state.update(
            last_window=f"last {REIMPORT_DAYS}d + missing days", campaigns=synced, rows=rows,
            errors=(errors + list(state.get("errors") or []))[:20],
        )
        if manual:
            state["last_manual_at"] = now.isoformat()
        if synced and not errors:
            state["last_success_at"] = now.isoformat()
            record.last_sync_at = now
            record.last_error = None
        elif errors:
            record.last_error = str(errors[0]["message"])[:300]
        record.extra_metadata = {**(record.extra_metadata or {}), "insights_sync": state}
    write_audit_log(
        db, tenant_id=tenant_id, actor_user_id=actor_user_id,
        action="meta.insights_failed" if errors and not synced else "meta.insights_synced",
        resource_type="integration", resource_id=str(record.id) if record else None,
        metadata={"campaigns": synced, "rows": rows, "errors": len(errors)},
    )
    # Live trigger ad_threshold_crossed (SPEC-BE-060) with each campaign's 7-day KPIs.
    for c in campaigns:
        fire(db, tenant_id, "ad_threshold_crossed",
             {"campaign": {"id": str(c.id), "name": c.name, **_campaign_kpis(db, tenant_id, str(c.id), 7)}})
    return {"synced_campaigns": synced, "rows_written": rows, "last_sync_at": now, "errors": errors}


def sync_all_meta_results() -> int:
    """Scheduler job (every 3 hours): every tenant with a connected Meta account."""
    from app.db.session import SessionLocal
    from app.models.integration import Integration

    done = 0
    db = SessionLocal()
    try:
        tenants = [
            t for (t,) in db.query(Integration.tenant_id)
            .filter(Integration.provider == "meta_ads", Integration.status == "connected")
            .distinct()
        ]
        for tenant_id in tenants:
            try:
                result = sync_meta_results(db, str(tenant_id), None, manual=False)
                done += 1 if result["synced_campaigns"] else 0
            except AppError as exc:
                db.rollback()
                logger.warning("meta_insights_scheduled_failed", tenant_id=str(tenant_id), error=exc.detail)
    finally:
        db.close()
    return done


# The objective's "result" metric (shown as Results / Conversions).
RESULT_FOR_OBJECTIVE = {"conversions": "purchases", "leads": "leads", "app_promotion": "app_installs",
                        "traffic": "link_clicks", "engagement": "post_engagement", "awareness": "reach", "reach": "reach"}


def _kpi(totals: dict[str, float], result_metric: str) -> dict[str, Any]:
    spend = totals.get("spend_cents")
    impressions = totals.get("impressions")
    clicks = totals.get("link_clicks")
    value = totals.get("purchase_value_cents")
    return {
        "spend": round(spend / 100, 2) if spend is not None else None,
        "impressions": int(impressions) if impressions is not None else None,
        "reach": int(totals["reach"]) if totals.get("reach") is not None else None,
        "clicks": int(clicks) if clicks is not None else None,
        "ctr": round(clicks / impressions * 100, 2) if clicks is not None and impressions else None,
        "results": int(totals[result_metric]) if totals.get(result_metric) is not None else None,
        "roas": round(value / spend, 2) if value is not None and spend else None,
    }


def get_campaign_results(db: Session, tenant_id: str, campaign_id: str, range_key: str) -> dict[str, Any]:
    from sqlalchemy import text

    c = get_campaign_row(db, tenant_id, campaign_id)
    days = {"7d": 7, "30d": 30, "90d": 90}.get(range_key)
    since = datetime.now(timezone.utc) - timedelta(days=days) if days else datetime(2000, 1, 1, tzinfo=timezone.utc)
    rows = db.execute(
        text("SELECT (dimensions->>'date')::date AS day, dimensions->>'ad_group_id' AS g, entity_id::text AS ad, metric, SUM(value) AS v "
             "FROM analytics_events WHERE tenant_id = :t AND source = 'meta' AND dimensions->>'campaign_id' = :c "
             "AND event_time >= :since GROUP BY 1, 2, 3, 4"),
        {"t": tenant_id, "c": str(c.id), "since": since},
    ).all()
    result_metric = RESULT_FOR_OBJECTIVE.get(c.objective, "link_clicks")

    def bucket(keyfn: Any) -> dict[Any, dict[str, float]]:
        out: dict[Any, dict[str, float]] = {}
        for r in rows:
            entry = out.setdefault(keyfn(r), {})
            entry[r.metric] = entry.get(r.metric, 0.0) + float(r.v)
        return out

    totals = bucket(lambda r: "all").get("all", {})
    daily = bucket(lambda r: r.day)
    by_group = bucket(lambda r: r.g)
    by_ad = bucket(lambda r: r.ad)
    groups = [g for g in c.ad_groups if g.tenant_id == c.tenant_id]
    meta = (c.extra_metadata or {}).get("meta") or {}
    record = _meta_record(db, tenant_id)
    kpis = _kpi(totals, result_metric)
    currency = c.currency.strip()
    if not rows:
        summary = "No results imported from Meta yet."
    else:
        ctr = f"{kpis['ctr']}%" if kpis["ctr"] is not None else "—"
        roas = str(kpis["roas"]) if kpis["roas"] is not None else "—"
        results = kpis["results"] if kpis["results"] is not None else "—"
        summary = (
            f"Spend {currency} {kpis['spend'] or 0:,.2f}, {kpis['impressions'] or 0:,} impressions, "
            f"CTR {ctr}, ROAS {roas}, {results} result(s)."
        )
    return {
        "campaign_id": str(c.id),
        "currency": currency,
        "range": range_key,
        "source": "meta",
        "result_metric": result_metric,
        "summary": summary,
        "totals": kpis,
        "daily": [{"date": d.isoformat(), **_kpi(v, result_metric)} for d, v in sorted(daily.items())],
        "ad_sets": [
            {"id": str(g.id), "name": g.name, "status": g.status,
             "effective_status": (g.extra_metadata or {}).get("effective_status"),
             **_kpi(by_group.get(str(g.id), {}), result_metric)}
            for g in groups
        ],
        "ads": [
            {"id": str(a.id), "name": a.name, "status": a.status, "ad_set_id": str(g.id),
             "effective_status": (a.extra_metadata or {}).get("effective_status"),
             **_kpi(by_ad.get(str(a.id), {}), result_metric)}
            for g in groups for a in g.ads if a.tenant_id == c.tenant_id
        ],
        "effective_status": meta.get("effective_status"),
        "last_sync_at": record.last_sync_at.astimezone(timezone.utc) if record and record.last_sync_at else None,
    }


def roas_30d(db: Session, tenant_id: str) -> float | None:
    from sqlalchemy import text

    value, spend = db.execute(
        text("SELECT SUM(value) FILTER (WHERE metric = 'purchase_value_cents'), SUM(value) FILTER (WHERE metric = 'spend_cents') "
             "FROM analytics_events WHERE tenant_id = :t AND source = ANY(:sources) AND event_time >= now() - interval '30 days'"),
        {"t": tenant_id, "sources": list(AD_RESULT_SOURCES)},
    ).one()
    return round(float(value) / float(spend), 2) if value is not None and spend else None
