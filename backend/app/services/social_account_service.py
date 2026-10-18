"""Connected social accounts (SPEC-BE-075).

The accounts are the tenant's facebook / instagram / tiktok / linkedin
integrations (pasted tokens, SPEC-BE-052, or a sign-in, SPEC-BE-080). Profile, permissions and limits
come from the last connection test (integrations.metadata.profile), not from
a platform call per list. `connection()` hands an adapter its decrypted
credentials; they are never returned to a client.

SPEC-BE-104: when a platform has no usable direct connection (not connected,
expired or error) but the company has a SocialAPI account for it, that account
is the platform's account (`connected_via: "socialapi"`) and `connection()`
returns `via: "socialapi"`, which social_base.adapter() turns into the SocialAPI
publisher. A direct connection always comes first.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, ConflictError
from app.integrations import verify
from app.integrations.meta_ads import graph_base
from app.integrations.social_base import PLATFORMS, SocialError, call
from app.models.integration import Integration
from app.models.scheduled_post import ScheduledPost
from app.schemas.integration import IntegrationSave
from app.services import integration_service as integrations
from app.services import social_oauth_service

logger = structlog.get_logger(__name__)

LABEL = {"facebook": "Facebook Page", "instagram": "Instagram", "tiktok": "TikTok", "linkedin": "LinkedIn Page"}
DEFAULT_CAPABILITIES = {
    "facebook": {"text_only": True, "image": True, "carousel": True, "video": True, "story": False, "reel": True},
    "instagram": {"text_only": False, "image": True, "carousel": True, "video": True, "story": True, "reel": True},
    "tiktok": {"text_only": False, "image": True, "carousel": True, "video": True, "story": False, "reel": False},
    "linkedin": {"text_only": True, "image": True, "carousel": True, "video": True, "story": False, "reel": False},
}
NOTES = {
    "tiktok": ["Until TikTok audits your developer app, posts made through the API are private (only you can see them)."],
    "instagram": ["Instagram fetches media from a public https address: set PUBLIC_BASE_URL (or use S3 storage)."],
    "linkedin": ["Posting as a company page needs LinkedIn's Community Management API access."],
    "facebook": [],
}


# Connection details (SPEC-BE-080, item 12): how it was connected, the
# account id, granted scopes, token status and the last check / results sync.
ACCOUNT_FIELD = {"facebook": "page_id", "instagram": "ig_account_id", "tiktok": "", "linkedin": "organization_urn"}
EXPIRING_REFRESH = timedelta(days=7)
EXPIRING_ACCESS = timedelta(hours=24)
_NO_TOKEN_INFO: dict[str, Any] = {
    "connected_via": None, "account_id": None, "scopes": [], "token_status": None, "token_expires_at": None,
    "reconnect_by": None, "last_checked_at": None, "last_synced_at": None,
}


def _iso_utc(raw: Any) -> datetime | None:
    return datetime.fromisoformat(raw).astimezone(timezone.utc) if raw else None


def _token_info(record: Integration, platform: str, state: str, now: datetime) -> dict[str, Any]:
    oauth = dict((record.settings or {}).get("oauth") or {})
    via = "oauth" if oauth.get("via") == "oauth" else "token"
    access, refresh = _iso_utc(oauth.get("access_expires_at")), _iso_utc(oauth.get("refresh_expires_at"))
    has_refresh = bool(oauth.get("has_refresh"))
    if via == "token":
        token_status = "unknown"  # a pasted token's lifetime isn't known
    elif state == "expired" or (record.expires_at is not None and record.expires_at <= now):
        token_status = "expired"
    elif access is None and refresh is None:
        token_status = "no_expiry"
    elif (has_refresh and refresh is not None and refresh - now < EXPIRING_REFRESH) or (
        not has_refresh and access is not None and access - now < EXPIRING_ACCESS
    ):
        token_status = "expiring_soon"
    else:
        token_status = "valid"
    key = ACCOUNT_FIELD[platform]
    return {
        "connected_via": via,
        "account_id": oauth.get("external_account_id") or (integrations._fields(record).get(key) if key else None) or None,
        "scopes": list(oauth.get("scopes") or []),
        "token_status": token_status,
        "token_expires_at": access,
        "reconnect_by": refresh if has_refresh else access,
        "last_checked_at": integrations._verified_at(record),
        "last_synced_at": record.last_sync_at.astimezone(timezone.utc) if record.last_sync_at else None,
    }


SOCIALAPI_NOTE = "Posts through SocialAPI (connected in Organic › SocialAPI)."


def _socialapi_account(platform: str, a: dict[str, Any], last: datetime | None) -> dict[str, Any]:
    from app.services import socialapi_service

    problem = socialapi_service.organic_problem(a)
    capabilities = dict(DEFAULT_CAPABILITIES[platform])
    if platform == "instagram":
        capabilities["story"] = False  # no documented story option in SocialAPI's post API
    return {
        **_NO_TOKEN_INFO,
        "connected_via": "socialapi",
        "account_id": a.get("id"),
        "oauth_available": social_oauth_service.oauth_available(platform),
        "integration_id": None,
        "platform": platform,
        "label": LABEL[platform],
        "account_name": a.get("page_name") or a.get("name"),
        "handle": a.get("username"),
        "avatar_url": a.get("avatar_url"),
        "status": "error" if problem else "connected",
        "missing_permissions": [],
        "capabilities": capabilities,
        "limits": {},
        "extra": {},
        "last_error": problem,
        "last_published_at": last,
        "notes": [SOCIALAPI_NOTE],
    }


def _account(db: Session, tenant_id: str, platform: str, now: datetime) -> dict[str, Any]:
    records = integrations._records(db, tenant_id, platform)
    status, _ = integrations._provider_status(records, now)
    record = integrations._primary(records)
    profile = dict(((record.extra_metadata or {}).get("profile") if record else None) or {})
    missing = list(profile.get("missing_permissions") or [])
    if status == "not_connected" or record is None:
        state = "not_connected"
    elif status == "connected":
        state = "missing_permissions" if missing else "connected"
    else:
        state = "expired" if record.status == "expired" else "error"
    last = db.query(func.max(ScheduledPost.published_at)).filter(
        ScheduledPost.tenant_id == tenant_id, ScheduledPost.channel == platform, ScheduledPost.status == "published"
    ).scalar()
    if state in ("not_connected", "expired", "error"):
        from app.services import socialapi_service

        via_sapi = socialapi_service.organic_accounts(db, tenant_id).get(platform)
        if via_sapi is not None:
            return _socialapi_account(platform, via_sapi, last.astimezone(timezone.utc) if last else None)
    connected = state != "not_connected" and record is not None
    return {
        **(_token_info(record, platform, state, now) if connected and record is not None else _NO_TOKEN_INFO),
        "oauth_available": social_oauth_service.oauth_available(platform),
        "integration_id": str(record.id) if record and state != "not_connected" else None,
        "platform": platform,
        "label": LABEL[platform],
        "account_name": (profile.get("account_name") or (record.account_name if record else None)) if state != "not_connected" else None,
        "handle": profile.get("handle") if state != "not_connected" else None,
        "avatar_url": profile.get("avatar_url") if state != "not_connected" else None,
        "status": state,
        "missing_permissions": missing,
        "capabilities": dict(profile.get("capabilities") or DEFAULT_CAPABILITIES[platform]),
        "limits": dict(profile.get("limits") or {}),
        "extra": dict(profile.get("extra") or {}),
        "last_error": record.last_error if record and state != "not_connected" else None,
        "last_published_at": last.astimezone(timezone.utc) if last else None,
        "notes": NOTES[platform],
    }


def list_accounts(db: Session, tenant_id: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {"items": [_account(db, tenant_id, p, now) for p in PLATFORMS]}


def account(db: Session, tenant_id: str, platform: str) -> dict[str, Any]:
    return _account(db, tenant_id, platform, datetime.now(timezone.utc))


def connection(db: Session, tenant_id: str, platform: str) -> dict[str, Any]:
    """{integration_id, fields} for an adapter; ConflictError when the account
    isn't connected (the scheduler turns it into a failed post). An OAuth
    token about to expire is refreshed first (SPEC-BE-080)."""
    social_oauth_service.ensure_fresh(db, tenant_id, platform)
    conn = integrations.ad_platform_connection(db, tenant_id, platform)
    if conn is not None and conn["status"] == "connected":
        return {"integration_id": conn["integration_id"], "fields": conn["fields"], "via": "direct"}
    from app.services import socialapi_service

    account = socialapi_service.organic_accounts(db, tenant_id).get(platform)
    if account is None:
        raise ConflictError(f"{LABEL[platform]} isn't connected: connect it in Organic › SocialAPI.")
    problem = socialapi_service.organic_problem(account)
    if problem:
        raise ConflictError(f"{LABEL[platform]} (SocialAPI) can't post yet: {problem}")
    return {"integration_id": None, "via": "socialapi",
            "fields": {"key": socialapi_service.organic_key(db, tenant_id), "account_id": str(account["id"]), "platform": platform}}


def mark_expired(db: Session, tenant_id: str, platform: str, message: str) -> None:
    integrations.mark_ad_platform_expired(db, tenant_id, platform, message)


def use_meta_connection(db: Session, tenant_id: str, actor_user_id: str) -> dict[str, Any]:
    """Fill the Facebook (and Instagram) social integrations from the Meta Ads
    connection: the Page token comes from GET /{page_id}?fields=access_token.
    Works only when that token may manage the Page; otherwise the reason."""
    meta = integrations.meta_publish_credentials(db, tenant_id)
    if meta is None or meta["status"] != "connected" or not meta.get("page_id"):
        raise AppError("Connect Meta Ads with a Facebook Page first (Integrations › Meta Ads Manager).", 409)
    try:
        page = call("facebook", "GET", f"{graph_base()}/{meta['page_id']}",
                    params={"fields": "access_token,name", "access_token": meta["access_token"]}).json()
    except SocialError as exc:
        raise AppError(f"The Meta connection can't manage the Page: {exc.message}", 409) from None
    page_token = page.get("access_token")
    if not page_token:
        raise AppError("The Meta connection didn't return a Page token (it needs pages_manage_posts on the Page).", 409)
    fb = integrations.save_credentials(db, tenant_id, actor_user_id, "facebook",
                                       IntegrationSave(account_name=page.get("name"), fields={"page_id": meta["page_id"], "access_token": page_token}))
    ig_ok = False
    if meta.get("instagram_id"):
        ig = integrations.save_credentials(db, tenant_id, actor_user_id, "instagram",
                                           IntegrationSave(fields={"ig_account_id": meta["instagram_id"], "access_token": page_token}))
        ig_ok = bool(ig["ok"])
    message = "Facebook Page connected" if fb["ok"] else f"Facebook: {fb['message']}"
    if meta.get("instagram_id"):
        message += "; Instagram connected." if ig_ok else "; Instagram couldn't be verified with this token."
    logger.info("social_from_meta", tenant_id=tenant_id, facebook=fb["ok"], instagram=ig_ok)
    return {"facebook": bool(fb["ok"]), "instagram": ig_ok, "message": message}


def refresh_profile(db: Session, tenant_id: str, platform: str) -> dict[str, Any] | None:
    """Re-run the adapter's check (used before validating TikTok privacy)."""
    record = integrations._primary(integrations._records(db, tenant_id, platform))
    if record is None:
        return None
    result = verify.verify(platform, {**integrations._fields(record), **integrations._secrets(record)})
    if result.ok and result.profile is not None:
        meta = dict(record.extra_metadata or {})
        meta["profile"] = result.profile
        record.extra_metadata = meta
    return result.profile
