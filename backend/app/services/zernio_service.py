"""Zernio as the paid-ads engine for every company (SPEC-BE-084).

One server-wide key (ZERNIO_API_KEY) serves every company. Each company gets its
own Zernio profile, created on first use. Storage is
tenants.settings["zernio"] = {profile_id, created_at, pending: {nonce: {u, p, step, exp}}}.
There is no DDL, and campaigns are read live from Zernio (GET /ads/tree), never
copied into our tables. The Meta builder, the multi-platform builder, the AI
Autopilot, the analytics imports and the enums are untouched.

Tenant isolation: the key sees every company's profile, so every id a caller
sends is checked against this company's profile first (accounts listed under
it, ad accounts listed under one of those accounts, campaigns / ad sets / ads
found in its campaign tree). A foreign or unknown id is a 404, never a 403.

D3 (user's choice, 2026-10-08): any manager+ may create ACTIVE campaigns and
resume them. There is no owner-only step and no spend-cap approval.

Audit rows use resource_type "tenant" (audit_log.resource_id is a uuid; Zernio
ids go into the metadata). Ad copy is never logged.
"""
import base64
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.audit import write_audit_log
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.integrations import zernio as z
from app.models.audit_log import AuditLog
from app.models.media import MediaAsset
from app.models.tenant import Tenant
from app.schemas import zernio as s
from app.services import media_service

logger = structlog.get_logger(__name__)

SETTINGS_KEY = "zernio"
PENDING_TTL = timedelta(minutes=30)
BAD_STATE = "This connection link expired or is invalid; start Connect again."
# Ads account kinds -> the platforms (wizard cards) they serve. One metaads
# account serves both Facebook and Instagram.
KIND_PLATFORMS: dict[str, list[str]] = {}
for _key, _rules in z.PLATFORMS.items():
    KIND_PLATFORMS.setdefault(_rules["ads_account"], []).append(_key)
# The posting account a boost runs from (platform card -> Zernio posting kind).
POSTING_KIND = {"facebook": "facebook", "instagram": "instagram", "tiktok": "tiktok", "linkedin": "linkedin",
                "pinterest": "pinterest", "twitter": "twitter"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _call(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a client call; Zernio errors -> AppError with Zernio's message."""
    try:
        return fn(*args, **kwargs)
    except z.ZernioError as exc:
        logger.warning("zernio_call_failed", call=getattr(fn, "__name__", "?"), status=exc.status_code, code=exc.code)
        raise AppError(exc.message, exc.status_code) from None


def _require_configured() -> None:
    if not z.configured():
        raise AppError("Zernio isn't set up on this server yet (the administrator adds ZERNIO_API_KEY).", 503)


def _tenant(db: Session, tenant_id: str, lock: bool = False) -> Tenant:
    tenant = db.get(Tenant, tenant_id, with_for_update=lock) if lock else db.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant not found.")
    return tenant


def _config(tenant: Tenant) -> dict[str, Any]:
    return dict((tenant.settings or {}).get(SETTINGS_KEY) or {})


def _save(tenant: Tenant, config: dict[str, Any]) -> None:
    # Reassign a new dict so SQLAlchemy sees the jsonb change.
    settings = dict(tenant.settings or {})
    settings[SETTINGS_KEY] = config
    tenant.settings = settings


def _audit(db: Session, tenant_id: str, actor: str | None, action: str, **meta: Any) -> None:
    # write_audit_log commits. Never any key or ad copy in the metadata.
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor, action=f"zernio.{action}", resource_type="tenant",
                    resource_id=tenant_id, metadata={k: v for k, v in meta.items() if v is not None})


def _already_audited(db: Session, tenant_id: str, action: str, request_id: str | None) -> bool:
    """A retried create replays Zernio's answer (Idempotency-Key): audit it once."""
    if not request_id:
        return False
    return db.query(AuditLog.id).filter(
        AuditLog.tenant_id == tenant_id, AuditLog.action == f"zernio.{action}",
        AuditLog.extra_metadata["request_id"].astext == request_id,
    ).first() is not None


def _str(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _int(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _ts(raw: Any) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if value else None


# ---------------------------------------------------------------------------
# Company profile
# ---------------------------------------------------------------------------
def profile_id(db: Session, tenant_id: str) -> str:
    """This company's Zernio profile, created (once) on first use."""
    _require_configured()
    config = _config(_tenant(db, tenant_id))
    if config.get("profile_id"):
        return str(config["profile_id"])
    tenant = _tenant(db, tenant_id, lock=True)  # one creator per company
    config = _config(tenant)
    if config.get("profile_id"):
        return str(config["profile_id"])
    name = f"{tenant.name.strip()[:80]} · {str(tenant.id)[:8]}"
    try:
        # The tenant id as Idempotency-Key: a retried first call replays the same profile.
        profile = z.create_profile(name, tenant.timezone, f"profile-{tenant.id}")
        pid = _str(profile.get("_id") or profile.get("id"))
    except z.ZernioError as exc:
        pid = None
        if exc.status_code == 422:
            # A 409 name clash (mapped to 422): reuse the profile of exactly that name,
            # which is ours (the name carries the tenant id).
            pid = next((str(p.get("_id")) for p in _call(_profiles) if p.get("name") == name), None)
        if not pid:
            raise AppError(exc.message, exc.status_code) from None
    if not pid:
        raise AppError("Zernio didn't return a profile for this company.", 502)
    config.update({"profile_id": pid, "created_at": datetime.now(timezone.utc).isoformat()})
    _save(tenant, config)
    db.commit()
    _audit(db, tenant_id, None, "profile_created", profile_id=pid)
    logger.info("zernio_profile_created", tenant_id=tenant_id)
    return pid


def _profiles() -> list[dict[str, Any]]:
    body = z.call("GET", "/profiles")
    rows = body.get("profiles") if isinstance(body, dict) else None
    return [p for p in rows if isinstance(p, dict)] if isinstance(rows, list) else []


def status(db: Session, tenant_id: str) -> dict[str, Any]:
    if not z.configured():
        return {"configured": False, "profile_ready": False, "account_count": None}
    pid = profile_id(db, tenant_id)
    return {"configured": True, "profile_ready": True, "account_count": len(_accounts(pid))}


# ---------------------------------------------------------------------------
# Accounts (ownership guard)
# ---------------------------------------------------------------------------
def _accounts(pid: str) -> list[dict[str, Any]]:
    rows = _call(z.list_accounts, pid)
    out = []
    for a in rows:
        owner = a.get("profileId")
        owner_id = owner.get("_id") if isinstance(owner, dict) else owner
        # Belt and braces: the filter is server-side, but only this profile's rows count.
        if str(owner_id or "") == pid and a.get("_id"):
            out.append(a)
    return out


def _account_out(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(a.get("_id")),
        "kind": str(a.get("platform") or ""),
        "username": _str(a.get("username")),
        "display_name": _str(a.get("displayName")),
        "picture_url": _str(a.get("profilePicture")),
        "needs_reconnection": bool(a.get("needsReconnection")) or a.get("isActive") is False,
        "parent_account_id": _str(a.get("parentAccountId")),
    }


def _require_account(db: Session, tenant_id: str, account_id: str, kinds: set[str] | None = None) -> dict[str, Any]:
    pid = profile_id(db, tenant_id)
    account = next((a for a in _accounts(pid) if str(a["_id"]) == account_id), None)
    if account is None or (kinds is not None and account.get("platform") not in kinds):
        raise NotFoundError("Account not found.")
    return account


def _ads_account_for(db: Session, tenant_id: str, platform: str, account_id: str) -> dict[str, Any]:
    return _require_account(db, tenant_id, account_id, {z.PLATFORMS[platform]["ads_account"]})


def _require_ad_account(account_id: str, ad_account_id: str) -> dict[str, Any]:
    row = next((r for r in _call(z.ad_accounts, account_id) if str(r.get("id")) == ad_account_id), None)
    if row is None:
        raise NotFoundError("Ad account not found.")
    return row


def platforms(db: Session, tenant_id: str) -> dict[str, Any]:
    if not z.configured():
        return {"configured": False, "platforms": [_platform_info(k, [], []) for k in z.PLATFORMS]}
    accounts = [_account_out(a) for a in _accounts(profile_id(db, tenant_id))]
    out = []
    for key, rules in z.PLATFORMS.items():
        ads = [a for a in accounts if a["kind"] == rules["ads_account"]]
        posting = [a for a in accounts if a["kind"] == POSTING_KIND.get(key)]
        out.append(_platform_info(key, ads, posting))
    return {"configured": True, "platforms": out}


def _platform_info(key: str, ads: list[dict[str, Any]], posting: list[dict[str, Any]]) -> dict[str, Any]:
    r = z.PLATFORMS[key]
    meta = r["family"] == "meta"
    return {
        "key": key, "label": r["label"], "connected": any(not a["needs_reconnection"] for a in ads),
        "ads_accounts": ads, "posting_accounts": posting,
        "goals": [{"key": g, "label": z.GOAL_LABELS.get(g, g)} for g in r["goals"]],
        "ctas": r["ctas"], "media": r["media"], "targeting": r["targeting"], "limits": r["limits"],
        "bid": r["bid"], "bid_strategies": z.BID_STRATEGIES if r["bid"] else [],
        "validate_supported": r["validate"], "preview_supported": r["preview"],
        "campaign_types": r.get("campaign_types", []),
        "placements": z.PLACEMENTS if meta else {},
        "special_ad_categories": z.SPECIAL_AD_CATEGORIES if meta else [],
        "income_tiers": (["top_10"] if key == "googleads" else z.INCOME_TIERS) if "income_tier" in r["targeting"] else [],
    }


# ---------------------------------------------------------------------------
# Connect (Zernio's hosted OAuth; the browser returns to our callback page)
# ---------------------------------------------------------------------------
def _redirect_url(nonce: str) -> str:
    # A short single-use nonce, not a JWT: X caps the URL-encoded redirect_url
    # at 258 characters (it travels inside X's OAuth state).
    return get_settings().FRONTEND_BASE_URL.rstrip("/") + f"/marketing/paid/zernio/callback?zs={nonce}"


def _remember(db: Session, tenant_id: str, actor: str, platform: str, step: str) -> str:
    tenant = _tenant(db, tenant_id, lock=True)
    config = _config(tenant)
    now = datetime.now(timezone.utc)
    pending = {k: v for k, v in dict(config.get("pending") or {}).items()
               if isinstance(v, dict) and (_ts(v.get("exp")) or now) > now}
    nonce = secrets.token_urlsafe(16)
    pending[nonce] = {"u": str(actor), "p": platform, "step": step, "exp": (now + PENDING_TTL).isoformat()}
    config["pending"] = pending
    _save(tenant, config)
    db.commit()
    return nonce


def connect(db: Session, tenant_id: str, actor: str, platform: str) -> dict[str, Any]:
    pid = profile_id(db, tenant_id)
    rules = z.PLATFORMS[platform]
    accounts = _accounts(pid)
    posting = next((a for a in accounts if a.get("platform") == POSTING_KIND.get(platform)), None)
    if platform == "twitter" and posting is None:
        # X ads need the X posting account first (no ads-only mode for X).
        nonce = _remember(db, tenant_id, actor, platform, "posting")
        result = _call(z.connect_posting, "twitter", pid, _redirect_url(nonce))
        step = "posting"
    else:
        nonce = _remember(db, tenant_id, actor, platform, "ads")
        account_id = str(posting["_id"]) if posting is not None and platform in ("twitter", "tiktok") else None
        result = _call(z.connect_ads, platform, pid, _redirect_url(nonce), account_id)
        step = "ads"
    _audit(db, tenant_id, actor, "connect_started", platform=platform, step=step)
    auth_url = _str(result.get("authUrl"))
    if result.get("alreadyConnected") and not auth_url:
        return {"auth_url": None, "already_connected": True, "step": step}
    if not auth_url:
        raise AppError(f"Zernio didn't return a {rules['label']} sign-in link.", 502)
    return {"auth_url": auth_url, "already_connected": False, "step": step}


def callback(db: Session, tenant_id: str, actor: str, payload: s.CallbackRequest) -> dict[str, Any]:
    tenant = _tenant(db, tenant_id, lock=True)
    config = _config(tenant)
    pending = dict(config.get("pending") or {})
    entry = pending.pop(payload.zs, None)  # single use
    config["pending"] = pending
    _save(tenant, config)
    db.commit()
    if not isinstance(entry, dict) or entry.get("u") != str(actor) or \
            (_ts(entry.get("exp")) or datetime.min.replace(tzinfo=timezone.utc)) < datetime.now(timezone.utc):
        raise AppError(BAD_STATE, 400)
    platform, step = str(entry.get("p")), str(entry.get("step") or "ads")
    label = z.PLATFORMS.get(platform, {}).get("label", platform)
    if payload.error:
        reason = payload.error_message or payload.error_reason or payload.error.replace("_", " ")
        raise AppError(f"{label} didn't connect: {reason}", 422)
    _audit(db, tenant_id, actor, "account_connected", platform=platform, step=step, account_id=payload.account_id)
    message = (f"Your {label} account is connected. Click Connect again to add its ads account."
               if step == "posting" else f"{label} ads are connected.")
    return {"platform": platform, "step": step, "connected": True, "account_id": payload.account_id, "message": message}


def disconnect(db: Session, tenant_id: str, actor: str, account_id: str) -> None:
    account = _require_account(db, tenant_id, account_id)
    _call(z.disconnect, account_id)
    _audit(db, tenant_id, actor, "account_disconnected", account_id=account_id, kind=account.get("platform"))


# ---------------------------------------------------------------------------
# Ad accounts, identities, posts, targeting
# ---------------------------------------------------------------------------
def ad_accounts(db: Session, tenant_id: str, account_id: str) -> dict[str, Any]:
    _require_account(db, tenant_id, account_id)
    items = []
    for r in _call(z.ad_accounts, account_id):
        if not r.get("id"):
            continue
        reasons = r.get("unusableReason")
        items.append({
            "id": str(r["id"]), "name": _str(r.get("name")), "currency": _str(r.get("currency")),
            "timezone": _str(r.get("timezoneName")), "status": _str(r.get("status")),
            "selectable": r.get("selectable") is not False,
            "unusable_reason": "; ".join(str(x) for x in reasons) if isinstance(reasons, list) and reasons
            else _str(reasons),
            "min_daily_budget": _num(r.get("minimumDailyBudget")), "business_name": _str(r.get("businessName")),
        })
    return {"items": items}


def identities(db: Session, tenant_id: str, account_id: str, ad_account_id: str) -> dict[str, Any]:
    account = _require_account(db, tenant_id, account_id)
    _require_ad_account(account_id, ad_account_id)
    kind = account.get("platform")
    out: dict[str, Any] = {"pages": [], "instagram_accounts": [], "tiktok_identities": [], "default_page_id": None,
                           "default_instagram_id": None}
    if kind in ("metaads", "facebook", "instagram"):
        body = _call(z.meta_identities, account_id, ad_account_id)
        for p in body.get("pages") or []:
            if isinstance(p, dict) and p.get("pageId"):
                out["pages"].append({"id": str(p["pageId"]), "name": _str(p.get("name")), "kind": "page", "detail": None})
                ig = p.get("instagramBusinessAccount") or p.get("connectedInstagramAccount")
                if isinstance(ig, dict) and ig.get("id"):
                    out["instagram_accounts"].append({"id": str(ig["id"]), "name": _str(ig.get("username") or ig.get("name")),
                                                      "kind": "instagram", "detail": _str(p.get("name"))})
        resolved = body.get("resolved") if isinstance(body.get("resolved"), dict) else {}
        out["default_page_id"] = _str(resolved.get("pageId"))
        out["default_instagram_id"] = _str(resolved.get("igUserId"))
    elif kind in ("tiktokads", "tiktok"):
        for i in _call(z.tiktok_identities, account_id, ad_account_id):
            if i.get("identityId"):
                out["tiktok_identities"].append({"id": str(i["identityId"]), "name": _str(i.get("displayName") or i.get("username")),
                                                 "kind": str(i.get("identityType") or ""), "detail": _str(i.get("username"))})
    return out


def account_posts(db: Session, tenant_id: str, account_id: str) -> dict[str, Any]:
    _require_account(db, tenant_id, account_id, set(POSTING_KIND.values()))
    return {"items": [
        {"id": str(p["id"]), "message": _str(p.get("message")), "created_at": _ts(p.get("createdTime")),
         "permalink": _str(p.get("permalink")), "picture": _str(p.get("picture")), "media_type": _str(p.get("mediaType"))}
        for p in _call(z.account_posts, account_id) if p.get("id")
    ]}


def targeting_search(db: Session, tenant_id: str, account_id: str, q: str, dimension: str, geo_type: str | None,
                     country: str | None, ad_account_id: str | None) -> dict[str, Any]:
    _require_account(db, tenant_id, account_id)
    rows = _call(z.targeting_search, account_id, q, dimension, geo_type, country, ad_account_id)
    items = []
    for r in rows:
        if not (r.get("id") or r.get("platformId")):
            continue
        size = r.get("audienceSize")
        items.append({
            "id": str(r.get("id") or r.get("platformId")), "name": str(r.get("name") or r.get("id")),
            "type": _str(r.get("type")),
            "path": " › ".join(str(x) for x in r["path"]) if isinstance(r.get("path"), list) else _str(r.get("path")),
            "country_code": _str(r.get("countryCode")),
            "audience_size": _int(size) if not isinstance(size, dict) else _int(size.get("upper") or size.get("lower")),
        })
    return {"items": items}


def _targeting(t: s.Targeting | s.BoostTargeting) -> dict[str, Any]:
    """Our TargetingSpec -> Zernio's camelCase TargetingSpec (empty = broadest)."""
    out: dict[str, Any] = {}
    if t.countries:
        out["countries"] = t.countries
    if t.regions:
        out["regions"] = [{"key": r.key, **({"name": r.name} if r.name else {})} for r in t.regions]
    if t.cities:
        out["cities"] = [{"key": c.key, **({"name": c.name} if c.name else {}),
                          **({"radius": c.radius, "distanceUnit": c.distance_unit} if c.radius else {})} for c in t.cities]
    if t.age_min is not None:
        out["ageMin"] = t.age_min
    if t.age_max is not None:
        out["ageMax"] = t.age_max
    if t.gender != "all":
        out["gender"] = t.gender
    if t.languages:
        out["languages"] = t.languages
    if t.interests:
        out["interests"] = [{"id": i.id, "name": i.name} for i in t.interests]
    if isinstance(t, s.Targeting):
        for name in ("zips", "metros"):
            rows = getattr(t, name)
            if rows:
                out[name] = [{"key": r.key, **({"name": r.name} if r.name else {})} for r in rows]
        if t.custom_locations:
            out["customLocations"] = [{"latitude": c.latitude, "longitude": c.longitude, "radius": c.radius,
                                       "distanceUnit": c.distance_unit, **({"name": c.name} if c.name else {})}
                                      for c in t.custom_locations]
        if t.excluded:
            ex: dict[str, Any] = {}
            if t.excluded.countries:
                ex["countries"] = [c.strip().upper() for c in t.excluded.countries]
            for name in ("regions", "cities", "zips"):
                rows = getattr(t.excluded, name)
                if rows:
                    ex[name] = [{"key": r.key} for r in rows]
            if ex:
                out["excludedLocations"] = ex
        if t.behaviors:
            out["behaviors"] = [{"id": b.id, "name": b.name} for b in t.behaviors]
        if t.income_tier:
            out["incomeTier"] = t.income_tier
    return out


def reach(db: Session, tenant_id: str, payload: s.ReachRequest) -> dict[str, Any]:
    _ads_account_for(db, tenant_id, payload.platform, payload.account_id)
    _require_ad_account(payload.account_id, payload.ad_account_id)
    body = _call(z.reach_estimate, payload.account_id, payload.ad_account_id, _targeting(payload.targeting),
                 payload.optimization_goal)
    # available:false = this platform has no pre-flight estimate; shown as such, never invented.
    return {"available": bool(body.get("available")), "lower": _int(body.get("lower")), "upper": _int(body.get("upper")),
            "daily": _int(body.get("daily"))}


# ---------------------------------------------------------------------------
# Media (our library -> a URL the platform can fetch)
# ---------------------------------------------------------------------------
def _media_url(asset: MediaAsset, *, meta_upload: tuple[str, str] | None) -> str:
    """A public URL for the asset. Meta images without a public address are
    uploaded as base64 to the ad account instead (POST /ads/images, ≤ 30 MB)."""
    try:
        return media_service.platform_url(asset)
    except ConflictError as exc:
        if meta_upload and asset.kind == "image" and int(asset.bytes) <= 30 * 1024 * 1024:
            b64 = base64.b64encode(media_service.read_bytes(asset)).decode()
            return str(_call(z.upload_image_base64, meta_upload[0], meta_upload[1], b64, asset.name or f"image-{asset.id}"))
        raise AppError(exc.detail, 422) from None


def _media(db: Session, tenant_id: str, payload: s.CampaignCreate) -> dict[str, Any]:
    c, rules = payload.creative, z.PLATFORMS[payload.platform]
    ids = [i for i in (c.media_id, c.square_media_id) if i]
    rows = media_service.media_rows(db, tenant_id, ids)
    if not rows:
        return {}
    main = rows[0]
    if main.kind not in rules["media"]:
        need = " or ".join(rules["media"])
        raise AppError(f"{rules['label']} ads take {need} here; the chosen file is {main.kind}.", 422)
    meta = rules["family"] == "meta"
    upload = (payload.account_id, payload.ad_account_id) if meta else None
    url = _media_url(main, meta_upload=upload)
    if payload.platform == "googleads":
        square = rows[1]
        if square.kind != "image":
            raise AppError("Google Display needs two images.", 422)
        return {"images": {"landscape": url, "square": _media_url(square, meta_upload=None)}}
    if main.kind == "video" and rules["family"] in ("meta", "linkedin"):
        return {"video": {"url": url}}
    # TikTok is video-only and Zernio's imageUrl carries the VIDEO URL there.
    return {"imageUrl": url}


# ---------------------------------------------------------------------------
# Create, validate, preview
# ---------------------------------------------------------------------------
def _create_payload(db: Session, tenant_id: str, payload: s.CampaignCreate) -> dict[str, Any]:
    rules, c = z.PLATFORMS[payload.platform], payload.creative
    family = rules["family"]
    body: dict[str, Any] = {
        "accountId": payload.account_id, "adAccountId": payload.ad_account_id, "name": payload.name,
        "goal": payload.goal, "budgetAmount": z.money(payload.budget.amount), "budgetType": payload.budget.type,
        "status": payload.status,
    }
    if family == "meta":  # Zernio: exact campaign / ad set names are Meta-only
        if payload.campaign_name:
            body["campaignName"] = payload.campaign_name
        if payload.ad_set_name:
            body["adSetName"] = payload.ad_set_name
    if payload.start_at:
        body["startDate"] = _iso(payload.start_at)
    if payload.end_at:
        body["endDate"] = _iso(payload.end_at)
    targeting = _targeting(payload.targeting)
    if targeting:
        body["targeting"] = targeting
    if payload.placements:
        p = payload.placements
        body["placements"] = {k: v for k, v in {
            "publisherPlatforms": p.publisher_platforms, "facebookPositions": p.facebook_positions,
            "instagramPositions": p.instagram_positions, "messengerPositions": p.messenger_positions,
            "audienceNetworkPositions": p.audience_network_positions, "threadsPositions": p.threads_positions,
            "whatsappPositions": p.whatsapp_positions, "devicePlatforms": p.device_platforms}.items() if v}
    if payload.special_ad_categories:
        body["specialAdCategories"] = payload.special_ad_categories
    for ours, theirs in (("headline", "headline"), ("long_headline", "longHeadline"), ("body", "body"),
                         ("description", "description"), ("call_to_action", "callToAction"), ("link_url", "linkUrl")):
        value = getattr(c, ours)
        if value:
            body[theirs] = value
    body.update(_media(db, tenant_id, payload))
    for ours, theirs in (("page_id", "pageId"), ("instagram_account_id", "instagramAccountId"),
                         ("identity_id", "identityId"), ("organization_id", "organizationId"), ("board_id", "boardId"),
                         ("lead_gen_form_id", "leadGenFormId")):
        value = getattr(payload, ours)
        if value:
            body[theirs] = value
    if payload.platform == "googleads":
        body["campaignType"] = payload.campaign_type
        if payload.keywords:
            body["keywords"] = [{"text": k.text, "matchType": k.match} for k in payload.keywords]
    if payload.promoted_object:
        po = payload.promoted_object
        promoted = {k: v for k, v in {"pixelId": po.pixel_id, "customEventType": po.custom_event_type,
                                       "customConversionId": po.custom_conversion_id, "applicationId": po.application_id,
                                       "objectStoreUrl": po.object_store_url}.items() if v}
        if promoted:
            body["promotedObject"] = promoted
    if payload.bid:
        bid = {"bidStrategy": payload.bid.strategy}
        if payload.bid.amount is not None:
            bid["bidAmount"] = z.money(payload.bid.amount)  # type: ignore[assignment]
        if payload.bid.roas_floor is not None:
            bid["roasAverageFloor"] = float(payload.bid.roas_floor)  # type: ignore[assignment]
        # Meta: the bid trio's preferred home is platformSpecificData; Google takes the flat fields.
        if family == "meta":
            body["platformSpecificData"] = bid
        else:
            body.update(bid)
    return body


def _check_ownership(db: Session, tenant_id: str, platform: str, account_id: str, ad_account_id: str) -> dict[str, Any]:
    _ads_account_for(db, tenant_id, platform, account_id)
    ad_account = _require_ad_account(account_id, ad_account_id)
    if ad_account.get("selectable") is False:
        reasons = ad_account.get("unusableReason")
        why = "; ".join(str(x) for x in reasons) if isinstance(reasons, list) and reasons else "it can't run ads right now"
        raise AppError(f"This ad account can't be used: {why}.", 422)
    return ad_account


def create_campaign(db: Session, tenant_id: str, actor: str, payload: s.CampaignCreate) -> dict[str, Any]:
    _check_ownership(db, tenant_id, payload.platform, payload.account_id, payload.ad_account_id)
    body = _create_payload(db, tenant_id, payload)
    key = f"{tenant_id}:{payload.request_id or uuid.uuid4().hex}"
    result = _call(z.create_ad, body, key)
    ad = result.get("ad") if isinstance(result.get("ad"), dict) else (
        (result.get("ads") or [None])[0] if isinstance(result.get("ads"), list) else None) or {}
    out = {
        "platform": payload.platform,
        "campaign_id": _str(ad.get("platformCampaignId")), "ad_set_id": _str(ad.get("platformAdSetId")),
        "ad_id": _str(ad.get("platformAdId") or ad.get("_id")),
        "status": _str(ad.get("status")), "review_status": _str(ad.get("reviewStatus")),
        "message": "Published: it runs once the platform approves it." if payload.status == "ACTIVE"
        else "Created paused: resume it from the Zernio tab when you're ready.",
    }
    if not _already_audited(db, tenant_id, "campaign_created", payload.request_id):
        _audit(db, tenant_id, actor, "campaign_created", platform=payload.platform, goal=payload.goal,
               status=payload.status, budget=str(payload.budget.amount), budget_type=payload.budget.type,
               campaign_id=out["campaign_id"], ad_account_id=payload.ad_account_id, request_id=payload.request_id)
    logger.info("zernio_campaign_created", tenant_id=tenant_id, platform=payload.platform, status=payload.status)
    return out


def validate_campaign(db: Session, tenant_id: str, payload: s.CampaignCreate) -> dict[str, Any]:
    _check_ownership(db, tenant_id, payload.platform, payload.account_id, payload.ad_account_id)
    if not z.PLATFORMS[payload.platform]["validate"]:
        return {"supported": False, "ok": True,
                "message": f"{z.PLATFORMS[payload.platform]['label']} has no dry run; it is checked when you publish."}
    body = _create_payload(db, tenant_id, payload)
    try:
        z.validate_ad(body)
    except z.ZernioError as exc:
        if exc.status_code in (422, 403):
            return {"supported": True, "ok": False, "message": exc.message}
        raise AppError(exc.message, exc.status_code) from None
    return {"supported": True, "ok": True, "message": "The platform accepted every part of this campaign."}


_PREVIEW_FORMATS = ["DESKTOP_FEED_STANDARD", "MOBILE_FEED_STANDARD", "INSTAGRAM_STANDARD", "INSTAGRAM_STORY"]


def preview(db: Session, tenant_id: str, payload: s.CampaignCreate) -> dict[str, Any]:
    """Meta image ads: Zernio renders Meta's /generatepreviews iframes."""
    rules = z.PLATFORMS[payload.platform]
    if not rules["preview"]:
        return {"supported": False, "items": []}
    _check_ownership(db, tenant_id, payload.platform, payload.account_id, payload.ad_account_id)
    media = _media(db, tenant_id, payload)
    if "imageUrl" not in media:
        return {"supported": False, "items": []}  # video previews need an uploaded video id
    page_id = payload.page_id or identities(db, tenant_id, payload.account_id, payload.ad_account_id)["default_page_id"]
    if not page_id:
        raise AppError("Choose the Facebook Page the ad runs as to see a preview.", 422)
    c = payload.creative
    link_data = {k: v for k, v in {"link": c.link_url, "message": c.body, "name": c.headline, "description": c.description,
                                    "picture": media["imageUrl"],
                                    "call_to_action": {"type": c.call_to_action} if c.call_to_action else None}.items() if v}
    spec = {"object_story_spec": {"page_id": page_id, "link_data": link_data}}
    rows = _call(z.preview, payload.account_id, payload.ad_account_id, spec, _PREVIEW_FORMATS)
    return {"supported": True, "items": [{"format": str(r.get("format") or ""), "html": _str(r.get("html"))} for r in rows]}


# ---------------------------------------------------------------------------
# Boost an existing post
# ---------------------------------------------------------------------------
def boost(db: Session, tenant_id: str, actor: str, payload: s.BoostCreate) -> dict[str, Any]:
    _require_account(db, tenant_id, payload.account_id, {POSTING_KIND[payload.platform]})
    pid = profile_id(db, tenant_id)
    # The ad account must be one this company's ads connection for the platform can see.
    ads_kind = z.PLATFORMS[payload.platform]["ads_account"]
    ads_accounts = [a for a in _accounts(pid) if a.get("platform") == ads_kind]
    if not any(any(str(r.get("id")) == payload.ad_account_id for r in _call(z.ad_accounts, str(a["_id"])))
               for a in ads_accounts):
        raise NotFoundError("Ad account not found.")
    body: dict[str, Any] = {
        "accountId": payload.account_id, "adAccountId": payload.ad_account_id, "platformPostId": payload.post_id,
        "name": payload.name, "goal": payload.goal, "budgetAmount": z.money(payload.budget.amount),
        "budgetType": payload.budget.type, "status": payload.status,
    }
    if payload.start_at:
        body["startDate"] = _iso(payload.start_at)
    if payload.end_at:
        body["endDate"] = _iso(payload.end_at)
    targeting = _targeting(payload.targeting)
    if targeting:
        body["targeting"] = targeting
    result = _call(z.boost, body, f"{tenant_id}:{payload.request_id or uuid.uuid4().hex}")
    ad = result.get("ad") if isinstance(result.get("ad"), dict) else {}
    out = {
        "platform": payload.platform, "campaign_id": _str(ad.get("platformCampaignId")),
        "ad_set_id": _str(ad.get("platformAdSetId")), "ad_id": _str(ad.get("platformAdId") or ad.get("_id")),
        "status": _str(ad.get("status")), "review_status": _str(ad.get("reviewStatus")),
        "message": "Boost published: it runs once the platform approves it." if payload.status == "ACTIVE"
        else "Boost created paused: resume it from the Zernio tab when you're ready.",
    }
    if not _already_audited(db, tenant_id, "post_boosted", payload.request_id):
        _audit(db, tenant_id, actor, "post_boosted", platform=payload.platform, goal=payload.goal, status=payload.status,
               budget=str(payload.budget.amount), post_id=payload.post_id, campaign_id=out["campaign_id"],
               request_id=payload.request_id)
    return out


# ---------------------------------------------------------------------------
# Campaign tree and management
# ---------------------------------------------------------------------------
def _metrics(m: Any) -> dict[str, Any] | None:
    if not isinstance(m, dict):
        return None
    return {"spend": _num(m.get("spend")), "impressions": _int(m.get("impressions")), "reach": _int(m.get("reach")),
            "clicks": _int(m.get("clicks")), "ctr": _num(m.get("ctr")), "cpc": _num(m.get("cpc")),
            "cpm": _num(m.get("cpm")), "conversions": _num(m.get("conversions")), "roas": _num(m.get("roas"))}


def _budget(b: Any) -> dict[str, Any] | None:
    return {"amount": _num(b.get("amount")), "type": _str(b.get("type"))} if isinstance(b, dict) else None


def _ad_out(a: dict[str, Any]) -> dict[str, Any]:
    return {"id": str(a.get("platformAdId") or a.get("_id") or a.get("id") or ""),
            "name": _str(a.get("name") or a.get("adName")), "status": _str(a.get("status")),
            "review_status": _str(a.get("reviewStatus")), "metrics": _metrics(a.get("metrics"))}


def _campaign_out(c: dict[str, Any]) -> dict[str, Any]:
    ad_sets = []
    for st in c.get("adSets") or []:
        if not isinstance(st, dict):
            continue
        ad_sets.append({
            "id": str(st.get("platformAdSetId") or ""), "name": _str(st.get("adSetName")), "status": _str(st.get("status")),
            "budget": _budget(st.get("adSetBudget") or st.get("budget")), "metrics": _metrics(st.get("metrics")),
            "ads": [_ad_out(a) for a in st.get("ads") or [] if isinstance(a, dict)],
        })
    return {
        "id": str(c.get("platformCampaignId") or ""), "platform": str(c.get("platform") or ""),
        "name": _str(c.get("campaignName")), "status": _str(c.get("status")), "review_status": _str(c.get("reviewStatus")),
        "objective": _str(c.get("platformObjective")), "budget": _budget(c.get("campaignBudget") or c.get("budget")),
        "currency": _str(c.get("currency")), "ad_account_id": _str(c.get("platformAdAccountId")),
        "ad_account_name": _str(c.get("platformAdAccountName")), "created_at": _ts(c.get("createdTime")),
        "metrics": _metrics(c.get("metrics")), "ad_sets": ad_sets,
    }


_RANGE_DAYS = {"7d": 7, "30d": 30, "90d": 90}


def _range(range_: str) -> tuple[str, str]:
    end = date.today()
    return (end - timedelta(days=_RANGE_DAYS[range_] - 1)).isoformat(), end.isoformat()


def list_campaigns(db: Session, tenant_id: str, platform: str | None, status_: str | None, q: str | None, page: int,
                   range_: str) -> dict[str, Any]:
    pid = profile_id(db, tenant_id)
    start, end = _range(range_)
    tree_platform = z.PLATFORMS[platform]["tree"] if platform else None
    body = _call(z.tree, pid, platform=tree_platform, status=status_, search=q, page=page, limit=20,
                 fromDate=start, toDate=end)
    # Only this profile's campaigns (the profileId filter is server-side; this is the belt and braces).
    items = [_campaign_out(c) for c in body.get("campaigns") or []
             if isinstance(c, dict) and c.get("platformCampaignId") and str(c.get("profileId") or pid) == pid]
    pg = body.get("pagination") if isinstance(body.get("pagination"), dict) else {}
    return {"items": items, "page": _int(pg.get("page")) or page, "pages": _int(pg.get("pages")) or 1,
            "total": _int(pg.get("total")) or len(items), "backfill_pending": bool(body.get("backfillPending"))}


def _find(db: Session, tenant_id: str, level: str, node_id: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """(campaign, ad set or ad) for an id in THIS company's tree; else 404."""
    pid = profile_id(db, tenant_id)
    params = {"campaignId": node_id} if level == "campaign" else {"search": node_id}
    body = _call(z.tree, pid, limit=100, **params)
    for c in body.get("campaigns") or []:
        if not isinstance(c, dict) or str(c.get("profileId") or pid) != pid:
            continue
        if level == "campaign" and str(c.get("platformCampaignId")) == node_id:
            return c, None
        for st in c.get("adSets") or []:
            if not isinstance(st, dict):
                continue
            if level == "ad_set" and str(st.get("platformAdSetId")) == node_id:
                return c, st
            if level == "ad":
                for a in st.get("ads") or []:
                    if isinstance(a, dict) and node_id in (str(a.get("platformAdId")), str(a.get("_id"))):
                        return c, a
    raise NotFoundError({"campaign": "Campaign", "ad_set": "Ad set", "ad": "Ad"}[level] + " not found.")


def set_status(db: Session, tenant_id: str, actor: str, level: str, node_id: str, action: str) -> dict[str, Any]:
    """Pause / resume one level. D3 = B: any manager+ may resume (no owner step)."""
    campaign, _ = _find(db, tenant_id, level, node_id)
    platform = str(campaign.get("platform") or "")
    target = "paused" if action == "pause" else "active"
    if level == "campaign":
        result = _call(z.set_campaign_status, node_id, platform, target)
    elif level == "ad_set":
        result = _call(z.set_ad_set_status, node_id, platform, target)
    else:
        result = _call(z.set_ad_status, node_id, target)
    _audit(db, tenant_id, actor, f"{level}_{'paused' if action == 'pause' else 'resumed'}", platform=platform,
           id=node_id, campaign_id=str(campaign.get("platformCampaignId")))
    skipped = result.get("skippedReasons") if isinstance(result.get("skippedReasons"), list) else []
    note = f" ({'; '.join(str(x) for x in skipped)})" if skipped else ""
    return {"status": _str(result.get("status") or result.get("configuredStatus")) or target,
            "message": f"{'Paused' if action == 'pause' else 'Resumed'}{note}."}


def update_campaign(db: Session, tenant_id: str, actor: str, campaign_id: str, payload: s.CampaignUpdate) -> dict[str, Any]:
    campaign, _ = _find(db, tenant_id, "campaign", campaign_id)
    platform = str(campaign.get("platform") or "")
    # Zernio's campaign update covers Meta and Google; other platforms change budgets per ad set.
    if platform not in ("facebook", "instagram", "google"):
        raise AppError("Zernio can change the name and budget here only for Facebook, Instagram and Google campaigns.", 422)
    body: dict[str, Any] = {"platform": platform}
    if payload.name:
        body["name"] = payload.name
    if payload.budget:
        body["budget"] = {"amount": z.money(payload.budget.amount), "type": payload.budget.type}
    _call(z.update_campaign, campaign_id, body)
    _audit(db, tenant_id, actor, "campaign_updated", platform=platform, campaign_id=campaign_id,
           budget=str(payload.budget.amount) if payload.budget else None, renamed=bool(payload.name))
    return _campaign_out(_find(db, tenant_id, "campaign", campaign_id)[0])


def delete_campaign(db: Session, tenant_id: str, actor: str, campaign_id: str) -> dict[str, Any]:
    campaign, _ = _find(db, tenant_id, "campaign", campaign_id)
    platform = str(campaign.get("platform") or "")
    result = _call(z.delete_campaign, campaign_id, platform)
    _audit(db, tenant_id, actor, "campaign_deleted", platform=platform, campaign_id=campaign_id)
    return {"deleted": bool(result.get("deleted", True)), "ad_count": _int(result.get("adCount"))}


def campaign_analytics(db: Session, tenant_id: str, campaign_id: str, range_: str, breakdowns: str | None) -> dict[str, Any]:
    campaign, _ = _find(db, tenant_id, "campaign", campaign_id)
    platform = str(campaign.get("platform") or "")
    start, end = _range(range_)
    # Demographic breakdowns are a Meta feature in Zernio.
    wanted = breakdowns if platform in ("facebook", "instagram") else None
    code, body = _call(z.campaign_analytics, campaign_id, platform, start, end, wanted)
    a: dict[str, Any] = body["analytics"] if isinstance(body.get("analytics"), dict) else {}
    daily = []
    for d in a.get("daily") or []:
        if isinstance(d, dict) and (d.get("date") or d.get("day")):
            dm: dict[str, Any] = d["metrics"] if isinstance(d.get("metrics"), dict) else d
            daily.append({"day": str(d.get("date") or d.get("day"))[:10], "spend": _num(dm.get("spend")),
                          "impressions": _int(dm.get("impressions")), "clicks": _int(dm.get("clicks")),
                          "conversions": _num(dm.get("conversions"))})
    rows = []
    raw: dict[str, Any] = a["breakdowns"] if isinstance(a.get("breakdowns"), dict) else {}
    for dimension, values in raw.items():
        for v in values if isinstance(values, list) else []:
            if not isinstance(v, dict):
                continue
            label = v.get("value") or v.get(dimension) or v.get("key")
            if label in (None, ""):
                continue
            bm: dict[str, Any] = v["metrics"] if isinstance(v.get("metrics"), dict) else v
            rows.append({"dimension": str(dimension), "value": str(label), "spend": _num(bm.get("spend")),
                         "impressions": _int(bm.get("impressions")), "clicks": _int(bm.get("clicks"))})
    c = body.get("campaign") if isinstance(body.get("campaign"), dict) else {}
    return {"campaign_id": campaign_id, "platform": platform, "currency": _str(c.get("currency") or campaign.get("currency")),
            "start": start, "end": end, "backfill_pending": code == 202 or bool(body.get("backfillPending")),
            "summary": _metrics(a.get("summary")), "daily": daily, "breakdowns": rows}
