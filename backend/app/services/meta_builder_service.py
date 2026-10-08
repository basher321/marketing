"""Meta Ads Manager-style builder: Campaign -> Ad sets -> Ads (SPEC-BE-055).

Drafts live in our DB only (Meta's API has no draft object):
- campaign: the `campaigns` row + metadata.builder (campaign-level settings);
- ad set: an `ad_groups` row (targeting, budget, bid, external_id) + its
  metadata (schedule, goal, placements, promoted object, effective status);
- ad: an `ads` row + metadata (identity, format, media, text, CTA, destination,
  tracking, creative id, effective status).

Publishing creates everything on Meta through integrations/meta_ads.py in the
order campaign -> each ad set -> each ad's creative -> ad. The campaign is
created PAUSED and only switched ACTIVE at the end (mode "active"); any Meta
failure deletes what was created and rolls the DB back (502 + the failing
path). The SPEC-BE-047 spend-cap approval rule runs first: a non-owner's
over-cap publish becomes a `campaign` approval item; only the owner approves.

campaigns.budget_cents / daily_cap_cents / starts_at / ends_at / channels are
kept as roll-ups of the tree, so lists, analytics and the cap rule keep working.
"""
import copy
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import structlog
from sqlalchemy import column, insert, table
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.integrations import meta_ads
from app.models.campaign import Ad, AdGroup, Campaign
from app.models.tenant import Tenant
from app.schemas import meta as s
from app.services import integration_service
from app.utils.locale_data import format_money

logger = structlog.get_logger(__name__)

MAX_AD_SETS = 10
MAX_ADS = 10
IMAGE_MAX = 30 * 1024 * 1024
VIDEO_MAX = 1024 * 1024 * 1024
STATUS_CACHE = timedelta(seconds=60)

_approval_queue = table(
    "approval_queue",
    column("id"), column("tenant_id"), column("subject_type"), column("subject_id"), column("title"),
    column("summary"), column("payload", JSONB), column("requested_by_type"), column("requested_by"),
)


class PublishError(AppError):
    def __init__(self, detail: str, status_code: int, path: str | None = None, expired: bool = False):
        super().__init__(detail, status_code)
        self.path = path
        self.expired = expired


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _cents(amount: Decimal | float | None) -> int | None:
    if amount is None:
        return None
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


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


def _builder(c: Campaign) -> dict[str, Any]:
    return dict((c.extra_metadata or {}).get("builder") or {})


def _set_meta_key(c: Campaign, key: str, values: dict[str, Any]) -> None:
    meta = dict(c.extra_metadata or {})
    meta[key] = {**dict(meta.get(key) or {}), **values}
    c.extra_metadata = meta


def _md(row: AdGroup | Ad) -> dict[str, Any]:
    return dict(row.extra_metadata or {})


def _set_md(row: AdGroup | Ad, **values: Any) -> None:
    row.extra_metadata = {**_md(row), **values}


def _objective_key(c: Campaign) -> str:
    return meta_ads.STORED_TO_BUILDER.get(c.objective, "traffic")


def _conn(db: Session, tenant_id: str, required: bool = True) -> dict[str, str] | None:
    conn = integration_service.meta_publish_credentials(db, tenant_id)
    if conn is None or not conn.get("access_token"):
        if required:
            raise ConflictError("Connect Meta in Integrations to use the campaign builder's Meta features.")
        return None
    if conn["status"] != "connected":
        if required:
            raise ConflictError("Reconnect Meta in Integrations; the connection has expired or failed.")
        return None
    if required and not conn["ad_account_id"]:
        raise ConflictError("Choose a Meta ad account in Integrations.")
    return conn


def _client(conn: dict[str, str]) -> meta_ads.MetaClient:
    return meta_ads.MetaClient(conn["access_token"])


def _meta_call(db: Session, tenant_id: str, fn: Any, *args: Any) -> Any:
    """One Meta call with SPEC-BE-055 rule 9 error classes."""
    try:
        return fn(*args)
    except meta_ads.MetaError as exc:
        kind, status, message = meta_ads.classify(exc)
        if kind == "auth":
            integration_service.mark_meta_expired(db, tenant_id, exc.message)
            db.commit()
        raise AppError(message, status) from None


def _campaign(db: Session, tenant_id: str, campaign_id: str, lock: bool = False) -> Campaign:
    query = db.query(Campaign).filter(Campaign.tenant_id == tenant_id, Campaign.id == campaign_id)
    if lock:
        query = query.with_for_update()
    try:
        campaign = query.first()
    except Exception:
        db.rollback()
        campaign = None
    # A campaign built for another ad platform (SPEC-BE-062) is not Meta's.
    if campaign is None or "builder" not in (campaign.extra_metadata or {}) or (campaign.extra_metadata or {}).get("platform") not in (None, "meta"):
        raise NotFoundError("Campaign not found.")
    return campaign


def _ad_set(db: Session, tenant_id: str, ad_set_id: str) -> AdGroup:
    row = db.query(AdGroup).filter(AdGroup.tenant_id == tenant_id, AdGroup.id == ad_set_id).first()
    if row is None or (row.campaign.extra_metadata or {}).get("platform") not in (None, "meta"):
        raise NotFoundError("Ad set not found.")
    return row


def _ad(db: Session, tenant_id: str, ad_id: str) -> Ad:
    row = db.query(Ad).filter(Ad.tenant_id == tenant_id, Ad.id == ad_id).first()
    if row is None or (row.ad_group.campaign.extra_metadata or {}).get("platform") not in (None, "meta"):
        raise NotFoundError("Ad not found.")
    return row


def _tenant(db: Session, tenant_id: str) -> Tenant:
    return db.query(Tenant).filter(Tenant.id == tenant_id).one()


# ---------------------------------------------------------------------------
# Lookups (pickers)
# ---------------------------------------------------------------------------
def objectives(db: Session, tenant_id: str) -> dict[str, Any]:
    conn = _conn(db, tenant_id, required=False)
    apps: list[dict[str, Any]] | None = None
    if conn and conn["ad_account_id"]:
        try:
            apps = _client(conn).advertisable_apps(conn["ad_account_id"])
        except meta_ads.MetaError:
            apps = None
    items = []
    for key, rule in meta_ads.BUILDER_OBJECTIVES.items():
        available, reason = True, None
        if key == "app_promotion" and apps is not None and not apps:
            available, reason = False, "No app is registered to your Meta ad account (Business Settings › Apps)."
        if conn is None:
            reason = reason or "Connect Meta to publish; you can still build a draft."
        items.append(
            {
                "key": key, "label": rule["label"], "description": rule["description"], "meta_objective": rule["meta"],
                "available": available, "reason": reason, "conversion_locations": rule["locations"],
                "unavailable_locations": meta_ads.UNAVAILABLE_LOCATIONS if key in ("traffic", "engagement", "leads", "sales") else {},
            }
        )
    return {
        "objectives": items,
        "bid_strategies": list(meta_ads.BID_STRATEGIES),
        "special_ad_categories": list(meta_ads.SPECIAL_AD_CATEGORIES),
        "placements": meta_ads.PLACEMENT_POSITIONS,
        "calls_to_action": list(meta_ads.CALLS_TO_ACTION),
        "event_types": list(meta_ads.EVENT_TYPES),
        "preview_formats": list(meta_ads.PREVIEW_FORMATS),
        "connection": {
            "connected": conn is not None,
            "ad_account_id": conn["ad_account_id"] if conn else None,
            "page_id": conn["page_id"] if conn else None,
            "instagram_id": conn["instagram_id"] if conn else None,
            "pixel_id": conn["pixel_id"] if conn else None,
        },
    }


SEARCH_TYPES = {"adgeolocation", "adinterest", "adlocale", "adTargetingCategory"}


def targeting_search(db: Session, tenant_id: str, kind: str, query: str) -> list[dict[str, Any]]:
    if kind not in SEARCH_TYPES:
        raise AppError("Unknown search type.", 422)
    conn = _conn(db, tenant_id)
    assert conn is not None
    extra: dict[str, Any] = {}
    if kind == "adgeolocation":
        extra["location_types"] = ["country", "region", "city", "zip"]
    if kind == "adTargetingCategory":
        extra["class"] = "behaviors"
    client = _client(conn)
    hits = _meta_call(db, tenant_id, lambda: client.search(kind, query, **extra))
    return [
        {
            "id": str(h.get("key") or h.get("id")),
            "name": str(h.get("name") or ""),
            "type": h.get("type") or ("interest" if kind == "adinterest" else "locale" if kind == "adlocale" else None),
            "extra": {k: h[k] for k in ("country_code", "region", "audience_size_lower_bound", "audience_size_upper_bound", "path") if k in h},
        }
        for h in hits
    ]


def custom_audiences(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    conn = _conn(db, tenant_id)
    assert conn is not None
    rows = _meta_call(db, tenant_id, _client(conn).custom_audiences, conn["ad_account_id"])
    return [{"id": str(r["id"]), "name": r.get("name", ""), "type": r.get("subtype"),
             "extra": {"approximate_count": r.get("approximate_count_lower_bound")}} for r in rows]


def apps(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    conn = _conn(db, tenant_id)
    assert conn is not None
    rows = _meta_call(db, tenant_id, _client(conn).advertisable_apps, conn["ad_account_id"])
    return [{"id": str(r["id"]), "name": r.get("name", ""), "type": "app", "extra": {"object_store_urls": r.get("object_store_urls") or {}}} for r in rows]


def lead_forms(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    conn = _conn(db, tenant_id)
    assert conn is not None
    if not conn["page_id"]:
        raise ConflictError("Choose a Facebook Page in Integrations.")
    rows = _meta_call(db, tenant_id, _client(conn).lead_forms, conn["page_id"])
    return [{"id": str(r["id"]), "name": r.get("name", ""), "type": r.get("status")} for r in rows]


# --- ad setup lookups (SPEC-BE-082) ----------------------------------------
def product_sets(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    conn = _conn(db, tenant_id)
    assert conn is not None
    rows = _meta_call(db, tenant_id, _client(conn).product_sets, conn["ad_account_id"])
    return [{"id": str(r["id"]), "name": r.get("name") or "", "catalog_id": str(r["catalog_id"]),
             "catalog_name": r.get("catalog_name") or "", "product_count": r.get("product_count")} for r in rows]


def _next_cursor(body: dict[str, Any]) -> str | None:
    # Graph sends paging.next only when there is another page.
    paging = body.get("paging") or {}
    return (paging.get("cursors") or {}).get("after") if paging.get("next") else None


def posts(db: Session, tenant_id: str, platform: str, after: str | None) -> dict[str, Any]:
    """Posts usable as an ad: the Page's published posts, or the Instagram account's media."""
    conn = _conn(db, tenant_id)
    assert conn is not None
    client = _client(conn)
    if platform == "instagram":
        if not conn["instagram_id"]:
            raise ConflictError("Connect an Instagram account to the Page in Integrations.")
        body = _meta_call(db, tenant_id, client.instagram_posts, conn["instagram_id"], after)
        items = [{"platform": "instagram", "id": str(r["id"]), "message": r.get("caption") or "",
                  # A video's media_url is the video file; its still is thumbnail_url.
                  "picture": r.get("thumbnail_url") if r.get("media_type") == "VIDEO" else r.get("media_url"),
                  "permalink_url": r.get("permalink"), "created_time": r.get("timestamp")} for r in body.get("data") or []]
    else:
        if not conn["page_id"]:
            raise ConflictError("Choose a Facebook Page in Integrations.")
        body = _meta_call(db, tenant_id, client.page_posts, conn["page_id"], after)
        items = [{"platform": "facebook", "id": str(r["id"]), "message": r.get("message") or "", "picture": r.get("full_picture"),
                  "permalink_url": r.get("permalink_url"), "created_time": r.get("created_time")} for r in body.get("data") or []]
    return {"items": items, "next_cursor": _next_cursor(body)}


def create_post(db: Session, tenant_id: str, actor: str, payload: s.PostCreate) -> dict[str, Any]:
    """Publishes a new post on the connected Facebook Page (always public, user decision)."""
    conn = _conn(db, tenant_id)
    assert conn is not None
    if not conn["page_id"]:
        raise ConflictError("Choose a Facebook Page in Integrations.")
    post_id = _meta_call(db, tenant_id, _client(conn).create_page_post, conn["page_id"], payload.message, payload.link, payload.image_url)
    _audit(db, tenant_id, actor, "meta.page_post_created", "integration", conn["integration_id"],
           {"post_id": post_id, "has_image": bool(payload.image_url), "has_link": bool(payload.link)})
    return {"platform": "facebook", "id": post_id, "message": payload.message, "picture": payload.image_url,
            "permalink_url": f"https://www.facebook.com/{post_id}", "created_time": datetime.now(timezone.utc).isoformat()}


def pixels(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    conn = _conn(db, tenant_id)
    assert conn is not None
    rows = _meta_call(db, tenant_id, _client(conn).list_pixels, conn["ad_account_id"])
    return [{"id": str(r["id"]), "name": r.get("name", ""), "type": "pixel"} for r in rows]


def reach_estimate(db: Session, tenant_id: str, payload: s.ReachRequest) -> dict[str, Any]:
    conn = _conn(db, tenant_id, required=False)
    if conn is None or not conn["ad_account_id"]:
        return {"available": False, "reason": "Connect Meta to see an estimate."}
    spec = meta_targeting(payload.targeting.model_dump(), (payload.placements or s.Placements()).model_dump())
    try:
        data = _client(conn).delivery_estimate(conn["ad_account_id"], spec, payload.optimization_goal)
    except meta_ads.MetaError as exc:
        # Best-effort: never a fake number.
        return {"available": False, "reason": f"Meta: {exc.message}"}
    curve = data.get("daily_outcomes_curve") or []
    reach = [int(p.get("reach") or 0) for p in curve if isinstance(p, dict)]
    lower = data.get("estimate_mau_lower_bound")
    upper = data.get("estimate_mau_upper_bound")
    if reach:
        lower, upper = min(reach), max(reach)
    if lower is None and upper is None:
        return {"available": False, "reason": "Meta didn't return an estimate for this audience."}
    return {"available": True, "daily_reach_lower": lower, "daily_reach_upper": upper}


def _kind_of(content: bytes) -> str | None:
    # Magic bytes, never the file name (SPEC-BE-055 acceptance 10).
    if content[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if content[4:8] == b"ftyp":
        return "video/mp4" if content[8:10] != b"qt" else "video/quicktime"
    if content[4:8] in (b"moov", b"mdat", b"wide", b"free"):
        return "video/quicktime"
    return None


def upload_media(db: Session, tenant_id: str, actor_user_id: str, filename: str, content: bytes) -> dict[str, Any]:
    kind = _kind_of(content)
    if kind is None:
        raise AppError("Upload a JPG or PNG image, or an MP4/MOV video.", 422)
    is_image = kind.startswith("image/")
    if len(content) > (IMAGE_MAX if is_image else VIDEO_MAX):
        raise AppError("The image can be at most 30 MB." if is_image else "The video can be at most 1 GB.", 413)
    conn = _conn(db, tenant_id)
    assert conn is not None
    client = _client(conn)
    name = (filename or ("image" if is_image else "video"))[:200]
    if is_image:
        res = _meta_call(db, tenant_id, client.upload_image, conn["ad_account_id"], name, content)
        result = {"type": "image", "image_hash": res["image_hash"], "thumbnail_url": res.get("url"), "status": "ready", "name": name}
    else:
        video_id = _meta_call(db, tenant_id, client.upload_video, conn["ad_account_id"], name, content)
        result = {"type": "video", "video_id": video_id, "thumbnail_url": None, "status": "processing", "name": name}
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor_user_id, action="meta.media_uploaded",
                    resource_type="integration", resource_id=conn["integration_id"],
                    metadata={"type": result["type"], "bytes": len(content), "name": name})
    return result


def video_status(db: Session, tenant_id: str, video_id: str) -> dict[str, Any]:
    conn = _conn(db, tenant_id)
    assert conn is not None
    res = _meta_call(db, tenant_id, _client(conn).video_status, video_id)
    return {"type": "video", "video_id": video_id, "thumbnail_url": res.get("thumbnail_url"), "status": res["status"], "name": ""}


# ---------------------------------------------------------------------------
# Tree read
# ---------------------------------------------------------------------------
def _ad_dict(ad: Ad) -> dict[str, Any]:
    md = _md(ad)
    return {
        "id": str(ad.id), "name": ad.name, "status": ad.status, "external_ad_id": ad.external_ad_id,
        "effective_status": md.get("effective_status"), "review_feedback": md.get("review_feedback"),
        "last_error": md.get("last_error"), "format": md.get("format") or "image", "media": md.get("media") or [],
        "cards": [{"type": "image", **card} for card in md.get("cards") or []], "carousel_source": _carousel_source(md),
        "product_set": md.get("product_set"), "existing_post": md.get("existing_post"), "primary_text": md.get("primary_text") or "", "headline": md.get("headline") or "",
        "description": md.get("description") or "", "call_to_action": md.get("call_to_action") or "LEARN_MORE",
        "destination": md.get("destination") or {"type": "website"}, "url_tags": md.get("url_tags") or "",
        "use_instagram": bool(md.get("use_instagram", True)),
        "content_asset_id": str(ad.content_asset_id) if ad.content_asset_id else None,
    }


def _ad_set_dict(group: AdGroup) -> dict[str, Any]:
    md = _md(group)
    return {
        "id": str(group.id), "name": group.name, "status": group.status, "external_id": group.external_id,
        "effective_status": md.get("effective_status"), "last_error": md.get("last_error"),
        "conversion_location": md.get("conversion_location") or "website", "optimization_goal": md.get("optimization_goal"),
        "pixel_id": md.get("pixel_id"), "custom_event_type": md.get("custom_event_type"), "app_id": md.get("app_id"),
        "app_store_url": md.get("app_store_url"), "budget_type": md.get("budget_type") or "daily",
        "budget": _major(group.budget_cents), "bid_strategy": group.bid_strategy, "bid_amount": _major(md.get("bid_amount_cents")),
        "starts_at": _utc(md.get("starts_at")), "ends_at": _utc(md.get("ends_at")),
        "targeting": dict(group.targeting or {}), "placements": md.get("placements") or {"mode": "advantage"},
        "ads": [_ad_dict(a) for a in sorted(group.ads, key=lambda x: (x.created_at, str(x.id))) if a.tenant_id == group.tenant_id],
    }


def _groups(c: Campaign) -> list[AdGroup]:
    return sorted([g for g in c.ad_groups if g.tenant_id == c.tenant_id], key=lambda g: (g.created_at, str(g.id)))


def tree(db: Session, c: Campaign) -> dict[str, Any]:
    from app.services.campaign_service import approval_decision

    b = _builder(c)
    meta = dict((c.extra_metadata or {}).get("meta") or {})
    approval = None
    if c.budget_cents > 0 and c.starts_at:
        required, reason = approval_decision(db, c)
        approval = {"required": required, "reason": reason}
    published = bool(meta.get("campaign_id"))
    return {
        "campaign": {
            "id": str(c.id), "name": c.name, "objective": _objective_key(c), "status": c.status, "currency": c.currency.strip(),
            "special_ad_categories": b.get("special_ad_categories") or [], "special_ad_category_country": b.get("special_ad_category_country") or [],
            "buying_type": b.get("buying_type") or "AUCTION", "budget_mode": b.get("budget_mode") or "ad_set",
            "budget_type": b.get("budget_type") or "daily", "budget": _major(b.get("budget_cents")),
            "bid_strategy": b.get("bid_strategy") or "LOWEST_COST_WITHOUT_CAP", "bid_amount": _major(b.get("bid_amount_cents")),
            "roas_floor": b.get("roas_floor"), "spend_cap": _major(b.get("spend_cap_cents")), "spent": _major(c.spent_cents) or 0.0,
            "starts_at": _utc(c.starts_at), "ends_at": _utc(c.ends_at), "pending_approval_id": b.get("pending_approval_id"),
            "effective_status": meta.get("effective_status"),
        },
        "ad_sets": [_ad_set_dict(g) for g in _groups(c)],
        "missing": missing(db, c),
        "meta": {
            **{k: meta.get(k) for k in ("campaign_id", "ad_account_id", "published_at", "last_error", "effective_status", "last_status_sync")},
            "published": published,
            "ads_manager_url": meta_ads.ads_manager_url(meta["ad_account_id"], meta["campaign_id"]) if published else None,
        } if meta else None,
        "approval": approval,
    }


def get_tree(db: Session, tenant_id: str, campaign_id: str) -> dict[str, Any]:
    c = _campaign(db, tenant_id, campaign_id)
    meta = (c.extra_metadata or {}).get("meta") or {}
    last = _utc(meta.get("last_status_sync"))
    if meta.get("campaign_id") and (last is None or datetime.now(timezone.utc) - last > STATUS_CACHE):
        try:
            refresh_statuses(db, c)
            db.commit()
        except AppError:
            db.rollback()
            c = _campaign(db, tenant_id, campaign_id)
    return tree(db, c)


# ---------------------------------------------------------------------------
# Missing / local validation
# ---------------------------------------------------------------------------
def _issue(level: str, row_id: Any, field: str, message: str) -> dict[str, Any]:
    return {"level": level, "id": str(row_id) if row_id else None, "field": field, "message": message, "source": "local"}


def missing(db: Session, c: Campaign) -> list[dict[str, Any]]:
    b = _builder(c)
    out: list[dict[str, Any]] = []
    key = _objective_key(c)
    rule = meta_ads.BUILDER_OBJECTIVES[key]
    categories = b.get("special_ad_categories") or []
    if c.objective == "message_replies":
        out.append(_issue("campaign", c.id, "objective", "Messages campaigns aren't supported on Meta yet."))
    if categories and not b.get("special_ad_category_country"):
        out.append(_issue("campaign", c.id, "special_ad_category_country", "Choose the countries for the special ad category."))
    mode = b.get("budget_mode") or "ad_set"
    if mode == "campaign" and not b.get("budget_cents"):
        out.append(_issue("campaign", c.id, "budget", "Set the campaign budget."))
    strategy = b.get("bid_strategy") or "LOWEST_COST_WITHOUT_CAP"
    if mode == "campaign" and strategy in ("LOWEST_COST_WITH_BID_CAP", "COST_CAP") and not b.get("bid_amount_cents"):
        out.append(_issue("campaign", c.id, "bid_amount", "Set the bid cap / cost cap amount."))
    if mode == "campaign" and strategy == "LOWEST_COST_WITH_MIN_ROAS" and not b.get("roas_floor"):
        out.append(_issue("campaign", c.id, "roas_floor", "Set the minimum ROAS."))
    groups = _groups(c)
    if not groups:
        out.append(_issue("campaign", c.id, "ad_sets", "Add at least one ad set."))
    conn = integration_service.meta_publish_credentials(db, c.tenant_id) or {}
    for g in groups:
        md = _md(g)
        loc = md.get("conversion_location") or "website"
        goal = md.get("optimization_goal")
        if loc not in rule["locations"]:
            out.append(_issue("ad_set", g.id, "conversion_location", f"{rule['label']} campaigns can't use this conversion location."))
        elif goal not in rule["locations"][loc]:
            out.append(_issue("ad_set", g.id, "optimization_goal", "Choose a performance goal allowed for this objective and location."))
        if mode == "ad_set" and not g.budget_cents:
            out.append(_issue("ad_set", g.id, "budget", "Set the ad set budget."))
        budget_type = md.get("budget_type") if mode == "ad_set" else b.get("budget_type")
        if not md.get("starts_at"):
            out.append(_issue("ad_set", g.id, "starts_at", "Choose a start date."))
        if budget_type == "lifetime" and not md.get("ends_at"):
            out.append(_issue("ad_set", g.id, "ends_at", "A lifetime budget needs an end date."))
        if md.get("starts_at") and md.get("ends_at") and _utc(md["ends_at"]) <= _utc(md["starts_at"]):  # type: ignore[operator]
            out.append(_issue("ad_set", g.id, "ends_at", "The end must be after the start."))
        if mode == "ad_set" and g.bid_strategy in ("LOWEST_COST_WITH_BID_CAP", "COST_CAP") and not md.get("bid_amount_cents"):
            out.append(_issue("ad_set", g.id, "bid_amount", "Set the bid cap / cost cap amount."))
        t = dict(g.targeting or {})
        if not (t.get("countries") or t.get("regions") or t.get("cities") or t.get("zips")):
            out.append(_issue("ad_set", g.id, "targeting.locations", "Add at least one location."))
        if t.get("pending_terms"):
            out.append(_issue("ad_set", g.id, "targeting.detailed", "Pick these from Meta's list: " + ", ".join(t["pending_terms"])))
        if categories:
            if (t.get("age_min") or 18) != 18 or (t.get("age_max") or 65) != 65 or (t.get("genders") or "all") != "all":
                out.append(_issue("ad_set", g.id, "targeting.age", "Special ad categories can't target by age or gender."))
            if t.get("zips"):
                out.append(_issue("ad_set", g.id, "targeting.zips", "Special ad categories can't target zip codes."))
            if any((a.get("type") or "") == "lookalike" for a in t.get("custom_audiences") or []):
                out.append(_issue("ad_set", g.id, "targeting.custom_audiences", "Special ad categories can't use lookalike audiences."))
        needs_pixel = loc == "website" and goal in ("OFFSITE_CONVERSIONS", "VALUE")
        if needs_pixel and not (md.get("pixel_id") or conn.get("pixel_id")):
            out.append(_issue("ad_set", g.id, "pixel_id", "Select a Meta Pixel / dataset for conversion tracking."))
        if key == "app_promotion" or loc == "app":
            if not md.get("app_id") or not md.get("app_store_url"):
                out.append(_issue("ad_set", g.id, "app_id", "Choose the app and its store link."))
        placements = md.get("placements") or {}
        if placements.get("mode") == "manual" and not placements.get("platforms"):
            out.append(_issue("ad_set", g.id, "placements", "Choose at least one platform for manual placements."))
        ads = [a for a in g.ads if a.tenant_id == g.tenant_id]
        if not ads:
            out.append(_issue("ad_set", g.id, "ads", "Add at least one ad."))
        uses_ig = placements.get("mode") != "manual" or "instagram" in (placements.get("platforms") or [])
        for ad in ads:
            out.extend(_ad_missing(ad, key, loc, conn, uses_ig))
        # The ad set is promoted with one product set (SPEC-BE-082).
        if len({ps["id"] for a in ads if (ps := _ad_product_set(a))}) > 1:
            out.append(_issue("ad_set", g.id, "product_set", "All product-set ads in one ad set must use the same product set."))
    # ...and the campaign with one catalog.
    if len({ps["catalog_id"] for g in groups for a in g.ads if (ps := _ad_product_set(a))}) > 1:
        out.append(_issue("campaign", c.id, "product_set", "All product sets in one campaign must come from the same catalog."))
    return out


def _carousel_source(md: dict[str, Any]) -> str:
    return md.get("carousel_source") or "manual"


def _ad_product_set(ad: Ad) -> dict[str, Any] | None:
    """The product set an ad publishes with (only a product-set carousel has one)."""
    md = _md(ad)
    ps = md.get("product_set") or {}
    if md.get("format") == "carousel" and _carousel_source(md) == "product_set" and ps.get("id"):
        return dict(ps)
    return None


def _group_product_set(g: AdGroup) -> dict[str, Any] | None:
    return next((ps for a in g.ads if a.tenant_id == g.tenant_id and (ps := _ad_product_set(a))), None)


def _ad_missing(ad: Ad, objective: str, loc: str, conn: dict[str, Any], uses_ig: bool) -> list[dict[str, Any]]:
    md = _md(ad)
    out = []
    if not conn.get("page_id"):
        out.append(_issue("ad", ad.id, "identity", "Choose a Facebook Page in Integrations (ads run as a Page)."))
    if uses_ig and md.get("use_instagram", True) and not conn.get("instagram_id"):
        out.append(_issue("ad", ad.id, "identity.instagram", "Connect an Instagram account, or turn off Instagram for this ad."))
    fmt = md.get("format") or "image"
    media = md.get("media") or []
    if fmt == "image" and not (media and media[0].get("image_hash")):
        out.append(_issue("ad", ad.id, "media", "Upload an image."))
    if fmt == "video":
        if not (media and media[0].get("video_id")):
            out.append(_issue("ad", ad.id, "media", "Upload a video."))
        elif media[0].get("status") not in (None, "ready"):
            out.append(_issue("ad", ad.id, "media", "Video is still processing on Meta."))
    if fmt == "carousel" and _carousel_source(md) == "product_set":
        # SPEC-BE-082: Meta only fills cards from a catalog in a Sales campaign.
        if not (md.get("product_set") or {}).get("id"):
            out.append(_issue("ad", ad.id, "product_set", "Choose a product set."))
        if objective != "sales":
            out.append(_issue("ad", ad.id, "product_set", "Product-set carousels need a Sales campaign."))
    elif fmt == "carousel":
        cards = md.get("cards") or []
        if not 2 <= len(cards) <= 10:
            out.append(_issue("ad", ad.id, "cards", "A carousel needs 2 to 10 cards."))
        if any((card.get("type") or "image") == "video" and card.get("status") not in (None, "ready") for card in cards):
            out.append(_issue("ad", ad.id, "cards", "A card's video is still processing on Meta."))
    if fmt == "existing_post":
        # The post brings its own text, media and button: nothing else is required.
        post = md.get("existing_post") or {}
        if not post.get("id"):
            out.append(_issue("ad", ad.id, "existing_post", "Choose a post, or create one."))
        elif post.get("platform") == "instagram" and not conn.get("instagram_id"):
            out.append(_issue("ad", ad.id, "existing_post", "Connect the Instagram account in Integrations to use an Instagram post."))
        if loc in ("instant_form", "app") or objective == "app_promotion":
            out.append(_issue("ad", ad.id, "existing_post", "An existing post can't be used with an instant form or app destination."))
        return out
    if not (md.get("primary_text") or "").strip():
        out.append(_issue("ad", ad.id, "primary_text", "Write the primary text."))
    if fmt != "carousel" and not (md.get("headline") or "").strip() and objective != "awareness":
        out.append(_issue("ad", ad.id, "headline", "Write a headline."))
    dest = md.get("destination") or {}
    dtype = dest.get("type") or "website"
    if loc == "instant_form":
        if not dest.get("lead_form_id"):
            out.append(_issue("ad", ad.id, "destination.lead_form_id", "Choose an instant form."))
    elif loc == "app" or objective == "app_promotion":
        pass  # the ad set's app store link is the destination
    elif objective in ("traffic", "sales", "leads") and not dest.get("url"):
        out.append(_issue("ad", ad.id, "destination.url", "Add the website link (https)."))
    elif dtype == "website" and dest.get("url") is None and objective == "engagement":
        pass
    return out


# ---------------------------------------------------------------------------
# Create / edit
# ---------------------------------------------------------------------------
def _rollup(db: Session, c: Campaign) -> None:
    """campaigns.* summary columns from the tree (see module docstring)."""
    from zoneinfo import ZoneInfo

    b = _builder(c)
    groups = _groups(c)
    starts = [_utc(_md(g).get("starts_at")) for g in groups if _md(g).get("starts_at")]
    ends = [_utc(_md(g).get("ends_at")) for g in groups if _md(g).get("ends_at")]
    c.starts_at = min(starts) if starts else None  # type: ignore[type-var]
    c.ends_at = max(ends) if ends and len(ends) == len(groups) else None  # type: ignore[type-var]
    tz = ZoneInfo(_tenant(db, c.tenant_id).timezone or "UTC")

    def days(start: datetime | None, end: datetime | None) -> int | None:
        if not start or not end:
            return None
        return (end.astimezone(tz).date() - start.astimezone(tz).date()).days + 1

    daily = total = 0
    if (b.get("budget_mode") or "ad_set") == "campaign":
        amount = int(b.get("budget_cents") or 0)
        n = days(c.starts_at, c.ends_at)
        if b.get("budget_type") == "lifetime":
            total, daily = amount, (amount // n if n else amount)
        else:
            daily, total = amount, amount * (n or 1)
    else:
        for g in groups:
            md = _md(g)
            amount = int(g.budget_cents or 0)
            n = days(_utc(md.get("starts_at")), _utc(md.get("ends_at")))
            if md.get("budget_type") == "lifetime":
                total += amount
                daily += amount // n if n else amount
            else:
                daily += amount
                total += amount * (n or 1)
    c.budget_cents, c.daily_cap_cents = total, daily
    platforms: list[str] = []
    for g in groups:
        p = _md(g).get("placements") or {}
        chosen = p.get("platforms") if p.get("mode") == "manual" else ["facebook", "instagram"]
        for ch in chosen or []:
            if ch in ("facebook", "instagram", "messenger") and ch not in platforms:
                platforms.append(ch)
    c.channels = platforms


def _audit(db: Session, tenant_id: str, actor: str, action: str, resource_type: str, resource_id: Any, meta: dict[str, Any] | None = None) -> None:
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor, action=action, resource_type=resource_type,
                    resource_id=str(resource_id), metadata=meta or {})


def _apply_campaign(c: Campaign, payload: s.CampaignFields) -> list[str]:
    sent = payload.model_fields_set
    b = _builder(c)
    if "name" in sent and payload.name:
        c.name = payload.name.strip()
    if "objective" in sent and payload.objective:
        c.objective = meta_ads.BUILDER_OBJECTIVES[payload.objective]["stored"]
    simple = {"special_ad_categories": payload.special_ad_categories, "buying_type": payload.buying_type,
              "budget_mode": payload.budget_mode, "budget_type": payload.budget_type, "bid_strategy": payload.bid_strategy}
    for k, v in simple.items():
        if k in sent and v is not None:
            b[k] = v
    if "special_ad_category_country" in sent:
        b["special_ad_category_country"] = [x.strip().upper() for x in payload.special_ad_category_country or []]
    if "budget" in sent:
        b["budget_cents"] = _cents(payload.budget)
    if "bid_amount" in sent:
        b["bid_amount_cents"] = _cents(payload.bid_amount)
    if "roas_floor" in sent:
        b["roas_floor"] = float(payload.roas_floor) if payload.roas_floor else None
    if "spend_cap" in sent:
        b["spend_cap_cents"] = _cents(payload.spend_cap)
    _set_meta_key(c, "builder", b)
    return sorted(sent)


def create_campaign(db: Session, tenant_id: str, actor: str, payload: s.CampaignCreate, with_defaults: bool = True) -> dict[str, Any]:
    tenant = _tenant(db, tenant_id)
    c = Campaign(
        tenant_id=tenant_id, name=payload.name.strip(), objective=meta_ads.BUILDER_OBJECTIVES[payload.objective]["stored"],
        status="draft", channels=[], budget_cents=0, daily_cap_cents=0, spent_cents=0,
        currency=(tenant.currency or "USD").strip(), extra_metadata={"builder": {"buying_type": "AUCTION", "budget_mode": "ad_set", "budget_type": "daily", "bid_strategy": "LOWEST_COST_WITHOUT_CAP", "special_ad_categories": []}},
        created_by=actor,
    )
    db.add(c)
    db.flush()
    _apply_campaign(c, payload)
    if with_defaults:
        group = _new_ad_set(c, s.AdSetCreate(name=f"{c.name} — Ad set"[:255]))
        db.add(group)
        db.flush()
        db.add(_new_ad(group, s.AdCreate(name=f"{c.name} — Ad"[:255])))
        db.flush()
    db.refresh(c)
    _rollup(db, c)
    _audit(db, tenant_id, actor, "campaign.builder_created", "campaign", c.id, {"name": c.name, "objective": payload.objective})
    db.refresh(c)
    logger.info("campaign_builder_created", tenant_id=tenant_id, campaign_id=str(c.id))
    return tree(db, c)


def _published(c: Campaign) -> bool:
    return bool(((c.extra_metadata or {}).get("meta") or {}).get("campaign_id"))


LIVE_CAMPAIGN_FIELDS = {"name", "budget", "spend_cap", "bid_amount"}
LIVE_AD_SET_FIELDS = {"name", "budget", "ends_at", "bid_amount"}
LIVE_AD_FIELDS = {"name", "primary_text", "headline", "description", "call_to_action"}


def _live_guard(sent: set[str], allowed: set[str], what: str) -> None:
    bad = sorted(sent - allowed)
    if bad:
        raise ConflictError(f"On a published {what} only {', '.join(sorted(allowed))} can change; duplicate it to change {', '.join(bad)}.")


def update_campaign(db: Session, tenant_id: str, actor: str, campaign_id: str, payload: s.CampaignFields) -> dict[str, Any]:
    c = _campaign(db, tenant_id, campaign_id, lock=True)
    sent = set(payload.model_fields_set)
    if _published(c):
        _live_guard(sent, LIVE_CAMPAIGN_FIELDS, "campaign")
        b = _builder(c)
        values: dict[str, Any] = {}
        if "name" in sent and payload.name:
            values["name"] = payload.name
        if "budget" in sent and payload.budget and b.get("budget_mode") == "campaign":
            values["daily_budget" if b.get("budget_type") != "lifetime" else "lifetime_budget"] = meta_ads.to_meta_amount(_cents(payload.budget) or 0, c.currency)
        if "spend_cap" in sent and payload.spend_cap:
            values["spend_cap"] = meta_ads.to_meta_amount(_cents(payload.spend_cap) or 0, c.currency)
        if "bid_amount" in sent and payload.bid_amount and b.get("budget_mode") == "campaign":
            values["bid_amount"] = meta_ads.to_meta_amount(_cents(payload.bid_amount) or 0, c.currency)
        if values:
            conn = _conn(db, tenant_id)
            assert conn is not None
            _meta_call(db, tenant_id, _client(conn).post, (c.extra_metadata or {})["meta"]["campaign_id"], values)
    elif c.status != "draft":
        raise ConflictError(f"This campaign is {c.status}; it can't be edited.")
    changed = _apply_campaign(c, payload)
    _rollup(db, c)
    _audit(db, tenant_id, actor, "campaign.meta_updated" if _published(c) else "campaign.builder_updated", "campaign", c.id, {"fields": changed})
    db.refresh(c)
    return tree(db, c)


def _targeting_from_audience(db: Session, tenant_id: str, audience_id: str) -> dict[str, Any]:
    from app.services.audience_service import get_audience

    audience = get_audience(db, tenant_id, audience_id)
    if audience is None:
        raise NotFoundError("Audience not found.")
    t = dict(audience.targeting or {})
    genders = t.get("genders") or []
    pending = [*(t.get("interests") or []), *(t.get("regions") or [])]
    return {
        "countries": [c.upper() for c in t.get("countries") or []],
        "regions": [], "cities": [], "zips": [], "locales": [], "detailed": [], "custom_audiences": [], "excluded_custom_audiences": [],
        "age_min": int(t.get("age_min") or 18), "age_max": int(t.get("age_max") or 65),
        "genders": genders[0] if len(genders) == 1 else "all", "advantage_audience": False,
        # Names from a saved audience must be re-picked from Meta's search (they need Meta ids).
        "pending_terms": pending,
    }


def _apply_ad_set(db: Session, group: AdGroup, payload: s.AdSetFields) -> list[str]:
    sent = set(payload.model_fields_set)
    md = _md(group)
    if "name" in sent and payload.name:
        group.name = payload.name.strip()
    for k in ("conversion_location", "optimization_goal", "pixel_id", "custom_event_type", "app_id", "app_store_url", "budget_type"):
        if k in sent:
            md[k] = getattr(payload, k)
    if "budget" in sent:
        group.budget_cents = _cents(payload.budget)
    if "bid_strategy" in sent:
        group.bid_strategy = payload.bid_strategy
    if "bid_amount" in sent:
        md["bid_amount_cents"] = _cents(payload.bid_amount)
    if "starts_at" in sent:
        md["starts_at"] = _iso(payload.starts_at)
    if "ends_at" in sent:
        md["ends_at"] = _iso(payload.ends_at)
    if "placements" in sent and payload.placements is not None:
        md["placements"] = payload.placements.model_dump()
    if "targeting" in sent and payload.targeting is not None:
        group.targeting = payload.targeting.model_dump()
    if "audience_id" in sent and payload.audience_id:
        group.targeting = _targeting_from_audience(db, str(group.tenant_id), payload.audience_id)
        group.audience_id = payload.audience_id
    group.extra_metadata = md
    return sorted(sent)


def _default_goal(objective: str) -> tuple[str, str]:
    locations = meta_ads.BUILDER_OBJECTIVES[objective]["locations"]
    loc = next(iter(locations))
    return loc, locations[loc][0]


def _new_ad_set(c: Campaign, payload: s.AdSetFields) -> AdGroup:
    loc, goal = _default_goal(_objective_key(c))
    start = datetime.now(timezone.utc).replace(second=0, microsecond=0) + timedelta(hours=1)
    group = AdGroup(
        tenant_id=c.tenant_id, campaign_id=c.id, name=(payload.name or "New ad set")[:255], targeting=s.Targeting().model_dump(),
        bid_strategy="LOWEST_COST_WITHOUT_CAP", status="draft",
        extra_metadata={"conversion_location": loc, "optimization_goal": goal, "budget_type": "daily",
                        "starts_at": start.isoformat(), "placements": {"mode": "advantage"},
                        "custom_event_type": "PURCHASE" if _objective_key(c) == "sales" else ("LEAD" if _objective_key(c) == "leads" else None)},
    )
    return group


def add_ad_set(db: Session, tenant_id: str, actor: str, campaign_id: str, payload: s.AdSetCreate) -> dict[str, Any]:
    c = _campaign(db, tenant_id, campaign_id, lock=True)
    if c.status != "draft":
        raise ConflictError("Ad sets can only be added to a draft; duplicate the campaign instead.")
    if len(_groups(c)) >= MAX_AD_SETS:
        raise AppError(f"A campaign can have at most {MAX_AD_SETS} ad sets.", 422)
    group = _new_ad_set(c, payload)
    db.add(group)
    db.flush()
    _apply_ad_set(db, group, payload)
    db.add(_new_ad(group, s.AdCreate(name=f"{group.name} — Ad"[:255])))
    db.flush()
    db.refresh(c)
    _rollup(db, c)
    _audit(db, tenant_id, actor, "ad_set.created", "ad_group", group.id, {"campaign_id": str(c.id)})
    db.refresh(c)
    return tree(db, c)


def update_ad_set(db: Session, tenant_id: str, actor: str, ad_set_id: str, payload: s.AdSetFields) -> dict[str, Any]:
    group = _ad_set(db, tenant_id, ad_set_id)
    c = _campaign(db, tenant_id, str(group.campaign_id), lock=True)
    sent = set(payload.model_fields_set)
    if group.external_id:
        _live_guard(sent, LIVE_AD_SET_FIELDS, "ad set")
        values: dict[str, Any] = {}
        md = _md(group)
        if "name" in sent and payload.name:
            values["name"] = payload.name
        if "budget" in sent and payload.budget:
            values["lifetime_budget" if md.get("budget_type") == "lifetime" else "daily_budget"] = meta_ads.to_meta_amount(_cents(payload.budget) or 0, c.currency)
        if "ends_at" in sent and payload.ends_at:
            values["end_time"] = _iso(payload.ends_at)
        if "bid_amount" in sent and payload.bid_amount:
            values["bid_amount"] = meta_ads.to_meta_amount(_cents(payload.bid_amount) or 0, c.currency)
        if values:
            conn = _conn(db, tenant_id)
            assert conn is not None
            _meta_call(db, tenant_id, _client(conn).post, group.external_id, values)
    elif c.status != "draft":
        raise ConflictError(f"This campaign is {c.status}; it can't be edited.")
    changed = _apply_ad_set(db, group, payload)
    _rollup(db, c)
    _audit(db, tenant_id, actor, "ad_set.updated", "ad_group", group.id, {"fields": changed, "on_meta": bool(group.external_id)})
    db.refresh(c)
    return tree(db, c)


def duplicate_ad_set(db: Session, tenant_id: str, actor: str, ad_set_id: str) -> dict[str, Any]:
    group = _ad_set(db, tenant_id, ad_set_id)
    c = _campaign(db, tenant_id, str(group.campaign_id), lock=True)
    if c.status != "draft":
        raise ConflictError("Duplicating into a published campaign isn't supported yet; duplicate the campaign.")
    if len(_groups(c)) >= MAX_AD_SETS:
        raise AppError(f"A campaign can have at most {MAX_AD_SETS} ad sets.", 422)
    md = {k: v for k, v in _md(group).items() if k not in ("effective_status", "last_error")}
    copy_row = AdGroup(tenant_id=c.tenant_id, campaign_id=c.id, name=f"{group.name} (copy)"[:255], targeting=copy.deepcopy(group.targeting),
                       budget_cents=group.budget_cents, bid_strategy=group.bid_strategy, status="draft", audience_id=group.audience_id, extra_metadata=md)
    db.add(copy_row)
    db.flush()
    for ad in group.ads:
        db.add(Ad(tenant_id=c.tenant_id, ad_group_id=copy_row.id, name=ad.name, status="draft", content_asset_id=ad.content_asset_id,
                  extra_metadata={k: v for k, v in _md(ad).items() if k not in ("effective_status", "last_error", "creative_id", "review_feedback")}))
    db.flush()
    db.refresh(c)
    _rollup(db, c)
    _audit(db, tenant_id, actor, "ad_set.created", "ad_group", copy_row.id, {"duplicate_of": str(group.id)})
    db.refresh(c)
    return tree(db, c)


def delete_ad_set(db: Session, tenant_id: str, actor: str, ad_set_id: str) -> dict[str, Any]:
    group = _ad_set(db, tenant_id, ad_set_id)
    c = _campaign(db, tenant_id, str(group.campaign_id), lock=True)
    if group.external_id or c.status != "draft":
        raise ConflictError("A published ad set can't be deleted; pause it instead.")
    db.delete(group)
    db.flush()
    db.refresh(c)
    _rollup(db, c)
    _audit(db, tenant_id, actor, "ad_set.deleted", "ad_group", ad_set_id, {"campaign_id": str(c.id)})
    db.refresh(c)
    return tree(db, c)


def _new_ad(group: AdGroup, payload: s.AdFields) -> Ad:
    return Ad(tenant_id=group.tenant_id, ad_group_id=group.id, name=(payload.name or "New ad")[:255], status="draft",
              extra_metadata={"format": "image", "media": [], "cards": [], "call_to_action": "LEARN_MORE",
                              "destination": {"type": "website"}, "use_instagram": True,
                              "url_tags": "utm_source=facebook&utm_medium=paid&utm_campaign={{campaign.name}}"})


def _apply_ad(db: Session, ad: Ad, payload: s.AdFields) -> list[str]:
    sent = set(payload.model_fields_set)
    md = _md(ad)
    if "name" in sent and payload.name:
        ad.name = payload.name.strip()
    for k in ("format", "primary_text", "headline", "description", "call_to_action", "url_tags", "use_instagram"):
        if k in sent:
            md[k] = getattr(payload, k)
    if "media" in sent:
        md["media"] = [m.model_dump() for m in payload.media or []]
    if "cards" in sent:
        md["cards"] = [c.model_dump() for c in payload.cards or []]
    # SPEC-BE-082: each format keeps its own data, so switching back loses nothing.
    if "carousel_source" in sent and payload.carousel_source:
        md["carousel_source"] = payload.carousel_source
    if "product_set" in sent:
        md["product_set"] = payload.product_set.model_dump() if payload.product_set else None
    if "existing_post" in sent:
        md["existing_post"] = payload.existing_post.model_dump() if payload.existing_post else None
    if "destination" in sent and payload.destination is not None:
        md["destination"] = payload.destination.model_dump()
    if "call_to_action" in sent and payload.call_to_action and payload.call_to_action not in meta_ads.CALLS_TO_ACTION:
        raise AppError("Unknown call to action.", 422)
    if "content_asset_id" in sent and payload.content_asset_id:
        from app.models.content import ContentAsset

        asset = db.query(ContentAsset).filter(ContentAsset.tenant_id == ad.tenant_id, ContentAsset.id == payload.content_asset_id).first()
        if asset is None:
            raise NotFoundError("Creative not found.")
        variants = asset.variants or []
        index = asset.selected_variant_index or 0
        variant = variants[index] if index < len(variants) else {}
        ad.content_asset_id = asset.id
        md["headline"] = md.get("headline") or variant.get("headline") or ""
        md["primary_text"] = variant.get("description") or md.get("primary_text") or ""
    ad.extra_metadata = md
    return sorted(sent)


def add_ad(db: Session, tenant_id: str, actor: str, ad_set_id: str, payload: s.AdCreate) -> dict[str, Any]:
    group = _ad_set(db, tenant_id, ad_set_id)
    c = _campaign(db, tenant_id, str(group.campaign_id), lock=True)
    if c.status != "draft":
        raise ConflictError("Ads can only be added to a draft campaign.")
    if len([a for a in group.ads if a.tenant_id == group.tenant_id]) >= MAX_ADS:
        raise AppError(f"An ad set can have at most {MAX_ADS} ads.", 422)
    ad = _new_ad(group, payload)
    db.add(ad)
    db.flush()
    _apply_ad(db, ad, payload)
    _audit(db, tenant_id, actor, "ad.created", "ad", ad.id, {"ad_set_id": str(group.id)})
    db.refresh(c)
    return tree(db, c)


def _child_attachment(card: dict[str, Any], link: str, cta: dict[str, Any]) -> dict[str, Any]:
    child = {"link": card.get("link") or link, "name": card.get("headline") or "",
             "description": card.get("description") or "", "call_to_action": cta}
    if (card.get("type") or "image") == "video":
        # A video card needs a still for Meta: the processed video's thumbnail.
        child.update(video_id=card.get("video_id"), picture=card.get("thumbnail_url"))
    else:
        child["image_hash"] = card.get("image_hash")
    return child


def _creative_spec(c: Campaign, group: AdGroup, ad: Ad, conn: dict[str, str]) -> dict[str, Any]:
    md, gmd = _md(ad), _md(group)
    dest = md.get("destination") or {}
    loc = gmd.get("conversion_location") or "website"
    page = conn["page_id"]
    link = dest.get("url") or gmd.get("app_store_url") or f"https://www.facebook.com/{page}"
    cta: dict[str, Any] = {"type": md.get("call_to_action") or "LEARN_MORE", "value": {"link": link}}
    if loc == "instant_form":
        cta["value"] = {"lead_gen_form_id": dest.get("lead_form_id")}
    if loc == "app" or _objective_key(c) == "app_promotion":
        cta["value"] = {"link": gmd.get("app_store_url"), "application": gmd.get("app_id")}
    fmt = md.get("format") or "image"
    placements = gmd.get("placements") or {}
    uses_ig = placements.get("mode") != "manual" or "instagram" in (placements.get("platforms") or [])
    name = f"{ad.name} — Creative"[:255]
    if fmt == "existing_post":
        # SPEC-BE-082: the post's own text, media and button are used as is.
        post = md.get("existing_post") or {}
        spec: dict[str, Any] = {"name": name}
        if post.get("platform") == "instagram":
            spec.update(object_id=page, instagram_user_id=conn.get("instagram_id"), source_instagram_media_id=post.get("id"))
        else:
            spec["object_story_id"] = post.get("id")
            if uses_ig and md.get("use_instagram", True) and conn.get("instagram_id"):
                spec["instagram_user_id"] = conn["instagram_id"]
        if md.get("url_tags"):
            spec["url_tags"] = md["url_tags"]
        return spec
    media = (md.get("media") or [{}])[0] if md.get("media") else {}
    story: dict[str, Any] = {"page_id": page}
    product_set = _ad_product_set(ad)
    if product_set:
        # Cards come from the catalog: Meta fills the {{product.*}} placeholders.
        story["template_data"] = {
            "link": link, "message": md.get("primary_text") or "", "call_to_action": {"type": cta["type"]},
            "multi_share_end_card": False, "name": "{{product.name}}", "description": "{{product.price}}",
        }
    elif fmt == "video":
        story["video_data"] = {
            "video_id": media.get("video_id"), "image_url": media.get("thumbnail_url"), "message": md.get("primary_text") or "",
            "title": md.get("headline") or "", "link_description": md.get("description") or "", "call_to_action": cta,
        }
    elif fmt == "carousel":
        story["link_data"] = {
            "link": link, "message": md.get("primary_text") or "", "call_to_action": cta, "multi_share_end_card": False,
            "child_attachments": [_child_attachment(card, link, cta) for card in md.get("cards") or []],
        }
    else:
        story["link_data"] = {
            "link": link, "message": md.get("primary_text") or "", "name": md.get("headline") or "",
            "description": md.get("description") or "", "image_hash": media.get("image_hash"), "call_to_action": cta,
        }
    spec = {"name": name, "object_story_spec": story}
    if product_set:
        spec["product_set_id"] = product_set["id"]
    if uses_ig and md.get("use_instagram", True) and conn.get("instagram_id"):
        spec["instagram_user_id"] = conn["instagram_id"]
    if md.get("url_tags"):
        spec["url_tags"] = md["url_tags"]
    return spec


def update_ad(db: Session, tenant_id: str, actor: str, ad_id: str, payload: s.AdFields) -> dict[str, Any]:
    ad = _ad(db, tenant_id, ad_id)
    group = _ad_set(db, tenant_id, str(ad.ad_group_id))
    c = _campaign(db, tenant_id, str(group.campaign_id), lock=True)
    sent = set(payload.model_fields_set)
    if ad.external_ad_id:
        _live_guard(sent, LIVE_AD_FIELDS, "ad")
        changed = _apply_ad(db, ad, payload)
        conn = _conn(db, tenant_id)
        assert conn is not None
        client = _client(conn)
        values: dict[str, Any] = {}
        if sent - {"name"}:
            # Meta creatives are immutable: a text/CTA change makes a new creative
            # and points the ad at it (Meta re-reviews the ad).
            creative_id = _meta_call(db, tenant_id, client.create, conn["ad_account_id"], "adcreatives", _creative_spec(c, group, ad, conn))
            values["creative"] = {"creative_id": creative_id}
            _set_md(ad, creative_id=creative_id)
        if "name" in sent and payload.name:
            values["name"] = payload.name
        if values:
            _meta_call(db, tenant_id, client.post, ad.external_ad_id, values)
    else:
        if c.status != "draft":
            raise ConflictError(f"This campaign is {c.status}; it can't be edited.")
        changed = _apply_ad(db, ad, payload)
    _audit(db, tenant_id, actor, "ad.updated", "ad", ad.id, {"fields": changed, "on_meta": bool(ad.external_ad_id)})
    db.refresh(c)
    return tree(db, c)


def duplicate_ad(db: Session, tenant_id: str, actor: str, ad_id: str) -> dict[str, Any]:
    ad = _ad(db, tenant_id, ad_id)
    group = _ad_set(db, tenant_id, str(ad.ad_group_id))
    c = _campaign(db, tenant_id, str(group.campaign_id), lock=True)
    if c.status != "draft":
        raise ConflictError("Ads can only be duplicated in a draft campaign.")
    if len([a for a in group.ads if a.tenant_id == group.tenant_id]) >= MAX_ADS:
        raise AppError(f"An ad set can have at most {MAX_ADS} ads.", 422)
    new = Ad(tenant_id=c.tenant_id, ad_group_id=group.id, name=f"{ad.name} (copy)"[:255], status="draft", content_asset_id=ad.content_asset_id,
             extra_metadata={k: v for k, v in _md(ad).items() if k not in ("effective_status", "last_error", "creative_id", "review_feedback")})
    db.add(new)
    db.flush()
    _audit(db, tenant_id, actor, "ad.created", "ad", new.id, {"duplicate_of": str(ad.id)})
    db.refresh(c)
    return tree(db, c)


def delete_ad(db: Session, tenant_id: str, actor: str, ad_id: str) -> dict[str, Any]:
    ad = _ad(db, tenant_id, ad_id)
    group = _ad_set(db, tenant_id, str(ad.ad_group_id))
    c = _campaign(db, tenant_id, str(group.campaign_id), lock=True)
    if ad.external_ad_id or c.status != "draft":
        raise ConflictError("A published ad can't be deleted; pause it instead.")
    db.delete(ad)
    db.flush()
    _audit(db, tenant_id, actor, "ad.deleted", "ad", ad_id, {"ad_set_id": str(group.id)})
    db.refresh(c)
    return tree(db, c)


# ---------------------------------------------------------------------------
# Meta request bodies
# ---------------------------------------------------------------------------
def meta_targeting(t: dict[str, Any], placements: dict[str, Any]) -> dict[str, Any]:
    geo: dict[str, Any] = {}
    covered = {str((r.get("extra") or {}).get("country_code") or "").upper() for r in [*(t.get("regions") or []), *(t.get("cities") or [])]}
    countries = [c for c in t.get("countries") or [] if c not in covered]
    if countries:
        geo["countries"] = countries
    if t.get("regions"):
        geo["regions"] = [{"key": r["key"]} for r in t["regions"]]
    if t.get("cities"):
        geo["cities"] = [{"key": r["key"], "radius": r.get("radius") or 10, "distance_unit": r.get("distance_unit") or "kilometer"} for r in t["cities"]]
    if t.get("zips"):
        geo["zips"] = [{"key": r["key"]} for r in t["zips"]]
    spec: dict[str, Any] = {
        "geo_locations": geo,
        "age_min": max(meta_ads.MIN_AGE, int(t.get("age_min") or 18)),
        "age_max": min(meta_ads.MAX_AGE, int(t.get("age_max") or 65)),
    }
    if t.get("genders") in ("male", "female"):
        spec["genders"] = [1] if t["genders"] == "male" else [2]
    if t.get("locales"):
        spec["locales"] = [int(r["key"]) for r in t["locales"] if str(r["key"]).isdigit()]
    detailed: dict[str, list[dict[str, str]]] = {}
    for r in t.get("detailed") or []:
        bucket = {"interest": "interests", "interests": "interests", "behaviors": "behaviors", "behavior": "behaviors"}.get(str(r.get("type") or "interests"), str(r.get("type") or "interests"))
        detailed.setdefault(bucket, []).append({"id": r["key"], "name": r.get("name") or ""})
    if detailed:
        spec["flexible_spec"] = [detailed]
    if t.get("custom_audiences"):
        spec["custom_audiences"] = [{"id": r["key"]} for r in t["custom_audiences"]]
    if t.get("excluded_custom_audiences"):
        spec["excluded_custom_audiences"] = [{"id": r["key"]} for r in t["excluded_custom_audiences"]]
    spec["targeting_automation"] = {"advantage_audience": 1 if t.get("advantage_audience") else 0}
    if (placements or {}).get("mode") == "manual":
        platforms = placements.get("platforms") or []
        spec["publisher_platforms"] = platforms
        positions = placements.get("positions") or {}
        for platform in platforms:
            chosen = [p for p in positions.get(platform) or [] if p in meta_ads.PLACEMENT_POSITIONS.get(platform, [])]
            if chosen:
                spec[f"{platform}_positions"] = chosen
        if placements.get("devices"):
            spec["device_platforms"] = placements["devices"]
    return spec


def _campaign_body(c: Campaign) -> dict[str, Any]:
    b = _builder(c)
    body: dict[str, Any] = {
        "name": c.name,
        "objective": meta_ads.BUILDER_OBJECTIVES[_objective_key(c)]["meta"],
        "status": "PAUSED",
        "special_ad_categories": b.get("special_ad_categories") or [],
        "buying_type": "AUCTION",
    }
    if b.get("special_ad_categories"):
        body["special_ad_category_country"] = b.get("special_ad_category_country") or []
    if (b.get("budget_mode") or "ad_set") == "campaign":
        amount = meta_ads.to_meta_amount(int(b.get("budget_cents") or 0), c.currency)
        body["lifetime_budget" if b.get("budget_type") == "lifetime" else "daily_budget"] = amount
        body["bid_strategy"] = b.get("bid_strategy") or "LOWEST_COST_WITHOUT_CAP"
    else:
        body["is_adset_budget_sharing_enabled"] = False
    if b.get("spend_cap_cents"):
        body["spend_cap"] = meta_ads.to_meta_amount(int(b["spend_cap_cents"]), c.currency)
    # SPEC-BE-082: a product-set carousel makes this a catalog Sales campaign.
    catalog = next((ps["catalog_id"] for g in _groups(c) if (ps := _group_product_set(g))), None)
    if catalog:
        body["promoted_object"] = {"product_catalog_id": catalog}
    return body


def _ad_set_body(c: Campaign, g: AdGroup, campaign_id: str, conn: dict[str, str], now: datetime) -> dict[str, Any]:
    b, md = _builder(c), _md(g)
    loc = md.get("conversion_location") or "website"
    goal = md.get("optimization_goal") or _default_goal(_objective_key(c))[1]
    start = max(_utc(md.get("starts_at")) or now, now)
    body: dict[str, Any] = {
        "name": g.name, "campaign_id": campaign_id, "start_time": start.isoformat(),
        "end_time": _iso(_utc(md.get("ends_at"))), "billing_event": "THRUPLAY" if goal == "THRUPLAY" else "IMPRESSIONS",
        "optimization_goal": goal, "targeting": meta_targeting(dict(g.targeting or {}), md.get("placements") or {}),
        "status": "ACTIVE",
    }
    if loc in meta_ads.DESTINATION_TYPES and loc != "on_ad":
        body["destination_type"] = meta_ads.DESTINATION_TYPES[loc]
    if (b.get("budget_mode") or "ad_set") == "ad_set":
        amount = meta_ads.to_meta_amount(int(g.budget_cents or 0), c.currency)
        body["lifetime_budget" if md.get("budget_type") == "lifetime" else "daily_budget"] = amount
        body["bid_strategy"] = g.bid_strategy or "LOWEST_COST_WITHOUT_CAP"
        strategy, bid = g.bid_strategy, md.get("bid_amount_cents")
    else:
        strategy, bid = b.get("bid_strategy"), b.get("bid_amount_cents")
    if strategy in ("LOWEST_COST_WITH_BID_CAP", "COST_CAP") and bid:
        body["bid_amount"] = meta_ads.to_meta_amount(int(bid), c.currency)
    if strategy == "LOWEST_COST_WITH_MIN_ROAS" and b.get("roas_floor"):
        body["bid_constraints"] = {"roas_average_floor": int(float(b["roas_floor"]) * 10000)}
    promoted: dict[str, Any] = {}
    if goal in ("OFFSITE_CONVERSIONS", "VALUE") and loc == "website":
        promoted = {"pixel_id": md.get("pixel_id") or conn["pixel_id"], "custom_event_type": md.get("custom_event_type") or "PURCHASE"}
    elif loc == "app" or _objective_key(c) == "app_promotion":
        promoted = {"application_id": md.get("app_id"), "object_store_url": md.get("app_store_url")}
    elif loc == "instant_form" or goal in ("PAGE_LIKES", "LEAD_GENERATION", "QUALITY_LEAD"):
        promoted = {"page_id": conn["page_id"]}
    product_set = _group_product_set(g)
    if product_set:
        promoted = {**promoted, "product_set_id": product_set["id"]}  # SPEC-BE-082
    if promoted:
        body["promoted_object"] = promoted
    return body


# ---------------------------------------------------------------------------
# Validate / preview
# ---------------------------------------------------------------------------
def _map_meta_error(exc: meta_ads.MetaError, level: str, row_id: Any) -> dict[str, Any]:
    _kind, _status, message = meta_ads.classify(exc)
    field = exc.blame_fields[0] if exc.blame_fields else "meta"
    return {"level": level, "id": str(row_id), "field": field, "message": message, "source": "meta"}


def validate(db: Session, tenant_id: str, actor: str, campaign_id: str) -> dict[str, Any]:
    c = _campaign(db, tenant_id, campaign_id)
    errors = missing(db, c)
    conn = _conn(db, tenant_id, required=False)
    if conn is None:
        errors.append({"level": "campaign", "id": str(c.id), "field": "connection", "message": "Connect Meta in Integrations to publish.", "source": "local"})
    elif not [e for e in errors if e["level"] == "campaign"]:
        # Meta validates the campaign object without creating it. Ad sets and
        # ads need a real campaign id, so they're validated at publish (which
        # rolls back on any error).
        try:
            _client(conn).validate_only(conn["ad_account_id"], "campaigns", _campaign_body(c))
        except meta_ads.MetaError as exc:
            errors.append(_map_meta_error(exc, "campaign", c.id))
    _audit(db, tenant_id, actor, "campaign.validated", "campaign", c.id, {"errors": len(errors)})
    return {"ok": not errors, "errors": errors}


def preview(db: Session, tenant_id: str, ad_id: str, ad_format: str) -> dict[str, Any]:
    if ad_format not in meta_ads.PREVIEW_FORMATS:
        raise AppError("Unknown preview format.", 422)
    ad = _ad(db, tenant_id, ad_id)
    group = _ad_set(db, tenant_id, str(ad.ad_group_id))
    c = _campaign(db, tenant_id, str(group.campaign_id))
    conn = _conn(db, tenant_id)
    assert conn is not None
    spec = _creative_spec(c, group, ad, conn)
    spec.pop("name", None)
    rows = _meta_call(db, tenant_id, _client(conn).previews, conn["ad_account_id"], spec, ad_format)
    if not rows:
        raise AppError("Meta returned no preview for this format.", 502)
    return {"format": ad_format, "iframe_html": str(rows[0].get("body") or "")}


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------
def publish(db: Session, tenant_id: str, actor: str, actor_is_owner: bool, campaign_id: str, mode: str = "active") -> dict[str, Any]:
    from app.services.campaign_service import approval_decision

    now = datetime.now(timezone.utc)
    c = _campaign(db, tenant_id, campaign_id, lock=True)
    if c.status != "draft":
        raise ConflictError(f"Only draft campaigns can be published (this one is {c.status}).")
    b = _builder(c)
    if b.get("pending_approval_id"):
        raise ConflictError("This campaign is already waiting for owner approval.")
    problems = missing(db, c)
    if problems:
        raise AppError("Fix these first: " + "; ".join(p["message"] for p in problems[:6]), 422)
    conn = _conn(db, tenant_id)
    assert conn is not None
    if c.ends_at and c.ends_at <= now:
        raise AppError("The schedule has already ended; pick new dates.", 422)
    required, reason = approval_decision(db, c)
    if required and not actor_is_owner:
        approval_id = db.execute(
            insert(_approval_queue).values(
                tenant_id=tenant_id, subject_type="campaign", subject_id=c.id, title=c.name[:255],
                summary=f"Publish {c.name} to Meta ({mode}): daily {format_money(c.daily_cap_cents, c.currency)}. Needs approval: {reason}.",
                payload={"campaign_id": str(c.id), "builder": True, "mode": mode, "daily_cap_cents": c.daily_cap_cents,
                         "budget_cents": c.budget_cents, "currency": c.currency.strip(), "reason": reason},
                requested_by_type="human", requested_by=actor,
            ).returning(_approval_queue.c.id)
        ).scalar_one()
        _set_meta_key(c, "builder", {"pending_approval_id": str(approval_id), "pending_mode": mode})
        _audit(db, tenant_id, actor, "campaign.submit_for_approval", "campaign", c.id, {"approval_id": str(approval_id), "reason": reason})
        db.refresh(c)
        return tree(db, c)
    try:
        _go_live(db, c, conn, mode, actor if actor_is_owner else None, now)
    except PublishError as exc:
        _record_failure(db, tenant_id, actor, campaign_id, exc)
        raise
    _audit(db, tenant_id, actor, "campaign.published", "campaign", c.id,
           {"platform": "meta", "mode": mode, "meta_campaign_id": (c.extra_metadata or {}).get("meta", {}).get("campaign_id"), "approval_rule": reason})
    db.refresh(c)
    return tree(db, c)


def _record_failure(db: Session, tenant_id: str, actor: str | None, campaign_id: str, exc: PublishError) -> None:
    db.rollback()
    if exc.expired:
        integration_service.mark_meta_expired(db, tenant_id, exc.detail)
    c = db.query(Campaign).filter(Campaign.tenant_id == tenant_id, Campaign.id == campaign_id).first()
    if c is not None:
        _set_meta_key(c, "meta", {"last_error": f"{exc.path + ': ' if exc.path else ''}{exc.detail}"[:400]})
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor, action="campaign.publish_failed", resource_type="campaign",
                    resource_id=campaign_id, metadata={"error": exc.detail[:300], "path": exc.path, "expired": exc.expired})


def _go_live(db: Session, c: Campaign, conn: dict[str, str], mode: str, approver: str | None, now: datetime) -> None:
    """Meta objects first, then our rows; no commit (the caller's audit commits)."""
    client = _client(conn)
    act = conn["ad_account_id"]
    created: list[str] = []
    path = "campaign"
    groups = _groups(c)
    try:
        account = client.get_ad_account(act)
        currency = str(account.get("currency") or "").upper()
        if currency != c.currency.strip().upper():
            raise PublishError(f"Your Meta ad account bills in {currency or 'another currency'}, but this campaign is in {c.currency.strip()}.", 422)
        if int(account.get("account_status") or 0) != 1:
            status_text = meta_ads.ACCOUNT_STATUS.get(int(account.get("account_status") or 0), "not active")
            raise PublishError(f"Your Meta ad account is {status_text}; fix it in Ads Manager.", 422)
        meta_campaign_id = client.create(act, "campaigns", _campaign_body(c))
        created.append(meta_campaign_id)
        results: list[tuple[AdGroup, str, list[tuple[Ad, str, str]]]] = []
        for gi, g in enumerate(groups):
            path = f"ad_sets[{gi}]"
            adset_id = client.create(act, "adsets", _ad_set_body(c, g, meta_campaign_id, conn, now))
            ads_done: list[tuple[Ad, str, str]] = []
            for ai, ad in enumerate(sorted([a for a in g.ads if a.tenant_id == g.tenant_id], key=lambda x: (x.created_at, str(x.id)))):
                path = f"ad_sets[{gi}].ads[{ai}]"
                creative_id = client.create(act, "adcreatives", _creative_spec(c, g, ad, conn))
                created.append(creative_id)
                ad_id = client.create(act, "ads", {"name": ad.name, "adset_id": adset_id, "creative": {"creative_id": creative_id}, "status": "ACTIVE"})
                ads_done.append((ad, ad_id, creative_id))
            results.append((g, adset_id, ads_done))
        if mode == "active":
            path = "campaign"
            client.set_status(meta_campaign_id, "ACTIVE")
    except meta_ads.MetaError as exc:
        for object_id in created:
            try:
                client.delete(object_id)
            except meta_ads.MetaError:
                logger.warning("meta_cleanup_failed", campaign_id=str(c.id), object_id=object_id)
        kind, status, message = meta_ads.classify(exc)
        raise PublishError(message, 409 if kind == "auth" else (status if kind in ("rate_limit", "permission") else 502), path=path, expired=kind == "auth") from None

    future = any((_utc(_md(g).get("starts_at")) or now) > now for g in groups)
    new_status = "paused" if mode == "paused" else ("scheduled" if future else "running")
    url = meta_ads.ads_manager_url(act, meta_campaign_id)
    for g, adset_id, ads_done in results:
        g.external_id = adset_id
        g.status = new_status
        _set_md(g, effective_status="PAUSED" if mode == "paused" else "ACTIVE", last_error=None)
        for ad, ad_id, creative_id in ads_done:
            ad.external_ad_id = ad_id
            ad.external_url = url
            ad.status = new_status
            _set_md(ad, creative_id=creative_id, effective_status="PENDING_REVIEW", last_error=None)
    _set_meta_key(c, "meta", {"campaign_id": meta_campaign_id, "ad_account_id": act, "published_at": now.isoformat(),
                              "last_error": None, "effective_status": "PAUSED" if mode == "paused" else "ACTIVE"})
    _set_meta_key(c, "builder", {"pending_approval_id": None, "pending_mode": None})
    c.status = new_status
    c.launched_at = now
    if mode == "paused":
        c.paused_at = now
    if approver:
        c.owner_approved_at = now
        c.owner_approved_by = approver


def apply_approval_decision(db: Session, tenant_id: str, approval_id: str, c: Campaign, decider: str, decision: str, now: datetime) -> None:
    """Owner approval of a builder publish (SPEC-BE-047 rule). Publishing errors
    keep the approval approved and leave the draft with last_error
    (SPEC-BE-054 decision 4)."""
    b = _builder(c)
    if c.status != "draft" or b.get("pending_approval_id") != approval_id:
        return
    if decision != "approved":
        _set_meta_key(c, "builder", {"pending_approval_id": None, "pending_mode": None})
        return
    conn = _conn(db, tenant_id, required=False)
    if conn is None:
        _set_meta_key(c, "builder", {"pending_approval_id": None})
        _set_meta_key(c, "meta", {"last_error": "Meta isn't connected; reconnect and publish again."})
        return
    try:
        with db.begin_nested():
            _go_live(db, c, conn, b.get("pending_mode") or "active", decider, now)
    except PublishError as exc:
        _set_meta_key(c, "builder", {"pending_approval_id": None})
        _set_meta_key(c, "meta", {"last_error": f"{exc.path + ': ' if exc.path else ''}{exc.detail}"[:400]})
        if exc.expired:
            integration_service.mark_meta_expired(db, tenant_id, exc.detail)


# ---------------------------------------------------------------------------
# Status per level, budget, status read-back
# ---------------------------------------------------------------------------
def set_status(db: Session, tenant_id: str, actor: str, level: str, object_id: str, resume: bool) -> dict[str, Any]:
    from app.services import campaign_service

    if level == "campaign":
        detail = (campaign_service.resume if resume else campaign_service.pause)(db, tenant_id, actor, object_id)
        return {"id": str(detail["id"]), "name": detail["name"], "level": level, "status": detail["status"]}
    row: AdGroup | Ad = _ad_set(db, tenant_id, object_id) if level == "ad_set" else _ad(db, tenant_id, object_id)
    external = row.external_id if isinstance(row, AdGroup) else row.external_ad_id
    if not external:
        raise ConflictError(f"This {level.replace('_', ' ')} isn't published on Meta.")
    if not resume and row.status not in ("running", "scheduled"):
        raise ConflictError(f"Only running or scheduled {level.replace('_', ' ')}s can be paused.")
    if resume and row.status != "paused":
        raise ConflictError(f"Only paused {level.replace('_', ' ')}s can be resumed.")
    conn = _conn(db, tenant_id)
    assert conn is not None
    _meta_call(db, tenant_id, _client(conn).set_status, external, "ACTIVE" if resume else "PAUSED")
    row.status = "running" if resume else "paused"
    _set_md(row, effective_status="ACTIVE" if resume else "PAUSED")
    if isinstance(row, AdGroup):
        for ad in row.ads:
            if ad.external_ad_id:
                ad.status = row.status
    _audit(db, tenant_id, actor, f"{level}.meta_{'resumed' if resume else 'paused'}", "ad_group" if level == "ad_set" else "ad", row.id, {"external_id": external})
    return {"id": str(row.id), "name": row.name, "level": level, "status": row.status}


def update_budget(db: Session, tenant_id: str, actor: str, campaign_id: str, cents: int, budget_type: str) -> dict[str, Any]:
    c = _campaign(db, tenant_id, campaign_id, lock=True)
    b = _builder(c)
    amount = Decimal(cents) / 100
    if (b.get("budget_mode") or "ad_set") == "campaign":
        update_campaign(db, tenant_id, actor, campaign_id, s.CampaignFields(budget=amount, budget_type=budget_type) if not _published(c) else s.CampaignFields(budget=amount))  # type: ignore[arg-type]
    else:
        groups = _groups(c)
        if len(groups) != 1:
            raise ConflictError("This campaign has several ad sets with their own budgets; change them in the builder.")
        update_ad_set(db, tenant_id, actor, str(groups[0].id), s.AdSetFields(budget=amount) if groups[0].external_id else s.AdSetFields(budget=amount, budget_type=budget_type))  # type: ignore[arg-type]
    return {"id": str(c.id), "name": c.name}


def refresh_statuses(db: Session, c: Campaign) -> None:
    """Reads Meta effective_status for the campaign, its ad sets and ads and
    maps them onto our status (SPEC-BE-055 rule 10 / SPEC-BE-056). No commit."""
    meta = (c.extra_metadata or {}).get("meta") or {}
    conn = _conn(db, str(c.tenant_id), required=False)
    if conn is None or not meta.get("campaign_id"):
        return
    groups = [g for g in _groups(c) if g.external_id]
    ads = [a for g in groups for a in g.ads if a.external_ad_id]
    ids = [meta["campaign_id"], *(g.external_id for g in groups), *(a.external_ad_id for a in ads)]
    try:
        data = _client(conn).get_many([i for i in ids if i], "effective_status,configured_status")
        review = _client(conn).get_many([a.external_ad_id for a in ads if a.external_ad_id], "ad_review_feedback") if ads else {}
    except meta_ads.MetaError as exc:
        kind, status, message = meta_ads.classify(exc)
        if exc.code == 100 and "exist" in exc.message.lower():
            c.status = "completed"
            _set_meta_key(c, "meta", {"deleted_on_meta": True})
            return
        if kind == "auth":
            integration_service.mark_meta_expired(db, str(c.tenant_id), exc.message)
        raise AppError(message, status) from None
    now = datetime.now(timezone.utc)
    camp = data.get(meta["campaign_id"]) or {}
    if camp.get("effective_status"):
        c.status = meta_ads.our_status(camp["effective_status"], c.status)
    _set_meta_key(c, "meta", {"effective_status": camp.get("effective_status"), "last_status_sync": now.isoformat()})
    for g in groups:
        eff = (data.get(g.external_id or "") or {}).get("effective_status")
        if eff:
            g.status = meta_ads.our_status(eff, g.status)
            _set_md(g, effective_status=eff)
    for a in ads:
        eff = (data.get(a.external_ad_id or "") or {}).get("effective_status")
        feedback = (review.get(a.external_ad_id or "") or {}).get("ad_review_feedback")
        if eff:
            a.status = meta_ads.our_status(eff, a.status)
            values: dict[str, Any] = {"effective_status": eff, "review_feedback": feedback}
            if eff in ("DISAPPROVED", "WITH_ISSUES"):
                reasons = "; ".join(str(v) for v in ((feedback or {}).get("global") or {}).values()) or eff.replace("_", " ").lower()
                values["last_error"] = reasons[:400]
            _set_md(a, **values)


# ---------------------------------------------------------------------------
# Command Chat (SPEC-BE-059): one command -> a whole draft tree
# ---------------------------------------------------------------------------
def create_from_command(db: Session, tenant_id: str, actor: str, spec: dict[str, Any]) -> dict[str, Any]:
    from zoneinfo import ZoneInfo

    tenant = _tenant(db, tenant_id)
    tz = ZoneInfo(tenant.timezone or "UTC")
    created = create_campaign(db, tenant_id, actor, s.CampaignCreate(name=spec["name"], objective=spec["objective"]), with_defaults=True)
    c = _campaign(db, tenant_id, created["campaign"]["id"], lock=True)
    group = _groups(c)[0]
    start_day = datetime.fromisoformat(spec["start_date"]).date() if spec.get("start_date") else None
    now = datetime.now(timezone.utc)
    starts = datetime.combine(start_day, datetime.min.time(), tz) if start_day else now.replace(second=0, microsecond=0) + timedelta(minutes=30)
    ends = starts + timedelta(days=int(spec["duration_days"]))
    placements = {"mode": "manual", "platforms": spec["platforms"]} if spec.get("platforms") else {"mode": "advantage"}
    update_ad_set(db, tenant_id, actor, str(group.id), s.AdSetFields(
        budget_type=spec.get("budget_type") or "daily", budget=Decimal(str(spec["budget"])), starts_at=starts, ends_at=ends,
        targeting=s.Targeting(countries=spec["countries"], age_min=spec.get("age_min", 18), age_max=spec.get("age_max", 65), genders=spec.get("genders", "all")),
        placements=s.Placements(**placements),
    ))
    titles = []
    if spec.get("skus"):
        from app.models.product import Product

        titles = [t for (t,) in db.query(Product.title).filter(Product.tenant_id == tenant_id, Product.sku.in_(spec["skus"])).all()]
    ad = next(a for a in group.ads)
    update_ad(db, tenant_id, actor, str(ad.id), s.AdFields(
        primary_text=spec.get("primary_text") or (f"Shop {', '.join(titles[:3])} now." if titles else None),
        headline=spec.get("headline") or (titles[0] if titles else spec["name"])[:255],
        call_to_action=spec.get("call_to_action") or "SHOP_NOW",
        destination=s.Destination(type="website", url=spec["destination_url"]),
    ))
    c = _campaign(db, tenant_id, str(c.id))
    _set_meta_key(c, "builder", {"source": "command_chat", "skus": spec.get("skus") or []})
    db.commit()
    return tree(db, c)
