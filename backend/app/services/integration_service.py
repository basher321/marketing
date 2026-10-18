"""Integrations: connection status (SPEC-BE-017) and in-app credentials with
connect / test / disconnect (SPEC-BE-052)."""
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from cryptography.fernet import InvalidToken
from jose import JWTError, jwt  # type: ignore[import-untyped]  # no stubs (baseline, as core/security.py)
from sqlalchemy import column, select, table, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.audit import write_audit_log
from app.core.exceptions import AppError, NotFoundError
from app.integrations import meta_ads
from app.integrations import verify as verifier
from app.models.integration import Integration
from app.schemas.integration import IntegrationSave
from app.utils.crypto import decrypt_secret, encrypt_secret

logger = structlog.get_logger(__name__)

# The credentials blob lives in settings["secrets_enc"]; credentials_ref is
# varchar(255) NOT NULL live, so it only holds this reference ("" = none).
CREDENTIALS_REF = "app:settings.secrets_enc"
CATEGORY_ORDER = ("Ads", "Social", "Messaging", "Email", "Commerce", "CRM")


def _is_expired(record: Integration, now: datetime) -> bool:
    # expires_at NULL = never-expiring credential, so NOT expired.
    return record.expires_at is not None and record.expires_at <= now


def _provider_status(records: list[Integration], now: datetime) -> tuple[str, datetime | None]:
    # Three-way status rule (SPEC-BE-017), per provider, over this tenant's
    # records for it (a tenant may have several accounts per provider):
    #   connected       - at least one record with status 'connected' whose
    #                     credential is not expired (expires_at NULL or > now).
    #   needs_reconnect - records exist but none qualifies as connected, and at
    #                     least one is status 'expired'/'error' or has
    #                     expires_at <= now.
    #   not_connected   - no records, or only records with status
    #                     'disconnected' (explicitly disconnected by the user).
    # last_synced_at is the latest last_sync_at among the qualifying connected
    # records (UTC), None if never synced; it is always None for
    # needs_reconnect and not_connected - never fabricated.
    active = [r for r in records if r.status != "disconnected"]
    connected = [r for r in active if r.status == "connected" and not _is_expired(r, now)]
    if connected:
        synced = [r.last_sync_at for r in connected if r.last_sync_at is not None]
        return "connected", (max(synced).astimezone(timezone.utc) if synced else None)
    if active:
        return "needs_reconnect", None
    return "not_connected", None


def _secrets(record: Integration | None) -> dict[str, str]:
    blob = ((record.settings or {}).get("secrets_enc") if record else None) or ""
    if not blob:
        return {}
    try:
        return dict(json.loads(decrypt_secret(blob)))
    except (InvalidToken, ValueError):
        # A key rotated or corrupted blob: treat as not configured.
        logger.warning("integration_secrets_unreadable", integration_id=str(record.id) if record else None)
        return {}


def _fields(record: Integration | None) -> dict[str, str]:
    return dict(((record.settings or {}).get("fields") if record else None) or {})


def _mask(value: str) -> str:
    return "••••" + value[-4:] if len(value) >= 8 else "••••"


def _primary(records: list[Integration]) -> Integration | None:
    # The record the page manages: newest non-disconnected one, else the newest.
    ordered = sorted(records, key=lambda r: r.updated_at or r.created_at, reverse=True)
    active = [r for r in ordered if r.status != "disconnected"]
    candidates = active or ordered
    return candidates[0] if candidates else None


def _verified_at(record: Integration | None) -> datetime | None:
    raw = ((record.extra_metadata or {}).get("verified_at") if record else None)
    return datetime.fromisoformat(raw).astimezone(timezone.utc) if raw else None


def _card(provider: verifier.Provider, records: list[Integration], now: datetime) -> dict[str, Any]:
    status, last_synced_at = _provider_status(records, now)
    record = _primary(records)
    fields, secrets = _fields(record), _secrets(record)
    masked = {k: v for k, v in fields.items() if v}
    masked.update({k: _mask(v) for k, v in secrets.items() if v})
    return {
        "provider": provider.provider,
        "name": provider.label,
        "category": provider.category,
        "status": status,
        "last_synced_at": last_synced_at,
        "account_name": record.account_name if record and status != "not_connected" else None,
        "configured_fields": [f.key for f in provider.fields if masked.get(f.key)],
        "masked": masked,
        "last_error": record.last_error if record and status != "not_connected" else None,
        "verified_at": _verified_at(record) if status != "not_connected" else None,
    }


def _records(db: Session, tenant_id: str, provider: str | None = None) -> list[Integration]:
    query = db.query(Integration).filter(Integration.tenant_id == tenant_id)
    if provider:
        query = query.filter(Integration.provider == provider)
    return query.all()


def list_integration_statuses(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    by_provider: dict[str, list[Integration]] = {}
    for record in _records(db, tenant_id):
        by_provider.setdefault(record.provider, []).append(record)
    providers = sorted(verifier.CATALOG, key=lambda p: CATEGORY_ORDER.index(p.category))
    result = [_card(p, by_provider.get(p.provider, []), now) for p in providers]
    logger.info(
        "integration_statuses_listed",
        tenant_id=tenant_id,
        connected=sum(1 for r in result if r["status"] == "connected"),
    )
    return result


# SPEC-BE-101 FR5: companies connect these (sign-in button, Zernio or SocialAPI);
# they never paste a token. An existing pasted connection keeps working.
CONNECT_ONLY = ("facebook", "instagram", "tiktok", "linkedin", "meta_ads", "tiktok_ads", "google_ads", "linkedin_ads",
                "x_ads", "snapchat_ads", "pinterest_ads")
CONNECT_ONLY_MESSAGE = "Connect your page with the Connect button, or through Zernio / SocialAPI; PilotSonic doesn't take pasted tokens."


def catalog() -> list[dict[str, Any]]:
    return [
        {
            "provider": p.provider,
            "label": p.label,
            "category": p.category,
            "fields": [
                {"key": f.key, "label": f.label, "secret": f.secret, "required": f.required, "help": f.help}
                for f in p.fields
            ],
            "test": True,
            "docs_url": p.docs_url,
            "connect_only": p.provider in CONNECT_ONLY,
        }
        for p in sorted(verifier.CATALOG, key=lambda p: CATEGORY_ORDER.index(p.category))
    ]


def _provider(provider: str) -> verifier.Provider:
    spec = verifier.BY_PROVIDER.get(provider)
    if spec is None:
        raise NotFoundError("Unknown integration.")
    return spec


def _apply_test(db: Session, record: Integration, spec: verifier.Provider, now: datetime) -> verifier.VerifyResult:
    values = {**_fields(record), **_secrets(record)}
    result = verifier.verify(spec.provider, values)
    record.status = "connected" if result.ok else "error"
    record.last_error = None if result.ok else result.message
    # Pasted credentials never expire here; an OAuth connection (SPEC-BE-080)
    # lives until its refresh token (or, without one, its access token) expires.
    record.expires_at = oauth_expiry((record.settings or {}).get("oauth"))
    if result.ok:
        meta = dict(record.extra_metadata or {})
        meta["verified_at"] = now.isoformat()
        record.extra_metadata = meta
        if result.account_name and not record.account_name:
            record.account_name = result.account_name[:255]
        if result.profile is not None:
            # Social accounts (SPEC-BE-075): shown on Organic › Accounts
            # without calling the platform on every list.
            meta["profile"] = result.profile
            record.extra_metadata = meta
    return result


def _result(record: Integration, result: verifier.VerifyResult, now: datetime) -> dict[str, Any]:
    status, _ = _provider_status([record], now)
    return {
        "status": status,
        "ok": result.ok,
        "message": result.message,
        "last_error": record.last_error,
        "verified_at": _verified_at(record),
        "account_name": record.account_name,
    }


def save_credentials(
    db: Session, tenant_id: str, actor_user_id: str, provider: str, payload: IntegrationSave
) -> dict[str, Any]:
    spec = _provider(provider)
    known = {f.key for f in spec.fields}
    unknown = sorted(set(payload.fields) - known)
    if unknown:
        raise AppError(f"Unknown fields for {spec.label}: {', '.join(unknown)}.", 422)

    record = _primary(_records(db, tenant_id, provider))
    fields, secrets = _fields(record), _secrets(record)
    for f in spec.fields:
        if f.key not in payload.fields:
            continue
        value = payload.fields[f.key].strip()
        if f.secret:
            if value:  # empty = keep the saved secret
                secrets[f.key] = value
        else:
            fields[f.key] = value
    missing = [f.label for f in spec.fields if f.required and not (fields.get(f.key) or secrets.get(f.key))]
    if missing:
        raise AppError(f"Required: {', '.join(missing)}.", 422)

    now = datetime.now(timezone.utc)
    if record is None:
        record = Integration(tenant_id=tenant_id, provider=provider, status="error")
        db.add(record)
    settings = dict(record.settings or {})
    settings["fields"] = fields
    settings["secrets_enc"] = encrypt_secret(json.dumps(secrets))
    record.settings = settings
    record.credentials_ref = CREDENTIALS_REF
    if payload.account_name is not None:
        record.account_name = payload.account_name.strip() or None
    record.connected_by = actor_user_id
    record.connected_at = now
    result = _apply_test(db, record, spec, now)
    db.flush()
    # write_audit_log commits. Never any credential value in the metadata.
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="integration.connect",
        resource_type="integration",
        resource_id=str(record.id),
        metadata={"provider": provider, "verified": result.ok, "fields": sorted(k for k, v in {**fields, **secrets}.items() if v)},
    )
    db.refresh(record)
    logger.info("integration_saved", tenant_id=tenant_id, provider=provider, verified=result.ok)
    out = _result(record, result, now)
    _after_store_connected(db, tenant_id, actor_user_id, provider, result.ok)
    return out


def test_connection(db: Session, tenant_id: str, actor_user_id: str, provider: str) -> dict[str, Any]:
    spec = _provider(provider)
    record = _primary(_records(db, tenant_id, provider))
    if record is None or record.status == "disconnected" or not _secrets(record):
        raise AppError(f"{spec.label} has no saved credentials to test.", 409)
    now = datetime.now(timezone.utc)
    result = _apply_test(db, record, spec, now)
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="integration.test",
        resource_type="integration",
        resource_id=str(record.id),
        metadata={"provider": provider, "verified": result.ok},
    )
    db.refresh(record)
    out = _result(record, result, now)
    _after_store_connected(db, tenant_id, actor_user_id, provider, result.ok)
    return out


# ---------------------------------------------------------------------------
# Social sign-in (SPEC-BE-080): the same settings shape as the pasted-token
# form (fields + secrets_enc), plus settings["oauth"] = {via, scopes,
# access_expires_at, refresh_expires_at, external_account_id}. The refresh
# token sits in secrets_enc next to the access token.
# ---------------------------------------------------------------------------
def oauth_expiry(oauth: dict[str, Any] | None) -> datetime | None:
    if not oauth:
        return None
    raw = oauth.get("refresh_expires_at") or (None if oauth.get("has_refresh") else oauth.get("access_expires_at"))
    return datetime.fromisoformat(raw).astimezone(timezone.utc) if raw else None


def save_oauth_credentials(
    db: Session,
    tenant_id: str,
    actor_user_id: str,
    provider: str,
    fields: dict[str, str],
    secrets_: dict[str, str],
    oauth: dict[str, Any],
    account_name: str | None = None,
) -> dict[str, Any]:
    spec = _provider(provider)
    record = _primary(_records(db, tenant_id, provider))
    now = datetime.now(timezone.utc)
    if record is None:
        record = Integration(tenant_id=tenant_id, provider=provider, status="error")
        db.add(record)
    settings = dict(record.settings or {})
    settings["fields"] = dict(fields)
    settings["secrets_enc"] = encrypt_secret(json.dumps({k: v for k, v in secrets_.items() if v}))
    settings["oauth"] = {**oauth, "via": "oauth", "has_refresh": bool(secrets_.get("refresh_token"))}
    settings.pop("oauth_pending", None)
    record.settings = settings
    record.credentials_ref = CREDENTIALS_REF
    if account_name:
        record.account_name = account_name.strip()[:255] or None
    record.connected_by = actor_user_id
    record.connected_at = now
    result = _apply_test(db, record, spec, now)
    db.flush()
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="integration.oauth_connected",
        resource_type="integration",
        resource_id=str(record.id),
        metadata={"provider": provider, "verified": result.ok, "scopes": list(oauth.get("scopes") or [])[:20],
                  "refreshable": bool(secrets_.get("refresh_token"))},
    )
    db.refresh(record)
    logger.info("integration_oauth_saved", tenant_id=tenant_id, provider=provider, verified=result.ok)
    return _result(record, result, now)


def store_refreshed_token(record: Integration, token: dict[str, Any]) -> None:
    """A refreshed access token (and the refresh token the platform returned,
    which may be a new one). No commit; the caller commits."""
    secrets_ = _secrets(record)
    secrets_["access_token"] = token["access_token"]
    if token.get("refresh_token"):
        secrets_["refresh_token"] = token["refresh_token"]
    settings = dict(record.settings or {})
    oauth = dict(settings.get("oauth") or {})
    oauth["access_expires_at"] = token.get("access_expires_at")
    if token.get("refresh_expires_at"):
        oauth["refresh_expires_at"] = token["refresh_expires_at"]
    oauth["refreshed_at"] = datetime.now(timezone.utc).isoformat()
    settings["secrets_enc"] = encrypt_secret(json.dumps(secrets_))
    settings["oauth"] = oauth
    record.settings = settings
    record.expires_at = oauth_expiry(oauth)
    if record.status == "expired":
        record.status = "connected"
        record.last_error = None


STORE_PROVIDERS = ("shopify", "woocommerce")


def _after_store_connected(db: Session, tenant_id: str, actor_user_id: str, provider: str, ok: bool) -> None:
    # SPEC-BE-058 step 1-3: a store that connects (or re-tests OK) gets its
    # shipping configuration detected, and imported when one exists. Runs in
    # the background after the commit; a failure is recorded on the
    # integration's shipping_sync status, never raised to the save.
    if not ok or provider not in STORE_PROVIDERS:
        return
    from app.services import shipping_service
    from app.services.scheduler_service import run_soon

    run_soon(shipping_service.auto_detect_and_sync, str(tenant_id), str(actor_user_id), db=db, name="shipping:auto-detect")


def store_connection(db: Session, tenant_id: str) -> dict[str, Any] | None:
    """The tenant's connected store (Shopify first, then WooCommerce), with its
    decrypted fields for the shipping clients. Never returned to a client."""
    now = datetime.now(timezone.utc)
    for provider in STORE_PROVIDERS:
        records = _records(db, tenant_id, provider)
        status, _ = _provider_status(records, now)
        record = _primary(records)
        if record is not None and status == "connected":
            return {
                "provider": provider,
                "integration_id": str(record.id),
                "account_name": record.account_name,
                "fields": {**_fields(record), **_secrets(record)},
            }
    return None


def store_record(db: Session, tenant_id: str, integration_id: str) -> Integration | None:
    return (
        db.query(Integration)
        .filter(Integration.tenant_id == tenant_id, Integration.id == integration_id)
        .first()
    )


def disconnect(db: Session, tenant_id: str, actor_user_id: str, provider: str) -> None:
    _provider(provider)
    records = [r for r in _records(db, tenant_id, provider) if r.status != "disconnected" or r.credentials_ref]
    if not records:
        raise NotFoundError("This integration isn't connected.")
    for record in records:
        # Credentials wiped; the row is kept for history.
        record.status = "disconnected"
        record.credentials_ref = ""
        settings = dict(record.settings or {})
        settings.pop("secrets_enc", None)
        settings.pop("fields", None)
        # SPEC-BE-054: also drop a pending Meta login and the chosen Page info;
        # SPEC-BE-080: and a social sign-in's token data / pending choices.
        for key in ("meta_pending", "meta_oauth_nonce", "meta", "oauth", "oauth_pending", "oauth_nonce"):
            settings.pop(key, None)
        record.settings = settings
        record.last_error = None
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="integration.disconnect",
        resource_type="integration",
        resource_id=str(records[0].id),
        metadata={"provider": provider, "rows": len(records)},
    )
    logger.info("integration_disconnected", tenant_id=tenant_id, provider=provider)


# ---------------------------------------------------------------------------
# "Connect with Facebook" (SPEC-BE-054)
# ---------------------------------------------------------------------------
# Flow: connect -> Meta login dialog -> the frontend's callback page posts
# {code, state} -> the token is stored encrypted as *pending* (an existing
# connection keeps working) together with the assets it can reach -> select
# moves it into the same settings shape the pasted-token form uses
# (secrets_enc + fields), so the Integrations card and publishing work the same
# for both paths.
META = "meta_ads"
# integrations.account_external_id exists live but the Integration model (not a
# SPEC-BE-054 target) doesn't map it: read/written through a Core table.
_integrations_ext = table(
    "integrations",
    column("id"),
    column("tenant_id"),
    column("provider"),
    column("account_external_id"),
)
STATE_TTL = timedelta(minutes=10)
STATE_TYPE = "meta_oauth"
BAD_STATE = "This sign-in link expired or is invalid; start Connect with Facebook again."


def _meta_redirect_uri() -> str:
    return get_settings().FRONTEND_BASE_URL.rstrip("/") + "/integrations/meta/callback"


def _require_meta_app() -> None:
    if not meta_ads.app_configured():
        raise AppError("Meta connection isn't set up on this server.", 503)


def _meta_row(db: Session, tenant_id: str, actor_user_id: str) -> Integration:
    record = _primary(_records(db, tenant_id, META))
    if record is None:
        record = Integration(
            tenant_id=tenant_id,
            provider=META,
            status="disconnected",
            credentials_ref="",
            connected_by=actor_user_id,
            # NOT NULL live; reset to the real time when the connection is made.
            connected_at=datetime.now(timezone.utc),
        )
        db.add(record)
        db.flush()
    return record


def _require_meta_access(db: Session, tenant_id: str) -> None:
    # SPEC-BE-103: the Super admin can switch PilotSonic's Meta app off for a
    # company. New sign-ins stop; an existing connection keeps its own token.
    from app.services import platform_service

    platform_service.require(tenant_id, "meta_app", db)


def meta_connect_url(db: Session, tenant_id: str, actor_user_id: str) -> dict[str, Any]:
    _require_meta_app()
    _require_meta_access(db, tenant_id)
    record = _meta_row(db, tenant_id, actor_user_id)
    nonce = secrets.token_urlsafe(16)
    settings = dict(record.settings or {})
    # Single use: the first callback presenting this nonce clears it.
    settings["meta_oauth_nonce"] = nonce
    record.settings = settings
    s = get_settings()
    claims = {
        "typ": STATE_TYPE,
        "t": str(tenant_id),
        "u": str(actor_user_id),
        "n": nonce,
        "exp": datetime.now(timezone.utc) + STATE_TTL,
    }
    state = jwt.encode(claims, s.SECRET_KEY.get_secret_value(), algorithm=s.JWT_ALGORITHM)
    db.commit()
    return {"login_url": meta_ads.login_url(_meta_redirect_uri(), state)}


def _check_state(record: Integration | None, tenant_id: str, actor_user_id: str, state: str) -> None:
    s = get_settings()
    try:
        claims = jwt.decode(state, s.SECRET_KEY.get_secret_value(), algorithms=[s.JWT_ALGORITHM])
    except JWTError:
        raise AppError(BAD_STATE, 400) from None
    expected = (record.settings or {}).get("meta_oauth_nonce") if record else None
    if (
        claims.get("typ") != STATE_TYPE
        or claims.get("t") != str(tenant_id)
        or claims.get("u") != str(actor_user_id)
        or not expected
        or claims.get("n") != expected
    ):
        raise AppError(BAD_STATE, 400)


def _account_id(raw: dict[str, Any]) -> str:
    return str(raw.get("account_id") or str(raw.get("id", "")).removeprefix("act_"))


def meta_callback(
    db: Session, tenant_id: str, actor_user_id: str, code: str, state: str
) -> dict[str, Any]:
    _require_meta_app()
    _require_meta_access(db, tenant_id)
    record = _primary(_records(db, tenant_id, META))
    _check_state(record, tenant_id, actor_user_id, state)
    assert record is not None  # _check_state needs a record holding the nonce
    settings = dict(record.settings or {})
    settings.pop("meta_oauth_nonce", None)  # consumed, even if the exchange fails
    record.settings = settings
    db.commit()

    try:
        token = meta_ads.exchange_code(code, _meta_redirect_uri())
        client = meta_ads.MetaClient(token)
        accounts = client.list_ad_accounts()
        pages = client.list_pages()
        pixels: list[dict[str, Any]] = []
        for acct in accounts[:25]:
            account_id = _account_id(acct)
            for px in client.list_pixels(account_id):
                pid = str(px["id"])
                pixels.append({"id": pid, "name": px.get("name") or pid, "ad_account_id": account_id})
    except meta_ads.MetaError as exc:
        raise AppError(f"Meta: {exc.message}", 502) from None

    ad_accounts = [
        {
            "id": _account_id(a),
            "name": a.get("name") or "",
            "currency": (a.get("currency") or "").upper(),
            "account_status": int(a.get("account_status") or 0),
        }
        for a in accounts
    ]
    page_list = []
    for p in pages:
        ig = p.get("instagram_business_account") or None
        page_list.append(
            {
                "id": str(p["id"]),
                "name": p.get("name") or str(p["id"]),
                "instagram": {"id": str(ig["id"]), "username": ig.get("username")} if ig else None,
            }
        )
    if not ad_accounts or not page_list:
        gaps = [x for x, ok in (("an ad account", ad_accounts), ("a Facebook Page", page_list)) if not ok]
        what = " or ".join(gaps)
        raise AppError(f"This Meta sign-in gave access to no {what}. Sign in again and select {what}.", 422)

    settings = dict(record.settings or {})
    # Held as pending until select; the current connection (if any) is untouched.
    settings["meta_pending"] = {
        "secrets_enc": encrypt_secret(json.dumps({"access_token": token})),
        "ad_accounts": ad_accounts,
        "pages": page_list,
        "pixels": pixels,
    }
    record.settings = settings
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="integration.meta_connected",
        resource_type="integration",
        resource_id=str(record.id),
        metadata={"ad_accounts": len(ad_accounts), "pages": len(page_list), "pixels": len(pixels)},
    )
    logger.info("meta_oauth_callback", tenant_id=tenant_id, ad_accounts=len(ad_accounts))
    return {
        "connection_id": str(record.id),
        "ad_accounts": ad_accounts,
        "pages": page_list,
        "pixels": pixels,
    }


def meta_select(
    db: Session,
    tenant_id: str,
    actor_user_id: str,
    ad_account_id: str,
    page_id: str,
    instagram_id: str | None,
    pixel_id: str | None,
) -> dict[str, Any]:
    record = _primary(_records(db, tenant_id, META))
    pending = ((record.settings or {}).get("meta_pending") if record else None) or None
    if record is None or not pending:
        raise AppError("Start Connect with Facebook again; there's nothing to choose from.", 409)
    account = next((a for a in pending["ad_accounts"] if a["id"] == ad_account_id), None)
    page = next((p for p in pending["pages"] if p["id"] == page_id), None)
    if account is None or page is None:
        raise AppError("Pick an ad account and a Page from the list Meta returned.", 422)
    if instagram_id and (not page.get("instagram") or page["instagram"]["id"] != instagram_id):
        raise AppError("That Instagram account isn't linked to the chosen Page.", 422)
    if pixel_id and not any(
        p["id"] == pixel_id and p["ad_account_id"] == ad_account_id for p in pending["pixels"]
    ):
        raise AppError("That Pixel doesn't belong to the chosen ad account.", 422)
    if account["account_status"] != 1:
        status_text = meta_ads.ACCOUNT_STATUS.get(account["account_status"], "not active")
        raise AppError(
            f"The ad account {account['name']} is {status_text}; fix it in Meta Ads Manager first.", 422
        )

    # One row per (tenant, provider, ad account) - a unique index: reuse a row
    # that already holds this ad account.
    existing_id = db.execute(
        select(_integrations_ext.c.id).where(
            _integrations_ext.c.tenant_id == tenant_id,
            _integrations_ext.c.provider == META,
            _integrations_ext.c.account_external_id == ad_account_id,
        )
    ).scalar()
    target = (db.get(Integration, str(existing_id)) if existing_id else None) or record
    now = datetime.now(timezone.utc)
    settings = dict(target.settings or {})
    settings["secrets_enc"] = pending["secrets_enc"]
    settings["fields"] = {
        "ad_account_id": ad_account_id,
        "page_id": page_id,
        "instagram_id": instagram_id or "",
        "pixel_id": pixel_id or "",
    }
    settings["meta"] = {"page_name": page["name"], "currency": account["currency"], "via": "oauth"}
    settings.pop("meta_pending", None)
    target.settings = settings
    target.credentials_ref = CREDENTIALS_REF
    target.account_name = account["name"][:255] or None
    target.connected_by = actor_user_id
    target.connected_at = now
    if target is not record:
        rest = dict(record.settings or {})
        rest.pop("meta_pending", None)
        record.settings = rest
    spec = _provider(META)
    result = _apply_test(db, target, spec, now)
    db.flush()
    db.execute(
        update(_integrations_ext)
        .where(_integrations_ext.c.id == target.id)
        .values(account_external_id=ad_account_id)
    )
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="integration.meta_selected",
        resource_type="integration",
        resource_id=str(target.id),
        metadata={
            "ad_account_id": ad_account_id,
            "page_id": page_id,
            "instagram": bool(instagram_id),
            "pixel": bool(pixel_id),
            "verified": result.ok,
        },
    )
    db.refresh(target)
    return _card(spec, [target], now)


def meta_publish_credentials(db: Session, tenant_id: str) -> dict[str, str] | None:
    """The tenant's Meta connection for publishing (SPEC-BE-054), or None when
    not connected. Same shape for the OAuth and the pasted-token path."""
    now = datetime.now(timezone.utc)
    records = _records(db, tenant_id, META)
    status, _ = _provider_status(records, now)
    record = _primary(records)
    if record is None or status == "not_connected":
        return None
    fields, secret = _fields(record), _secrets(record)
    return {
        "status": status,
        "integration_id": str(record.id),
        "access_token": secret.get("access_token", ""),
        "ad_account_id": (fields.get("ad_account_id") or "").removeprefix("act_"),
        "page_id": fields.get("page_id") or "",
        "instagram_id": fields.get("instagram_id") or "",
        "pixel_id": fields.get("pixel_id") or "",
    }


def mark_meta_expired(db: Session, tenant_id: str, message: str) -> None:
    """Meta rejected the token (code 190): the card shows Reconnect. No commit."""
    record = _primary(_records(db, tenant_id, META))
    if record is not None and record.status != "disconnected":
        record.status = "expired"
        record.last_error = message[:300]


def ad_platform_connection(db: Session, tenant_id: str, provider: str) -> dict[str, Any] | None:
    """An ad platform's connection for the Ad Manager (SPEC-BE-062): status,
    account name and the decrypted fields the adapter needs, or None when
    nothing was ever saved. Never returned to a client."""
    now = datetime.now(timezone.utc)
    records = _records(db, tenant_id, provider)
    status, _ = _provider_status(records, now)
    record = _primary(records)
    if record is None or status == "not_connected":
        return None
    return {
        "status": status,
        "integration_id": str(record.id),
        "account_name": record.account_name,
        "fields": {**_fields(record), **_secrets(record)},
    }


def mark_ad_platform_expired(db: Session, tenant_id: str, provider: str, message: str) -> None:
    """The platform rejected the credential: the card shows Reconnect. No commit."""
    record = _primary(_records(db, tenant_id, provider))
    if record is not None and record.status != "disconnected":
        record.status = "expired"
        record.last_error = message[:500]
