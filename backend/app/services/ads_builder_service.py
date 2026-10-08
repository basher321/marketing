"""Multi-platform Ad Manager (SPEC-BE-062): platform registry + one builder
for TikTok, Google Ads, YouTube, LinkedIn, X, Snapchat and Pinterest. Meta keeps its
own builder (meta_builder_service); this module never touches a Meta campaign.

Storage, on the existing tables (no new columns):
- campaigns: metadata.platform = <key>, metadata.builder = {} (so lists link to
  the editor, as for Meta), metadata.platform_campaign = {objective, campaign
  type, budget mode/cents, fields, external id, last error, pending approval}.
  budget_cents / daily_cap_cents / starts_at / ends_at / channels are roll-ups
  so the lists, analytics and the SPEC-BE-047 cap rule keep working.
- ad_groups: targeting (platform-shaped), metadata.platform_fields = {budget
  mode/cents, dates, fields}, external_id.
- ads: metadata.creative, external_ad_id.

Publishing goes through the platform's adapter module (contract in
integrations/base_adapter.py). A platform whose spec isn't built yet answers
501 instead of pretending to publish.
"""
import importlib
from datetime import datetime, timedelta, timezone
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from types import ModuleType
from typing import Any
from urllib.parse import urlparse

import structlog
from sqlalchemy import column, insert, table
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.integrations.base_adapter import PlatformError
from app.models.campaign import Ad, AdGroup, Campaign
from app.models.tenant import Tenant
from app.schemas import ads_builder as s
from app.services import integration_service
from app.utils.locale_data import format_money

logger = structlog.get_logger(__name__)

MAX_GROUPS = 10
MAX_ADS = 10

_approval_queue = table(
    "approval_queue",
    column("id"), column("tenant_id"), column("subject_type"), column("subject_id"), column("title"),
    column("summary"), column("payload", JSONB), column("requested_by_type"), column("requested_by"),
)


# ---------------------------------------------------------------------------
# Registry. Objective keys are the platform's own names; `stored` maps each one
# onto the live campaign_objective enum (awareness, traffic, engagement,
# conversions, reach, leads, app_promotion, message_replies). Text limits are
# each platform's documented maximums (SPEC-BE-063..068).
# ---------------------------------------------------------------------------
def _o(key: str, label: str, description: str, stored: str, reason: str | None = None) -> dict[str, Any]:
    return {"key": key, "label": label, "description": description, "stored": stored, "reason": reason}


PLATFORMS: dict[str, dict[str, Any]] = {
    "meta": {
        "label": "Meta", "provider": "meta_ads", "runs_on": "Facebook, Instagram, Messenger, Audience Network",
        "channels": ["facebook", "instagram", "messenger"],
        "hierarchy": {"campaign": "Campaign", "group": "Ad set", "ad": "Ad"},
        "objectives": [], "creative": {}, "adapter": None,  # Meta uses its own builder (SPEC-BE-055)
    },
    "tiktok": {
        "label": "TikTok", "provider": "tiktok_ads", "runs_on": "TikTok, Pangle, Global App Bundle",
        "channels": ["tiktok"], "spec": "SPEC-BE-063",
        "hierarchy": {"campaign": "Campaign", "group": "Ad group", "ad": "Ad"},
        "objectives": [
            _o("REACH", "Reach", "Show your ad to as many people as possible.", "reach"),
            _o("TRAFFIC", "Traffic", "Send people to your website or app.", "traffic"),
            _o("VIDEO_VIEWS", "Video views", "Get more people to watch your video.", "awareness"),
            _o("ENGAGEMENT", "Community interaction", "Get more followers or profile visits.", "engagement"),
            _o("LEAD_GENERATION", "Lead generation", "Collect leads with an instant form or your site.", "leads"),
            _o("APP_PROMOTION", "App promotion", "Get people to install or use your app.", "app_promotion"),
            _o("WEB_CONVERSIONS", "Website conversions", "Drive purchases or sign-ups on your site (needs a pixel).", "conversions"),
            _o("PRODUCT_SALES", "Product sales", "Sell catalog products.", "conversions", "Needs a TikTok product catalog, which isn't connected."),
        ],
        "creative": {"formats": ["single_video", "single_image", "spark_ad"], "text_limits": {"ad_text": 100, "display_name": 40},
                     "media": {"video": "9:16, 16:9 or 1:1, at least 5 s, up to 500 MB", "image": "Pangle placement only"}},
    },
    "google": {
        "label": "Google Ads", "provider": "google_ads", "runs_on": "Search, YouTube, Display, Gmail, Discover, Maps",
        "channels": ["google"], "spec": "SPEC-BE-064",
        "hierarchy": {"campaign": "Campaign", "group": "Ad group", "ad": "Ad"},
        "objectives": [
            _o("SALES", "Sales", "Drive online, in-app or in-store sales.", "conversions"),
            _o("LEADS", "Leads", "Get sign-ups and other conversions.", "leads"),
            _o("WEBSITE_TRAFFIC", "Website traffic", "Get the right people to visit your site.", "traffic"),
            _o("AWARENESS", "Awareness and consideration", "Reach a broad audience and build interest.", "awareness"),
            _o("APP_PROMOTION", "App promotion", "Get more installs and engagement for your app.", "app_promotion", "App campaigns aren't included in this release."),
        ],
        "campaign_types": [
            _o("SEARCH", "Search", "Text ads on Google search results.", "traffic"),
            _o("PERFORMANCE_MAX", "Performance Max", "One campaign across all Google channels.", "conversions"),
            _o("DISPLAY", "Display", "Image ads across millions of websites and apps.", "awareness"),
            _o("DEMAND_GEN", "Demand Gen", "Image and video ads on YouTube, Discover and Gmail.", "engagement"),
            _o("VIDEO", "YouTube video", "Video ads on YouTube.", "awareness", "The Google Ads API can't create this campaign type; use Demand Gen for YouTube video ads."),
        ],
        "creative": {"formats": ["responsive_search", "responsive_display", "demand_gen", "asset_group"],
                     "text_limits": {"headlines": 30, "long_headlines": 90, "descriptions": 90, "path1": 15, "path2": 15, "business_name": 25},
                     "media": {"image": "Landscape 1.91:1, square 1:1, logo 1:1"}},
    },
    # YouTube ads are Google Ads Video / Demand Gen campaigns: same connection
    # (google_ads) and the same adapter module (google_ads.py, SPEC-BE-064).
    # Stored with the existing `google` channel + metadata.platform = youtube,
    # so no enum change is needed.
    "youtube": {
        "label": "YouTube", "provider": "google_ads", "module": "google_ads",
        "runs_on": "YouTube videos, Shorts, YouTube search and home feed, Google video partners",
        "channels": ["google"], "spec": "SPEC-BE-064",
        "hierarchy": {"campaign": "Campaign", "group": "Ad group", "ad": "Video ad"},
        "objectives": [
            _o("VIDEO_VIEWS", "Video views", "Get more views and engagement on your videos.", "awareness"),
            _o("AWARENESS", "Awareness and reach", "Reach as many people as possible on YouTube.", "reach"),
            _o("WEBSITE_TRAFFIC", "Website traffic", "Send viewers to your site.", "traffic"),
            _o("LEADS", "Leads", "Get sign-ups from viewers.", "leads"),
            _o("SALES", "Sales", "Drive purchases from viewers (needs Google Ads conversion tracking).", "conversions"),
        ],
        "campaign_types": [
            _o("DEMAND_GEN", "Demand Gen", "Video ads in YouTube in-stream, in-feed and Shorts (plus Discover and Gmail).", "engagement"),
            _o("VIDEO", "Video", "YouTube video campaigns (views and reach).", "awareness", "The Google Ads API can't create this campaign type; use Demand Gen for YouTube video ads."),
        ],
        # Published as Demand Gen video ads; the format picks the YouTube surface
        # (in-stream / in-feed / Shorts channel controls). Bumper ads need a
        # Video campaign, which the API can't create, so they aren't offered.
        "creative": {"formats": ["skippable_in_stream", "in_feed", "shorts"],
                     "text_limits": {"headline": 40, "long_headline": 90, "description": 90, "business_name": 25},
                     "media": {"video": "A YouTube video (public or unlisted): paste its link or ID.", "logo": "Square logo image (1:1), required by Google."}},
    },
    "linkedin": {
        "label": "LinkedIn", "provider": "linkedin_ads", "runs_on": "LinkedIn feed, LinkedIn Audience Network",
        "channels": ["linkedin"], "spec": "SPEC-BE-065",
        # LinkedIn's own names: campaign group > campaign > creative.
        "hierarchy": {"campaign": "Campaign group", "group": "Campaign", "ad": "Creative"},
        "objectives": [
            _o("BRAND_AWARENESS", "Brand awareness", "Get your brand seen by more professionals.", "awareness"),
            _o("WEBSITE_VISIT", "Website visits", "Send professionals to your site.", "traffic"),
            _o("ENGAGEMENT", "Engagement", "Get more likes, comments, shares and follows.", "engagement"),
            _o("VIDEO_VIEW", "Video views", "Get more people to watch your video.", "awareness"),
            _o("LEAD_GENERATION", "Lead generation", "Collect leads with a LinkedIn Lead Gen Form.", "leads"),
            _o("WEBSITE_CONVERSION", "Website conversions", "Drive purchases or sign-ups on your site.", "conversions"),
            _o("TALENT_LEADS", "Talent leads / job applicants", "Hiring campaigns.", "leads", "Hiring campaigns aren't included."),
        ],
        "creative": {"formats": ["single_image", "video", "carousel", "text_ad", "document"],
                     "text_limits": {"intro_text": 600, "headline": 200, "description": 300},
                     "media": {"image": "1.91:1, 1:1 or 1:1.91", "video": "3 s to 30 min"}},
    },
    "x": {
        "label": "X (Twitter)", "provider": "x_ads", "runs_on": "X timelines, search, profiles; X Audience Platform",
        "channels": ["x"], "spec": "SPEC-BE-066",
        "hierarchy": {"campaign": "Campaign", "group": "Line item", "ad": "Promoted post"},
        "objectives": [
            _o("REACH", "Reach", "Show your post to as many people as possible.", "reach"),
            _o("ENGAGEMENTS", "Engagements", "Get more likes, replies and reposts.", "engagement"),
            _o("VIDEO_VIEWS", "Video views", "Get more people to watch your video.", "awareness"),
            _o("WEBSITE_CLICKS", "Website traffic", "Send people to your site.", "traffic"),
            _o("WEBSITE_CONVERSIONS", "Website conversions", "Drive actions on your site.", "conversions"),
            _o("APP_INSTALLS", "App installs", "Get people to install your app.", "app_promotion"),
            _o("FOLLOWERS", "Followers", "Grow your audience on X.", "engagement"),
        ],
        "creative": {"formats": ["text", "image", "video", "website_card"], "text_limits": {"text": 280, "card_headline": 70},
                     "media": {"image": "Up to 5 MB", "video": "Up to 2 min 20 s"}},
    },
    "snapchat": {
        "label": "Snapchat", "provider": "snapchat_ads", "runs_on": "Snapchat Stories, Discover, Spotlight",
        "channels": ["snapchat"], "spec": "SPEC-BE-067",
        "hierarchy": {"campaign": "Campaign", "group": "Ad squad", "ad": "Ad"},
        "objectives": [
            _o("AWARENESS_AND_ENGAGEMENT", "Awareness & engagement", "Reach Snapchatters and get them engaging.", "awareness"),
            _o("TRAFFIC", "Traffic", "Send Snapchatters to your site or app.", "traffic"),
            _o("LEADS", "Leads", "Collect leads with an instant form or your site.", "leads"),
            _o("APP_PROMOTION", "App promotion", "Get installs and app activity.", "app_promotion"),
            _o("SALES", "Sales", "Drive purchases on your site (needs the Snap Pixel).", "conversions"),
        ],
        "creative": {"formats": ["single_image", "single_video"], "text_limits": {"brand_name": 25, "headline": 34},
                     "media": {"image": "9:16, 1080x1920", "video": "9:16, 3 to 180 s"}},
    },
    "pinterest": {
        "label": "Pinterest", "provider": "pinterest_ads", "runs_on": "Pinterest home feed, search, related Pins",
        "channels": ["pinterest"], "spec": "SPEC-BE-068",
        "hierarchy": {"campaign": "Campaign", "group": "Ad group", "ad": "Promoted Pin"},
        "objectives": [
            _o("AWARENESS", "Brand awareness", "Get people to discover your brand.", "awareness"),
            _o("VIDEO_VIEW", "Video views", "Get more people to watch your video.", "awareness"),
            _o("CONSIDERATION", "Consideration", "Drive clicks to your site.", "traffic"),
            _o("WEB_CONVERSION", "Conversions", "Drive actions on your site (needs the Pinterest tag).", "conversions"),
            _o("CATALOG_SALES", "Catalog sales", "Promote products from your catalog.", "conversions", "Needs a Pinterest catalog, which isn't connected."),
        ],
        "creative": {"formats": ["image_pin", "video_pin", "existing_pin"], "text_limits": {"title": 100, "description": 500, "alt_text": 500},
                     "media": {"image": "2:3 recommended", "video": "4 s to 15 min"}},
    },
}
BUILDER_PLATFORMS = tuple(k for k in PLATFORMS if k != "meta")


def _adapter(platform: str) -> ModuleType | None:
    """The platform's adapter module if its publishing spec is built (it
    exposes `publish`); None otherwise."""
    try:
        module = importlib.import_module(f"app.integrations.{PLATFORMS[platform].get('module') or platform + '_ads'}")
    except ImportError:
        return None
    return module if callable(getattr(module, "publish", None)) else None


def _not_built(platform: str) -> AppError:
    p = PLATFORMS[platform]
    return AppError(f"Publishing to {p['label']} isn't available yet ({p.get('spec', '')}). Your draft is saved.", 501)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _cents(amount: Decimal | None) -> int | None:
    if amount is None:
        return None
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _major(cents: int | None) -> float | None:
    return None if cents is None else float(Decimal(cents) / 100)


def _utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value else None


def _pc(c: Campaign) -> dict[str, Any]:
    return dict((c.extra_metadata or {}).get("platform_campaign") or {})


def _set_pc(c: Campaign, **values: Any) -> None:
    meta = dict(c.extra_metadata or {})
    meta["platform_campaign"] = {**dict(meta.get("platform_campaign") or {}), **values}
    c.extra_metadata = meta


def _gf(g: AdGroup) -> dict[str, Any]:
    return dict((g.extra_metadata or {}).get("platform_fields") or {})


def _set_gf(g: AdGroup, **values: Any) -> None:
    meta = dict(g.extra_metadata or {})
    meta["platform_fields"] = {**dict(meta.get("platform_fields") or {}), **values}
    g.extra_metadata = meta


def _creative(ad: Ad) -> dict[str, Any]:
    return dict((ad.extra_metadata or {}).get("creative") or {})


def _platform_of(c: Campaign) -> str | None:
    return (c.extra_metadata or {}).get("platform")


def is_platform_campaign(c: Campaign) -> bool:
    """True for a campaign built here (not Meta, not the legacy wizard)."""
    return _platform_of(c) in BUILDER_PLATFORMS


def _campaign(db: Session, tenant_id: str, campaign_id: str, lock: bool = False) -> Campaign:
    query = db.query(Campaign).filter(Campaign.tenant_id == tenant_id, Campaign.id == campaign_id)
    if lock:
        query = query.with_for_update()
    try:
        c = query.first()
    except Exception:  # noqa: BLE001 - a malformed id is a 404, like the Meta builder
        db.rollback()
        c = None
    if c is None or not is_platform_campaign(c):
        raise NotFoundError("Campaign not found.")
    return c


def _group(db: Session, tenant_id: str, group_id: str) -> tuple[AdGroup, Campaign]:
    try:
        g = db.query(AdGroup).filter(AdGroup.tenant_id == tenant_id, AdGroup.id == group_id).first()
    except Exception:  # noqa: BLE001
        db.rollback()
        g = None
    if g is None:
        raise NotFoundError("Not found.")
    return g, _campaign(db, tenant_id, str(g.campaign_id))


def _ad(db: Session, tenant_id: str, ad_id: str) -> tuple[Ad, AdGroup, Campaign]:
    try:
        ad = db.query(Ad).filter(Ad.tenant_id == tenant_id, Ad.id == ad_id).first()
    except Exception:  # noqa: BLE001
        db.rollback()
        ad = None
    if ad is None:
        raise NotFoundError("Not found.")
    g, c = _group(db, tenant_id, str(ad.ad_group_id))
    return ad, g, c


def _groups(c: Campaign) -> list[AdGroup]:
    return sorted([g for g in c.ad_groups if g.tenant_id == c.tenant_id], key=lambda g: (g.created_at, str(g.id)))


def _ads(g: AdGroup) -> list[Ad]:
    return sorted([a for a in g.ads if a.tenant_id == g.tenant_id], key=lambda a: (a.created_at, str(a.id)))


def _audit(db: Session, tenant_id: str, actor: str, action: str, resource_type: str, resource_id: Any, meta: dict[str, Any] | None = None) -> None:
    # write_audit_log commits: the change and its audit row land in one commit.
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor, action=action, resource_type=resource_type,
                    resource_id=str(resource_id), metadata=meta or {})


def _conn(db: Session, tenant_id: str, platform: str) -> dict[str, Any] | None:
    return integration_service.ad_platform_connection(db, tenant_id, PLATFORMS[platform]["provider"])


def _require_conn(db: Session, tenant_id: str, platform: str) -> dict[str, Any]:
    conn = _conn(db, tenant_id, platform)
    label = PLATFORMS[platform]["label"]
    if conn is None:
        raise ConflictError(f"Connect {label} in Integrations first.")
    if conn["status"] != "connected":
        raise ConflictError(f"Reconnect {label} in Integrations; the connection has expired or failed.")
    return conn


def _objective(platform: str, key: str, campaign_type: bool = False) -> dict[str, Any]:
    options = PLATFORMS[platform]["campaign_types" if campaign_type else "objectives"]
    found = next((o for o in options if o["key"] == key), None)
    what = "campaign type" if campaign_type else "objective"
    if found is None:
        raise AppError(f"Unknown {what} {key} for {PLATFORMS[platform]['label']}.", 422)
    if found["reason"]:
        raise AppError(found["reason"], 422)
    return found


# ---------------------------------------------------------------------------
# Registry endpoint
# ---------------------------------------------------------------------------
def platforms(db: Session, tenant_id: str) -> dict[str, Any]:
    items = []
    for key, p in PLATFORMS.items():
        if key == "meta":
            meta = integration_service.meta_publish_credentials(db, tenant_id)
            connected = bool(meta and meta["status"] == "connected" and meta["access_token"])
            account = None
            if meta:
                record = integration_service.store_record(db, tenant_id, meta["integration_id"])
                account = record.account_name if record else None
            publishing = "live" if connected else "needs_connection"
        else:
            conn = _conn(db, tenant_id, key)
            connected = bool(conn and conn["status"] == "connected")
            account = conn["account_name"] if conn else None
            publishing = "not_built" if _adapter(key) is None else ("live" if connected else "needs_connection")
        items.append({
            "key": key, "label": p["label"], "runs_on": p["runs_on"], "channels": p["channels"], "hierarchy": p["hierarchy"],
            "connected": connected, "account_name": account if connected else None,
            "connect_hint": f"Connect {p['label']} in Integrations to publish.",
            "objectives": [{k: o[k] for k in ("key", "label", "description", "reason")} | {"available": o["reason"] is None} for o in p["objectives"]],
            "campaign_types": [{k: o[k] for k in ("key", "label", "description", "reason")} | {"available": o["reason"] is None} for o in p.get("campaign_types", [])],
            "creative": p["creative"], "publishing": publishing,
        })
    return {"platforms": items}


# ---------------------------------------------------------------------------
# Tree
# ---------------------------------------------------------------------------
def _group_dict(g: AdGroup) -> dict[str, Any]:
    f = _gf(g)
    return {
        "id": str(g.id), "name": g.name, "status": g.status, "external_id": g.external_id,
        "budget_mode": f.get("budget_mode") or "none", "budget": _major(f.get("budget_cents")),
        "starts_at": _utc(f.get("starts_at")), "ends_at": _utc(f.get("ends_at")),
        "targeting": dict(g.targeting or {}), "fields": dict(f.get("fields") or {}),
        "ads": [{"id": str(a.id), "name": a.name, "status": a.status, "external_id": a.external_ad_id, "creative": _creative(a)} for a in _ads(g)],
    }


def tree(db: Session, c: Campaign) -> dict[str, Any]:
    from app.services.campaign_service import approval_decision

    platform = _platform_of(c) or ""
    p = PLATFORMS[platform]
    pc = _pc(c)
    objective = next((o for o in p["objectives"] if o["key"] == pc.get("objective")), None)
    conn = _conn(db, str(c.tenant_id), platform)
    adapter = _adapter(platform)
    required, reason = approval_decision(db, c) if c.daily_cap_cents else (False, "")
    return {
        "platform": platform, "label": p["label"], "hierarchy": p["hierarchy"],
        "campaign": {
            "id": str(c.id), "name": c.name, "objective": pc.get("objective") or "", "objective_label": objective["label"] if objective else "",
            "campaign_type": pc.get("campaign_type"), "status": c.status, "currency": c.currency.strip(),
            "budget_mode": pc.get("budget_mode") or "none", "budget": _major(pc.get("budget_cents")),
            "starts_at": _utc(c.starts_at), "ends_at": _utc(c.ends_at), "fields": dict(pc.get("fields") or {}),
            "external_id": pc.get("external_id"), "last_error": pc.get("last_error"), "pending_approval_id": pc.get("pending_approval_id"),
        },
        "groups": [_group_dict(g) for g in _groups(c)],
        "issues": _issues(c),
        "connection": {
            "connected": bool(conn and conn["status"] == "connected"),
            "account_name": conn["account_name"] if conn else None,
            "publishing": "not_built" if adapter is None else "available",
            "message": None if adapter else f"Publishing to {p['label']} isn't available yet ({p.get('spec', '')}).",
        },
        "approval": {"required": required, "reason": reason} if c.daily_cap_cents else None,
    }


def _plain(value: Any) -> Any:
    """The tree as plain JSON types (datetimes -> ISO strings) for adapters."""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def adapter_tree(db: Session, c: Campaign) -> dict[str, Any]:
    return dict(_plain(tree(db, c)))


def get_tree(db: Session, tenant_id: str, campaign_id: str) -> dict[str, Any]:
    return tree(db, _campaign(db, tenant_id, campaign_id))


# ---------------------------------------------------------------------------
# Validation (platform-independent rules; each adapter adds its own)
# ---------------------------------------------------------------------------
def _issue(level: str, row_id: Any, path: str, message: str, severity: str = "error") -> dict[str, Any]:
    return {"level": level, "id": str(row_id) if row_id else None, "path": path, "message": message, "severity": severity}


def _https(value: Any) -> bool:
    parsed = urlparse(str(value or ""))
    return parsed.scheme == "https" and bool(parsed.hostname)


def _issues(c: Campaign) -> list[dict[str, Any]]:
    """What still blocks publishing, in tree order."""
    platform = _platform_of(c) or ""
    p = PLATFORMS[platform]
    pc = _pc(c)
    out: list[dict[str, Any]] = []
    if not pc.get("objective"):
        out.append(_issue("campaign", c.id, "campaign.objective", "Choose an objective."))
    if PLATFORMS[platform].get("campaign_types") and not pc.get("campaign_type"):
        out.append(_issue("campaign", c.id, "campaign.campaign_type", "Choose a campaign type."))
    now = datetime.now(timezone.utc)
    if c.ends_at and c.starts_at and c.ends_at <= c.starts_at:
        out.append(_issue("campaign", c.id, "campaign.ends_at", "The end must be after the start."))
    if c.ends_at and c.ends_at <= now:
        out.append(_issue("campaign", c.id, "campaign.ends_at", "The end date has passed."))
    campaign_budget = (pc.get("budget_mode") or "none") != "none" and pc.get("budget_cents")
    if (pc.get("budget_mode") or "none") == "total" and not c.ends_at:
        out.append(_issue("campaign", c.id, "campaign.ends_at", "A total budget needs an end date."))
    groups = _groups(c)
    if not groups:
        out.append(_issue("campaign", c.id, "groups", f"Add at least one {p['hierarchy']['group'].lower()}."))
    limits: dict[str, int] = p["creative"].get("text_limits", {})
    for gi, g in enumerate(groups):
        f = _gf(g)
        gpath = f"groups[{gi}]"
        if not campaign_budget and not ((f.get("budget_mode") or "none") != "none" and f.get("budget_cents")):
            out.append(_issue("group", g.id, f"{gpath}.budget", f"Set a budget on the {p['hierarchy']['campaign'].lower()} or on this {p['hierarchy']['group'].lower()}."))
        if not (g.targeting or {}).get("locations"):
            out.append(_issue("group", g.id, f"{gpath}.targeting.locations", "Add at least one location."))
        start, end = _utc(f.get("starts_at")), _utc(f.get("ends_at"))
        if start and end and end <= start:
            out.append(_issue("group", g.id, f"{gpath}.ends_at", "The end must be after the start."))
        ads = _ads(g)
        if not ads:
            out.append(_issue("group", g.id, f"{gpath}.ads", f"Add at least one {p['hierarchy']['ad'].lower()}."))
        for ai, ad in enumerate(ads):
            cr = _creative(ad)
            apath = f"{gpath}.ads[{ai}]"
            if not cr.get("format"):
                out.append(_issue("ad", ad.id, f"{apath}.format", "Choose a format."))
            elif cr["format"] not in p["creative"].get("formats", []):
                out.append(_issue("ad", ad.id, f"{apath}.format", f"{cr['format']} isn't a {p['label']} format."))
            for key, limit in limits.items():
                values = cr.get(key)
                for i, text in enumerate(values if isinstance(values, list) else [values]):
                    if isinstance(text, str) and len(text) > limit:
                        where = f"{key}[{i}]" if isinstance(values, list) else key
                        out.append(_issue("ad", ad.id, f"{apath}.{where}", f"{key.replace('_', ' ').capitalize()} is {len(text)} characters; {p['label']} allows {limit}."))
            if cr.get("destination_url") and not _https(cr["destination_url"]):
                out.append(_issue("ad", ad.id, f"{apath}.destination_url", "The link must start with https://."))
    return out


def validate(db: Session, tenant_id: str, campaign_id: str) -> dict[str, Any]:
    c = _campaign(db, tenant_id, campaign_id)
    platform = _platform_of(c) or ""
    issues = _issues(c)
    adapter = _adapter(platform)
    conn = _conn(db, tenant_id, platform)
    if adapter is not None and conn is not None and conn["status"] == "connected" and callable(getattr(adapter, "validate", None)):
        try:
            issues += adapter.validate(conn, adapter_tree(db, c))
        except PlatformError as exc:
            issues.append(_issue("campaign", c.id, exc.path or "campaign", exc.message))
    return {"ok": not any(i["severity"] == "error" for i in issues), "issues": issues}


# ---------------------------------------------------------------------------
# Roll-ups (lists, analytics, and the SPEC-BE-047 spend-cap rule read these)
# ---------------------------------------------------------------------------
def _days(start: datetime | None, end: datetime | None) -> int:
    if not start or not end or end <= start:
        return 1
    return max(1, int(Decimal((end - start).total_seconds()) / Decimal(86400) + Decimal("0.999999")))


def _daily(mode: str, cents: int | None, start: datetime | None, end: datetime | None) -> int:
    if not cents or mode == "none":
        return 0
    if mode == "daily":
        return cents
    return int((Decimal(cents) / _days(start, end)).to_integral_value(rounding=ROUND_CEILING))


def _rollup(c: Campaign) -> None:
    pc = _pc(c)
    groups = _groups(c)
    mode = pc.get("budget_mode") or "none"
    if mode != "none" and pc.get("budget_cents"):
        daily = _daily(mode, pc["budget_cents"], c.starts_at, c.ends_at)
        total = pc["budget_cents"] if mode == "total" else pc["budget_cents"] * _days(c.starts_at, c.ends_at)
    else:
        daily = total = 0
        for g in groups:
            f = _gf(g)
            gmode = f.get("budget_mode") or "none"
            start, end = _utc(f.get("starts_at")) or c.starts_at, _utc(f.get("ends_at")) or c.ends_at
            daily += _daily(gmode, f.get("budget_cents"), start, end)
            total += (f.get("budget_cents") or 0) if gmode == "total" else (f.get("budget_cents") or 0) * _days(start, end)
    c.daily_cap_cents = daily
    c.budget_cents = total
    c.channels = list(PLATFORMS[_platform_of(c) or ""]["channels"])


# ---------------------------------------------------------------------------
# Writes (manager+, drafts only)
# ---------------------------------------------------------------------------
def _draft_only(c: Campaign, what: str) -> None:
    if c.status != "draft":
        raise ConflictError(f"Only a draft's {what} can be changed; this campaign is {c.status}.")
    if _pc(c).get("pending_approval_id"):
        raise ConflictError("This campaign is waiting for owner approval.")


def _new_group(c: Campaign, name: str) -> AdGroup:
    return AdGroup(tenant_id=c.tenant_id, campaign_id=c.id, name=name[:255], targeting={"locations": []}, status="draft",
                   extra_metadata={"platform_fields": {"budget_mode": "none", "fields": {}}})


def _new_ad(g: AdGroup, platform: str, name: str) -> Ad:
    first_format = (PLATFORMS[platform]["creative"].get("formats") or [None])[0]
    return Ad(tenant_id=g.tenant_id, ad_group_id=g.id, name=name[:255], status="draft",
              extra_metadata={"creative": {"format": first_format}})


def create_campaign(db: Session, tenant_id: str, actor: str, platform: str, payload: s.CampaignCreate) -> dict[str, Any]:
    if platform not in BUILDER_PLATFORMS:
        raise NotFoundError("Unknown ad platform.")
    objective = _objective(platform, payload.objective)
    stored = objective["stored"]
    if PLATFORMS[platform].get("campaign_types"):
        if not payload.campaign_type:
            raise AppError("Choose a campaign type.", 422)
        _objective(platform, payload.campaign_type, campaign_type=True)
    elif payload.campaign_type:
        raise AppError(f"{PLATFORMS[platform]['label']} has no campaign types.", 422)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).one()
    c = Campaign(
        tenant_id=tenant_id, name=payload.name, objective=stored, status="draft", channels=list(PLATFORMS[platform]["channels"]),
        budget_cents=0, daily_cap_cents=0, spent_cents=0, currency=(tenant.currency or "USD").strip(),
        extra_metadata={"platform": platform, "builder": {},
                        "platform_campaign": {"objective": payload.objective, "campaign_type": payload.campaign_type,
                                              "budget_mode": "none", "fields": {}}},
        created_by=actor,
    )
    db.add(c)
    db.flush()
    h = PLATFORMS[platform]["hierarchy"]
    g = _new_group(c, f"{c.name} — {h['group']}")
    db.add(g)
    db.flush()
    db.add(_new_ad(g, platform, f"{c.name} — {h['ad']}"))
    db.flush()
    db.refresh(c)
    _rollup(c)
    _audit(db, tenant_id, actor, "ads_builder.campaign_created", "campaign", c.id,
           {"platform": platform, "objective": payload.objective, "campaign_type": payload.campaign_type})
    db.refresh(c)
    logger.info("ads_builder_campaign_created", tenant_id=tenant_id, campaign_id=str(c.id), platform=platform)
    return tree(db, c)


def update_campaign(db: Session, tenant_id: str, actor: str, campaign_id: str, payload: s.CampaignFields) -> dict[str, Any]:
    c = _campaign(db, tenant_id, campaign_id, lock=True)
    _draft_only(c, "settings")
    platform = _platform_of(c) or ""
    sent = payload.model_fields_set
    if "name" in sent and payload.name:
        c.name = payload.name
    if "objective" in sent and payload.objective:
        c.objective = _objective(platform, payload.objective)["stored"]
        _set_pc(c, objective=payload.objective)
    if "campaign_type" in sent:
        if not PLATFORMS[platform].get("campaign_types"):
            raise AppError(f"{PLATFORMS[platform]['label']} has no campaign types.", 422)
        if payload.campaign_type:
            _objective(platform, payload.campaign_type, campaign_type=True)
        _set_pc(c, campaign_type=payload.campaign_type)
    if "budget_mode" in sent and payload.budget_mode:
        _set_pc(c, budget_mode=payload.budget_mode)
    if "budget" in sent:
        _set_pc(c, budget_cents=_cents(payload.budget))
    if "starts_at" in sent:
        c.starts_at = payload.starts_at
    if "ends_at" in sent:
        c.ends_at = payload.ends_at
    if "fields" in sent:
        _set_pc(c, fields={**dict(_pc(c).get("fields") or {}), **(payload.fields or {})})
    _rollup(c)
    _audit(db, tenant_id, actor, "ads_builder.campaign_updated", "campaign", c.id, {"fields": sorted(sent)})
    db.refresh(c)
    return tree(db, c)


def add_group(db: Session, tenant_id: str, actor: str, campaign_id: str, payload: s.GroupFields) -> dict[str, Any]:
    c = _campaign(db, tenant_id, campaign_id, lock=True)
    _draft_only(c, "structure")
    platform = _platform_of(c) or ""
    h = PLATFORMS[platform]["hierarchy"]
    if len(_groups(c)) >= MAX_GROUPS:
        raise AppError(f"A campaign can have at most {MAX_GROUPS} {h['group'].lower()}s.", 422)
    g = _new_group(c, payload.name or f"{c.name} — {h['group']} {len(_groups(c)) + 1}")
    db.add(g)
    db.flush()
    _apply_group(g, payload)
    db.add(_new_ad(g, platform, f"{g.name} — {h['ad']}"))
    db.flush()
    db.refresh(c)
    _rollup(c)
    _audit(db, tenant_id, actor, "ads_builder.group_created", "ad_group", g.id, {"campaign_id": str(c.id)})
    db.refresh(c)
    return tree(db, c)


def _apply_group(g: AdGroup, payload: s.GroupFields) -> list[str]:
    sent = payload.model_fields_set
    if "name" in sent and payload.name:
        g.name = payload.name
    if "targeting" in sent and payload.targeting is not None:
        g.targeting = {**dict(g.targeting or {}), **payload.targeting}
    if "budget_mode" in sent and payload.budget_mode:
        _set_gf(g, budget_mode=payload.budget_mode)
    if "budget" in sent:
        _set_gf(g, budget_cents=_cents(payload.budget))
    if "starts_at" in sent:
        _set_gf(g, starts_at=_iso(payload.starts_at))
    if "ends_at" in sent:
        _set_gf(g, ends_at=_iso(payload.ends_at))
    if "fields" in sent:
        _set_gf(g, fields={**dict(_gf(g).get("fields") or {}), **(payload.fields or {})})
    return sorted(sent)


def update_group(db: Session, tenant_id: str, actor: str, group_id: str, payload: s.GroupFields) -> dict[str, Any]:
    g, c = _group(db, tenant_id, group_id)
    _draft_only(c, "structure")
    sent = _apply_group(g, payload)
    db.flush()
    db.refresh(c)
    _rollup(c)
    _audit(db, tenant_id, actor, "ads_builder.group_updated", "ad_group", g.id, {"fields": sent})
    db.refresh(c)
    return tree(db, c)


def duplicate_group(db: Session, tenant_id: str, actor: str, group_id: str) -> dict[str, Any]:
    g, c = _group(db, tenant_id, group_id)
    _draft_only(c, "structure")
    if len(_groups(c)) >= MAX_GROUPS:
        raise AppError(f"A campaign can have at most {MAX_GROUPS} groups.", 422)
    copy_g = AdGroup(tenant_id=g.tenant_id, campaign_id=c.id, name=f"{g.name} (copy)"[:255], targeting=dict(g.targeting or {}),
                     status="draft", extra_metadata={"platform_fields": _gf(g)})
    db.add(copy_g)
    db.flush()
    for ad in _ads(g):
        db.add(Ad(tenant_id=ad.tenant_id, ad_group_id=copy_g.id, name=ad.name, status="draft", extra_metadata={"creative": _creative(ad)}))
    db.flush()
    db.refresh(c)
    _rollup(c)
    _audit(db, tenant_id, actor, "ads_builder.group_duplicated", "ad_group", copy_g.id, {"from": str(g.id)})
    db.refresh(c)
    return tree(db, c)


def delete_group(db: Session, tenant_id: str, actor: str, group_id: str) -> dict[str, Any]:
    g, c = _group(db, tenant_id, group_id)
    _draft_only(c, "structure")
    if len(_groups(c)) <= 1:
        raise AppError("A campaign needs at least one group.", 422)
    for ad in _ads(g):
        db.delete(ad)
    db.delete(g)
    db.flush()
    db.refresh(c)
    _rollup(c)
    _audit(db, tenant_id, actor, "ads_builder.group_deleted", "ad_group", group_id, {"campaign_id": str(c.id)})
    db.refresh(c)
    return tree(db, c)


def add_ad(db: Session, tenant_id: str, actor: str, group_id: str, payload: s.AdFields) -> dict[str, Any]:
    g, c = _group(db, tenant_id, group_id)
    _draft_only(c, "structure")
    platform = _platform_of(c) or ""
    if len(_ads(g)) >= MAX_ADS:
        raise AppError(f"A group can have at most {MAX_ADS} ads.", 422)
    ad = _new_ad(g, platform, payload.name or f"{g.name} — {PLATFORMS[platform]['hierarchy']['ad']} {len(_ads(g)) + 1}")
    if payload.creative:
        ad.extra_metadata = {"creative": {**_creative(ad), **payload.creative}}
    db.add(ad)
    db.flush()
    _audit(db, tenant_id, actor, "ads_builder.ad_created", "ad", ad.id, {"ad_group_id": str(g.id)})
    db.refresh(c)
    return tree(db, c)


def update_ad(db: Session, tenant_id: str, actor: str, ad_id: str, payload: s.AdFields) -> dict[str, Any]:
    ad, _, c = _ad(db, tenant_id, ad_id)
    _draft_only(c, "ads")
    sent = payload.model_fields_set
    if "name" in sent and payload.name:
        ad.name = payload.name
    if "creative" in sent and payload.creative is not None:
        ad.extra_metadata = {**dict(ad.extra_metadata or {}), "creative": {**_creative(ad), **payload.creative}}
    _audit(db, tenant_id, actor, "ads_builder.ad_updated", "ad", ad.id, {"fields": sorted(sent)})
    db.refresh(c)
    return tree(db, c)


def duplicate_ad(db: Session, tenant_id: str, actor: str, ad_id: str) -> dict[str, Any]:
    ad, g, c = _ad(db, tenant_id, ad_id)
    _draft_only(c, "ads")
    if len(_ads(g)) >= MAX_ADS:
        raise AppError(f"A group can have at most {MAX_ADS} ads.", 422)
    copy_ad = Ad(tenant_id=ad.tenant_id, ad_group_id=g.id, name=f"{ad.name} (copy)"[:255], status="draft", extra_metadata={"creative": _creative(ad)})
    db.add(copy_ad)
    db.flush()
    _audit(db, tenant_id, actor, "ads_builder.ad_duplicated", "ad", copy_ad.id, {"from": str(ad.id)})
    db.refresh(c)
    return tree(db, c)


def delete_ad(db: Session, tenant_id: str, actor: str, ad_id: str) -> dict[str, Any]:
    ad, g, c = _ad(db, tenant_id, ad_id)
    _draft_only(c, "ads")
    if len(_ads(g)) <= 1:
        raise AppError("A group needs at least one ad.", 422)
    db.delete(ad)
    db.flush()
    _audit(db, tenant_id, actor, "ads_builder.ad_deleted", "ad", ad_id, {"ad_group_id": str(g.id)})
    db.refresh(c)
    return tree(db, c)


# ---------------------------------------------------------------------------
# Lookups and media (through the adapter; need a connection)
# ---------------------------------------------------------------------------
def lookup(db: Session, tenant_id: str, platform: str, kind: str, query: str) -> list[dict[str, Any]]:
    if platform not in BUILDER_PLATFORMS:
        raise NotFoundError("Unknown ad platform.")
    adapter = _adapter(platform)
    if adapter is None or not callable(getattr(adapter, "lookup", None)):
        raise _not_built(platform)
    conn = _require_conn(db, tenant_id, platform)
    return _call(db, tenant_id, platform, adapter.lookup, conn, kind, query)


def upload_media(db: Session, tenant_id: str, actor: str, platform: str, filename: str, content: bytes) -> dict[str, Any]:
    if platform not in BUILDER_PLATFORMS:
        raise NotFoundError("Unknown ad platform.")
    adapter = _adapter(platform)
    if adapter is None or not callable(getattr(adapter, "upload_media", None)):
        raise _not_built(platform)
    conn = _require_conn(db, tenant_id, platform)
    result: dict[str, Any] = _call(db, tenant_id, platform, adapter.upload_media, conn, filename, content)
    _audit(db, tenant_id, actor, "ads_builder.media_uploaded", "integration", conn["integration_id"],
           {"platform": platform, "kind": result.get("kind"), "media_id": result.get("media_id")})
    return result


def _call(db: Session, tenant_id: str, platform: str, fn: Any, *args: Any) -> Any:
    try:
        return fn(*args)
    except PlatformError as exc:
        if exc.auth:
            integration_service.mark_ad_platform_expired(db, tenant_id, PLATFORMS[platform]["provider"], exc.message)
            db.commit()
        raise AppError(exc.message, 409 if exc.auth else exc.status_code) from None


# ---------------------------------------------------------------------------
# Publish, approval, status
# ---------------------------------------------------------------------------
def publish(db: Session, tenant_id: str, actor: str, actor_is_owner: bool, campaign_id: str, mode: str = "active") -> dict[str, Any]:
    from app.services.campaign_service import approval_decision

    c = _campaign(db, tenant_id, campaign_id, lock=True)
    platform = _platform_of(c) or ""
    if c.status != "draft":
        raise ConflictError(f"Only draft campaigns can be published (this one is {c.status}).")
    if _pc(c).get("pending_approval_id"):
        raise ConflictError("This campaign is already waiting for owner approval.")
    if _adapter(platform) is None:
        raise _not_built(platform)
    result = validate(db, tenant_id, campaign_id)
    if not result["ok"]:
        raise AppError("Fix these first: " + "; ".join(i["message"] for i in result["issues"] if i["severity"] == "error")[:900], 422)
    conn = _require_conn(db, tenant_id, platform)
    required, reason = approval_decision(db, c)
    if required and not actor_is_owner:
        label = PLATFORMS[platform]["label"]
        approval_id = db.execute(
            insert(_approval_queue).values(
                tenant_id=tenant_id, subject_type="campaign", subject_id=c.id, title=c.name[:255],
                summary=f"Publish {c.name} to {label} ({mode}): daily {format_money(c.daily_cap_cents, c.currency)}. Needs approval: {reason}.",
                payload={"campaign_id": str(c.id), "builder": True, "platform": platform, "mode": mode, "daily_cap_cents": c.daily_cap_cents,
                         "budget_cents": c.budget_cents, "currency": c.currency.strip(), "reason": reason},
                requested_by_type="human", requested_by=actor,
            ).returning(_approval_queue.c.id)
        ).scalar_one()
        _set_pc(c, pending_approval_id=str(approval_id), pending_mode=mode)
        _audit(db, tenant_id, actor, "campaign.submit_for_approval", "campaign", c.id, {"approval_id": str(approval_id), "reason": reason, "platform": platform})
        db.refresh(c)
        return tree(db, c)
    try:
        _go_live(db, c, conn, mode, actor if actor_is_owner else None)
    except PlatformError as exc:
        _record_failure(db, tenant_id, actor, campaign_id, platform, exc)
        raise AppError(f"{exc.path + ': ' if exc.path else ''}{exc.message}", 409 if exc.auth else exc.status_code) from None
    _audit(db, tenant_id, actor, "campaign.published", "campaign", c.id,
           {"platform": platform, "mode": mode, "external_campaign_id": _pc(c).get("external_id"), "approval_rule": reason})
    db.refresh(c)
    return tree(db, c)


def _go_live(db: Session, c: Campaign, conn: dict[str, Any], mode: str, approver: str | None) -> None:
    """Platform objects first (the adapter rolls them back on failure), then
    our rows; no commit (the caller's audit commits)."""
    platform = _platform_of(c) or ""
    adapter = _adapter(platform)
    if adapter is None:
        raise PlatformError(f"Publishing to {PLATFORMS[platform]['label']} isn't available yet.", 501)
    ids: dict[str, Any] = adapter.publish(conn, adapter_tree(db, c), mode)
    now = datetime.now(timezone.utc)
    groups = _groups(c)
    future = any((_utc(_gf(g).get("starts_at")) or c.starts_at or now) > now for g in groups)
    new_status = "paused" if mode == "paused" else ("scheduled" if future else "running")
    for g in groups:
        g.external_id = (ids.get("groups") or {}).get(str(g.id))
        g.status = new_status
        for ad in _ads(g):
            ad.external_ad_id = (ids.get("ads") or {}).get(str(ad.id))
            ad.external_url = ids.get("url")
            ad.status = new_status
    _set_pc(c, external_id=ids.get("campaign"), url=ids.get("url"), published_at=now.isoformat(), last_error=None,
            pending_approval_id=None, pending_mode=None)
    c.status = new_status
    c.launched_at = now
    if mode == "paused":
        c.paused_at = now
    if approver:
        c.owner_approved_at = now
        c.owner_approved_by = approver


def _record_failure(db: Session, tenant_id: str, actor: str | None, campaign_id: str, platform: str, exc: PlatformError) -> None:
    db.rollback()
    if exc.auth:
        integration_service.mark_ad_platform_expired(db, tenant_id, PLATFORMS[platform]["provider"], exc.message)
    c = db.query(Campaign).filter(Campaign.tenant_id == tenant_id, Campaign.id == campaign_id).first()
    if c is not None:
        _set_pc(c, last_error=f"{exc.path + ': ' if exc.path else ''}{exc.message}"[:400])
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor, action="campaign.publish_failed", resource_type="campaign",
                    resource_id=campaign_id, metadata={"platform": platform, "error": exc.message[:300], "path": exc.path, "auth": exc.auth})


def apply_approval_decision(db: Session, tenant_id: str, approval_id: str, c: Campaign, decider: str, decision: str) -> None:
    """Owner decision on a platform publish (SPEC-BE-047 rule). A publishing
    error keeps the approval approved and leaves the draft with last_error,
    as the Meta builder does."""
    pc = _pc(c)
    if c.status != "draft" or pc.get("pending_approval_id") != approval_id:
        return
    if decision != "approved":
        _set_pc(c, pending_approval_id=None, pending_mode=None)
        return
    platform = _platform_of(c) or ""
    conn = _conn(db, tenant_id, platform)
    if conn is None or conn["status"] != "connected":
        _set_pc(c, pending_approval_id=None, last_error=f"{PLATFORMS[platform]['label']} isn't connected; reconnect and publish again.")
        return
    try:
        with db.begin_nested():
            _go_live(db, c, conn, pc.get("pending_mode") or "active", decider)
    except PlatformError as exc:
        _set_pc(c, pending_approval_id=None, last_error=f"{exc.path + ': ' if exc.path else ''}{exc.message}"[:400])
        if exc.auth:
            integration_service.mark_ad_platform_expired(db, tenant_id, PLATFORMS[platform]["provider"], exc.message)


def set_status(db: Session, tenant_id: str, actor: str, level: str, object_id: str, resume: bool) -> dict[str, Any]:
    """Pause/resume one level, on the platform first, then here."""
    row: Campaign | AdGroup | Ad
    if level == "campaign":
        c = _campaign(db, tenant_id, object_id, lock=True)
        row, external = c, _pc(c).get("external_id")
    elif level == "group":
        g, c = _group(db, tenant_id, object_id)
        row, external = g, g.external_id
    else:
        ad, _, c = _ad(db, tenant_id, object_id)
        row, external = ad, ad.external_ad_id
    platform = _platform_of(c) or ""
    what = PLATFORMS[platform]["hierarchy"][level].lower()
    if not external:
        raise ConflictError(f"This {what} isn't published on {PLATFORMS[platform]['label']}.")
    if not resume and row.status not in ("running", "scheduled"):
        raise ConflictError(f"Only a running or scheduled {what} can be paused.")
    if resume and row.status != "paused":
        raise ConflictError(f"Only a paused {what} can be resumed.")
    adapter = _adapter(platform)
    if adapter is None:
        raise _not_built(platform)
    conn = _require_conn(db, tenant_id, platform)
    _call(db, tenant_id, platform, adapter.set_status, conn, level, external, resume)
    now = datetime.now(timezone.utc)
    row.status = "running" if resume else "paused"
    if isinstance(row, Campaign):
        row.paused_at = None if resume else now
        # Published children follow the campaign, as campaign_service does for Meta.
        for g in _groups(row):
            if g.external_id:
                g.status = row.status
            for ad in _ads(g):
                if ad.external_ad_id:
                    ad.status = row.status
    if isinstance(row, AdGroup):
        for ad in _ads(row):
            if ad.external_ad_id:
                ad.status = row.status
    _audit(db, tenant_id, actor, f"ads_builder.{level}_{'resumed' if resume else 'paused'}",
           {"campaign": "campaign", "group": "ad_group", "ad": "ad"}[level], row.id, {"platform": platform, "external_id": external})
    return {"id": str(row.id), "name": row.name, "level": level, "status": row.status}


# ---------------------------------------------------------------------------
# Results import (SPEC-BE-062/063..068): daily campaign-level results into
# analytics_events, like Meta's (SPEC-BE-056) but per campaign, because every
# platform reports at that level. Rows: source = the platform (YouTube is
# 'google', the account it runs in), event_type 'platform_insights',
# entity 'campaign' = our campaigns.id, event_time = that day 00:00 UTC, one
# row per metric. Each import deletes the campaign's rows in the window and
# re-inserts them (idempotent; platforms revise recent days). Metric names
# match Meta's so reports read one set: spend_cents, impressions, clicks,
# link_clicks (= platform clicks), purchases / leads / app_installs (by the
# campaign's objective), purchase_value_cents. A metric the platform didn't
# report is left out, never 0.
# ---------------------------------------------------------------------------
RESULTS_THROTTLE = timedelta(minutes=5)
REIMPORT_DAYS = 3
MAX_IMPORT_DAYS = 90
_events = table(
    "analytics_events",
    column("tenant_id"), column("event_time"), column("event_type"), column("entity_type"), column("entity_id"),
    column("metric"), column("value"), column("dimensions", JSONB), column("source"),
)
CONVERSION_METRIC = {"conversions": "purchases", "leads": "leads", "app_promotion": "app_installs"}


def _source(platform: str) -> str:
    return "google" if platform == "youtube" else platform


def _record(db: Session, tenant_id: str, provider: str) -> Any:
    from app.models.integration import Integration

    return (
        db.query(Integration)
        .filter(Integration.tenant_id == tenant_id, Integration.provider == provider, Integration.status != "disconnected")
        .order_by(Integration.updated_at.desc())
        .first()
    )


def _metrics(row: dict[str, Any], objective: str) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    if row.get("spend") is not None:
        out["spend_cents"] = (Decimal(str(row["spend"])) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if row.get("impressions") is not None:
        out["impressions"] = Decimal(str(row["impressions"]))
    if row.get("clicks") is not None:
        out["clicks"] = out["link_clicks"] = Decimal(str(row["clicks"]))
    metric = CONVERSION_METRIC.get(objective)
    if metric and row.get("conversions") is not None:
        out[metric] = Decimal(str(row["conversions"]))
    if row.get("conversion_value") is not None:
        out["purchase_value_cents"] = (Decimal(str(row["conversion_value"])) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return out


def _import(db: Session, platform: str, conn: dict[str, Any], campaigns: list[Campaign], today: Any) -> int:
    from sqlalchemy import delete
    from sqlalchemy import text as sql_text

    adapter = _adapter(platform)
    if adapter is None or not callable(getattr(adapter, "import_results", None)):
        raise PlatformError(f"Results import for {PLATFORMS[platform]['label']} isn't available yet.", 501)
    by_external = {str(_pc(c)["external_id"]): c for c in campaigns}
    starts = []
    for c in campaigns:
        pc = _pc(c)
        published = datetime.fromisoformat(pc["published_at"]).date() if pc.get("published_at") else today
        last = datetime.fromisoformat(pc["insights_until"]).date() if pc.get("insights_until") else None
        since = min(today - timedelta(days=REIMPORT_DAYS - 1), (last + timedelta(days=1)) if last else published)
        starts.append(max(since, published, today - timedelta(days=MAX_IMPORT_DAYS - 1)))
    since = min(starts)
    rows = adapter.import_results(conn, list(by_external), since.isoformat(), today.isoformat())
    window_start = datetime.combine(since, datetime.min.time(), timezone.utc)
    window_end = datetime.combine(today + timedelta(days=1), datetime.min.time(), timezone.utc)
    source = _source(platform)
    db.execute(delete(_events).where(
        _events.c.tenant_id == campaigns[0].tenant_id, _events.c.source == source, _events.c.entity_type == "campaign",
        _events.c.entity_id.in_([c.id for c in campaigns]), _events.c.event_time >= window_start, _events.c.event_time < window_end,
    ))
    written = 0
    for row in rows:
        found = by_external.get(str(row.get("campaign_id")))
        if found is None or not row.get("date"):
            continue
        c = found
        day = datetime.fromisoformat(str(row["date"])[:10]).date()
        when = datetime.combine(day, datetime.min.time(), timezone.utc)
        dims = {"campaign_id": str(c.id), "platform": platform, "external_campaign_id": str(row["campaign_id"]),
                "date": day.isoformat(), "currency": c.currency.strip()}
        for metric, value in _metrics(row, c.objective).items():
            db.execute(_events.insert().values(tenant_id=c.tenant_id, event_time=when, event_type="platform_insights", entity_type="campaign",
                                               entity_id=c.id, metric=metric, value=value, dimensions=dims, source=source))
            written += 1
    for c in campaigns:
        c.spent_cents = int(db.execute(
            sql_text("SELECT COALESCE(SUM(value), 0) FROM analytics_events WHERE tenant_id = :t AND source = :s "
                     "AND metric = 'spend_cents' AND entity_type = 'campaign' AND entity_id = :c"),
            {"t": c.tenant_id, "s": source, "c": c.id},
        ).scalar_one())
        _set_pc(c, insights_until=today.isoformat())
    return written


def sync_results(db: Session, tenant_id: str, actor: str | None, campaign_id: str | None = None, manual: bool = True) -> dict[str, Any]:
    """Imports results for one or all published platform campaigns, per
    platform connection. A manual sync is throttled to one per 5 minutes per
    connection; the scheduler's isn't."""
    from app.services.campaign_service import _campaign_kpis
    from app.workflow_engine.dispatcher import fire

    now = datetime.now(timezone.utc)
    today = now.date()
    query = db.query(Campaign).filter(Campaign.tenant_id == tenant_id)
    if campaign_id:
        query = query.filter(Campaign.id == campaign_id)
    campaigns = [
        c for c in query.all()
        if is_platform_campaign(c) and _pc(c).get("external_id")
        and (c.status in ("running", "scheduled", "paused") or (c.ends_at and c.ends_at >= now - timedelta(days=30)))
    ]
    if campaign_id and not campaigns:
        raise NotFoundError("Campaign not found or not published on its platform.")
    # Grouped by connection: Google Ads and YouTube share google_ads, so they
    # share one throttle and are imported together.
    by_provider: dict[str, dict[str, list[Campaign]]] = {}
    for c in campaigns:
        platform = _platform_of(c) or ""
        by_provider.setdefault(PLATFORMS[platform]["provider"], {}).setdefault(platform, []).append(c)
    by_platform = {p: g for platforms in by_provider.values() for p, g in platforms.items()}
    errors: list[dict[str, Any]] = []
    synced = rows = 0
    for provider, platforms in by_provider.items():
        label = " / ".join(PLATFORMS[p]["label"] for p in platforms)
        record = _record(db, tenant_id, provider)
        state = dict(((record.extra_metadata or {}) if record else {}).get("insights_sync") or {})
        if manual and state.get("last_manual_at") and now - datetime.fromisoformat(state["last_manual_at"]) < RESULTS_THROTTLE:
            wait = int((RESULTS_THROTTLE - (now - datetime.fromisoformat(state["last_manual_at"]))).total_seconds())
            errors.append({"campaign_id": None, "message": f"{label} results were synced moments ago; try again in {wait // 60}m {wait % 60}s.", "at": now.isoformat()})
            continue
        conn = _conn(db, tenant_id, next(iter(platforms)))
        if conn is None or conn["status"] != "connected":
            errors.append({"campaign_id": None, "message": f"Connect {label} in Integrations to import results.", "at": now.isoformat()})
            continue
        for platform, group in platforms.items():
            try:
                with db.begin_nested():
                    rows += _import(db, platform, conn, group, today)
                synced += len(group)
                if record is not None:
                    state.update(last_success_at=now.isoformat(), campaigns=len(group))
                    record.last_sync_at = now
                    record.last_error = None
            except PlatformError as exc:
                errors.append({"campaign_id": None, "message": exc.message, "at": now.isoformat()})
                if exc.auth:
                    integration_service.mark_ad_platform_expired(db, tenant_id, provider, exc.message)
                elif record is not None:
                    record.last_error = exc.message[:300]
        if record is not None:
            if manual:
                state["last_manual_at"] = now.isoformat()
            record.extra_metadata = {**(record.extra_metadata or {}), "insights_sync": state}
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor,
                    action="ads_builder.results_failed" if errors and not synced else "ads_builder.results_synced",
                    resource_type="campaign", resource_id=campaign_id,
                    metadata={"campaigns": synced, "rows": rows, "errors": len(errors), "platforms": sorted(by_platform)})
    # Live trigger ad_threshold_crossed (SPEC-BE-060), as for Meta.
    for c in campaigns:
        fire(db, tenant_id, "ad_threshold_crossed", {"campaign": {"id": str(c.id), "name": c.name, **_campaign_kpis(db, tenant_id, str(c.id), 7)}})
    return {"synced_campaigns": synced, "rows_written": rows, "last_sync_at": now, "errors": errors}


def sync_all_results() -> int:
    """Scheduler job (every 3 hours, with Meta's): every tenant with a
    published platform campaign and a connected platform."""
    from app.db.session import SessionLocal
    from app.models.integration import Integration

    providers = sorted({p["provider"] for k, p in PLATFORMS.items() if k != "meta"})
    done = 0
    db = SessionLocal()
    try:
        tenants = [t for (t,) in db.query(Integration.tenant_id).filter(Integration.provider.in_(providers), Integration.status == "connected").distinct()]
        for tenant_id in tenants:
            try:
                result = sync_results(db, str(tenant_id), None, manual=False)
                done += 1 if result["synced_campaigns"] else 0
            except AppError as exc:
                db.rollback()
                logger.warning("platform_results_scheduled_failed", tenant_id=str(tenant_id), error=exc.detail)
    finally:
        db.close()
    return done
