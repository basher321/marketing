"""Social sign-in for organic posting (SPEC-BE-080).

Flows: "meta" (a Facebook Page and its linked Instagram account), "tiktok",
"linkedin" (a company page). connect -> the platform's dialog -> the frontend
callback page posts {code, state} -> callback exchanges the code server to
server -> (meta / linkedin) the user picks the account -> select saves it.

The result is stored by integration_service.save_oauth_credentials in the same
shape as a pasted token, so publishing and analytics don't change. Tokens are
encrypted, never returned, logged or audited. The state is a signed JWT bound
to tenant + user + flow with a single-use nonce on the flow's integration row,
like "Connect with Facebook" (SPEC-BE-054).

Refresh: TikTok access tokens last 24 h and LinkedIn's 60 days. ensure_fresh()
renews one before use and the social_token_refresh job renews those close to
expiry. A refresh is committed in its own session (row locked), so a failed
publish can't roll back a rotated refresh token and two workers can't spend
the same refresh token twice.
"""
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from cryptography.fernet import InvalidToken
from jose import JWTError, jwt  # type: ignore[import-untyped]  # no stubs (baseline, as core/security.py)
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.audit import write_audit_log
from app.core.exceptions import AppError
from app.integrations import facebook, linkedin, tiktok
from app.integrations.social_base import SocialError
from app.models.integration import Integration
from app.services import integration_service as integrations
from app.utils.crypto import decrypt_secret, encrypt_secret

logger = structlog.get_logger(__name__)

# flow -> (the integration row holding the nonce / pending choices, module, label)
FLOWS: dict[str, tuple[str, Any, str]] = {
    "meta": ("facebook", facebook, "Facebook"),
    "tiktok": ("tiktok", tiktok, "TikTok"),
    "linkedin": ("linkedin", linkedin, "LinkedIn"),
}
# Which flow connects each social platform (Instagram comes with its Page).
PLATFORM_FLOW = {"facebook": "meta", "instagram": "meta", "tiktok": "tiktok", "linkedin": "linkedin"}
REFRESHABLE = {"tiktok": tiktok, "linkedin": linkedin}
STATE_TTL = timedelta(minutes=10)
STATE_TYPE = "social_oauth"
BAD_STATE = "This sign-in link expired or is invalid; start Connect again."
REFRESH_SKEW = timedelta(minutes=5)
# The job's look-ahead: TikTok tokens last a day, LinkedIn's 60 days.
JOB_WINDOW = {"tiktok": timedelta(hours=2), "linkedin": timedelta(days=7)}


def _flow(flow: str) -> tuple[str, Any, str]:
    if flow not in FLOWS:
        raise AppError("Unknown sign-in.", 404)
    return FLOWS[flow]


def oauth_available(platform: str) -> bool:
    return bool(FLOWS[PLATFORM_FLOW[platform]][1].oauth_configured())


def _require(flow: str) -> tuple[str, Any, str]:
    provider, module, label = _flow(flow)
    if not module.oauth_configured():
        raise AppError(f"{label} sign-in isn't set up on this server; paste a token in Integrations instead.", 503)
    return provider, module, label


def redirect_uri(flow: str) -> str:
    # Must be registered exactly in the platform's developer app.
    return get_settings().FRONTEND_BASE_URL.rstrip("/") + f"/marketing/organic/accounts/callback/{flow}"


def _row(db: Session, tenant_id: str, actor_user_id: str, provider: str) -> Integration:
    record = integrations._primary(integrations._records(db, tenant_id, provider))
    if record is None:
        record = Integration(
            tenant_id=tenant_id, provider=provider, status="disconnected", credentials_ref="",
            connected_by=actor_user_id,
            # NOT NULL live; reset to the real time when the connection is made.
            connected_at=datetime.now(timezone.utc),
        )
        db.add(record)
        db.flush()
    return record


def connect_url(db: Session, tenant_id: str, actor_user_id: str, flow: str) -> dict[str, Any]:
    provider, module, _ = _require(flow)
    record = _row(db, tenant_id, actor_user_id, provider)
    nonce = secrets.token_urlsafe(16)
    settings = dict(record.settings or {})
    settings["oauth_nonce"] = nonce
    record.settings = settings
    s = get_settings()
    claims = {"typ": STATE_TYPE, "f": flow, "t": str(tenant_id), "u": str(actor_user_id), "n": nonce,
              "exp": datetime.now(timezone.utc) + STATE_TTL}
    state = jwt.encode(claims, s.SECRET_KEY.get_secret_value(), algorithm=s.JWT_ALGORITHM)
    db.commit()
    return {"login_url": module.login_url(redirect_uri(flow), state)}


def _check_state(record: Integration | None, tenant_id: str, actor_user_id: str, flow: str, state: str) -> None:
    s = get_settings()
    try:
        claims = jwt.decode(state, s.SECRET_KEY.get_secret_value(), algorithms=[s.JWT_ALGORITHM])
    except JWTError:
        raise AppError(BAD_STATE, 400) from None
    expected = (record.settings or {}).get("oauth_nonce") if record else None
    if (
        claims.get("typ") != STATE_TYPE
        or claims.get("f") != flow
        or claims.get("t") != str(tenant_id)
        or claims.get("u") != str(actor_user_id)
        or not expected
        or claims.get("n") != expected
    ):
        raise AppError(BAD_STATE, 400)


def _platform_error(exc: SocialError) -> AppError:
    # A rejected code / grant is the user's to retry (400); a platform outage 502.
    return AppError(exc.message, 502 if exc.transient else 400)


def _token_oauth(token: dict[str, Any], account_id: str | None) -> dict[str, Any]:
    return {"scopes": token.get("scopes") or [], "access_expires_at": token.get("access_expires_at"),
            "refresh_expires_at": token.get("refresh_expires_at"), "external_account_id": account_id}


def callback(db: Session, tenant_id: str, actor_user_id: str, flow: str, code: str, state: str) -> dict[str, Any]:
    provider, module, label = _require(flow)
    record = integrations._primary(integrations._records(db, tenant_id, provider))
    _check_state(record, tenant_id, actor_user_id, flow, state)
    assert record is not None  # _check_state needs the row holding the nonce
    settings = dict(record.settings or {})
    settings.pop("oauth_nonce", None)  # consumed, even if the exchange fails
    record.settings = settings
    db.commit()

    uri = redirect_uri(flow)
    try:
        if flow == "tiktok":
            token = tiktok.exchange_code(code, uri)
            result = integrations.save_oauth_credentials(
                db, tenant_id, actor_user_id, "tiktok", {},
                {"access_token": token["access_token"], "refresh_token": token["refresh_token"]},
                _token_oauth(token, token.get("account_id")),
            )
            logger.info("social_oauth_saved", tenant_id=tenant_id, flow=flow, verified=result["ok"])
            return {"flow": flow, "saved": True, "ok": bool(result["ok"]), "message": result["message"], "choices": [],
                    "scopes": token.get("scopes") or []}
        if flow == "meta":
            data = facebook.exchange_code(code, uri)
            pending: dict[str, Any] = {"pages": data["pages"], "scopes": data["scopes"]}
            choices = [{"id": p["id"], "name": p["name"], "handle": None, "avatar_url": p.get("avatar_url"),
                        "instagram": {"id": p["instagram"]["id"], "username": p["instagram"].get("username")} if p.get("instagram") else None}
                       for p in data["pages"]]
            scopes = data["scopes"]
            if not choices:
                raise AppError("This Facebook sign-in gave access to no Page. Sign in again and select your Page.", 422)
        else:
            token = linkedin.exchange_code(code, uri)
            orgs = linkedin.list_organizations(token["access_token"])
            if not orgs:
                raise AppError("This LinkedIn account doesn't administer a company page.", 422)
            pending = {"token": token, "orgs": orgs}
            choices = [{**o, "instagram": None} for o in orgs]
            scopes = token.get("scopes") or []
    except SocialError as exc:
        raise _platform_error(exc) from None

    settings = dict(record.settings or {})
    # Held encrypted until select (it contains tokens); the current connection keeps working.
    settings["oauth_pending"] = {"flow": flow, "enc": encrypt_secret(json.dumps(pending)),
                                 "created_at": datetime.now(timezone.utc).isoformat()}
    record.settings = settings
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor_user_id, action="integration.oauth_callback",
                    resource_type="integration", resource_id=str(record.id),
                    metadata={"flow": flow, "choices": len(choices), "scopes": scopes[:20]})
    logger.info("social_oauth_callback", tenant_id=tenant_id, flow=flow, choices=len(choices))
    return {"flow": flow, "saved": False, "ok": True, "message": f"Choose the {label} account to connect.", "choices": choices,
            "scopes": scopes}


def _pending(record: Integration | None, flow: str) -> dict[str, Any]:
    raw = ((record.settings or {}).get("oauth_pending") if record else None) or {}
    if not raw or raw.get("flow") != flow:
        raise AppError("Start Connect again; there's nothing to choose from.", 409)
    try:
        return dict(json.loads(decrypt_secret(raw["enc"])))
    except (InvalidToken, ValueError, KeyError):
        raise AppError("Start Connect again; the sign-in couldn't be read.", 409) from None


def select(db: Session, tenant_id: str, actor_user_id: str, flow: str, account_id: str, include_instagram: bool) -> dict[str, Any]:
    provider, _, label = _flow(flow)
    if flow == "tiktok":
        raise AppError("TikTok is saved at sign-in; there's nothing to choose.", 409)
    record = integrations._primary(integrations._records(db, tenant_id, provider))
    pending = _pending(record, flow)
    saved: list[str] = []
    messages: list[str] = []
    ok = True
    if flow == "meta":
        page = next((p for p in pending.get("pages") or [] if p["id"] == account_id), None)
        if page is None:
            raise AppError("Pick a Page from the list Facebook returned.", 422)
        scopes = pending.get("scopes") or []
        # A Page token from a long-lived user token doesn't expire: no expiry, no refresh.
        no_expiry = {"scopes": scopes, "access_expires_at": None, "refresh_expires_at": None}
        fb = integrations.save_oauth_credentials(db, tenant_id, actor_user_id, "facebook", {"page_id": page["id"]},
                                                 {"access_token": page["token"]}, {**no_expiry, "external_account_id": page["id"]},
                                                 account_name=page["name"])
        saved.append("facebook")
        ok = ok and bool(fb["ok"])
        messages.append("Facebook Page connected." if fb["ok"] else f"Facebook: {fb['message']}")
        ig = page.get("instagram")
        if include_instagram and ig:
            res = integrations.save_oauth_credentials(db, tenant_id, actor_user_id, "instagram", {"ig_account_id": ig["id"]},
                                                      {"access_token": page["token"]}, {**no_expiry, "external_account_id": ig["id"]},
                                                      account_name=ig.get("username"))
            saved.append("instagram")
            ok = ok and bool(res["ok"])
            messages.append("Instagram connected." if res["ok"] else f"Instagram: {res['message']}")
    else:
        org = next((o for o in pending.get("orgs") or [] if o["id"] == account_id), None)
        if org is None:
            raise AppError("Pick a company page from the list LinkedIn returned.", 422)
        token = pending["token"]
        res = integrations.save_oauth_credentials(db, tenant_id, actor_user_id, "linkedin", {"organization_urn": org["id"]},
                                                  {"access_token": token["access_token"], "refresh_token": token.get("refresh_token") or ""},
                                                  _token_oauth(token, org["id"]), account_name=org["name"])
        saved.append("linkedin")
        ok = bool(res["ok"])
        messages.append(f"{label} page connected." if res["ok"] else f"{label}: {res['message']}")
    logger.info("social_oauth_selected", tenant_id=tenant_id, flow=flow, saved=saved, ok=ok)
    return {"saved": saved, "ok": ok, "message": " ".join(messages)}


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------
def _needs_refresh(record: Integration | None, within: timedelta) -> bool:
    if record is None or record.status == "disconnected" or record.provider not in REFRESHABLE:
        return False
    oauth = (record.settings or {}).get("oauth") or {}
    if oauth.get("via") != "oauth" or not oauth.get("has_refresh") or not oauth.get("access_expires_at"):
        return False
    if not REFRESHABLE[record.provider].oauth_configured():
        return False
    expires = datetime.fromisoformat(oauth["access_expires_at"]).astimezone(timezone.utc)
    return expires <= datetime.now(timezone.utc) + within


def _refresh_locked(own: Session, record_id: str, within: timedelta) -> str:
    """Refresh one integration under a row lock; 'refreshed' | 'skipped' |
    'retry' (network / platform outage) | 'expired' (grant rejected)."""
    record = own.query(Integration).filter(Integration.id == record_id).with_for_update().first()
    refresh_token = integrations._secrets(record).get("refresh_token") if _needs_refresh(record, within) else None
    if record is None or not refresh_token:
        own.rollback()  # releases the row lock
        return "skipped"
    try:
        token = REFRESHABLE[record.provider].refresh(refresh_token)
    except SocialError as exc:
        if exc.transient:
            own.rollback()
            return "retry"
        record.status = "expired"
        record.last_error = exc.message[:500]
        own.commit()
        logger.warning("social_token_refresh_rejected", tenant_id=str(record.tenant_id), provider=record.provider)
        return "expired"
    integrations.store_refreshed_token(record, token)
    own.commit()
    logger.info("social_token_refreshed", tenant_id=str(record.tenant_id), provider=record.provider)
    return "refreshed"


def ensure_fresh(db: Session, tenant_id: str, platform: str, within: timedelta = REFRESH_SKEW) -> str:
    """Before an adapter call: renew the access token when it expires within
    `within`. Committed in its own session on the same bind."""
    record = integrations._primary(integrations._records(db, tenant_id, platform))
    if not _needs_refresh(record, within):
        return "skipped"
    assert record is not None
    with Session(bind=db.get_bind(), join_transaction_mode="create_savepoint") as own:
        outcome = _refresh_locked(own, str(record.id), within)
    db.refresh(record)
    return outcome


def refresh_due_tokens() -> dict[str, int]:
    """The social_token_refresh job: every OAuth TikTok / LinkedIn connection
    whose access token expires inside its window. One failure never stops the rest."""
    from app.db.session import SessionLocal

    counts = {"refreshed": 0, "skipped": 0, "retry": 0, "expired": 0}
    db = SessionLocal()
    try:
        rows = db.query(Integration.id, Integration.provider).filter(
            Integration.provider.in_(tuple(REFRESHABLE)), Integration.status != "disconnected").all()
        for record_id, provider in rows:
            try:
                counts[_refresh_locked(db, str(record_id), JOB_WINDOW[provider])] += 1
            except Exception:
                db.rollback()
                counts["retry"] += 1
                logger.exception("social_token_refresh_failed", integration_id=str(record_id))
    finally:
        db.close()
    return counts
