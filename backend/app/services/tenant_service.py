"""Tenant provisioning, organization settings, branding and data reset."""
import base64
from datetime import datetime, timezone
from typing import Any, Literal, cast

import structlog
from sqlalchemy import select, text
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.core.security import verify_password
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.tenant import BrandingTextUpdate, TenantUpdate
from app.utils import locale_data

logger = structlog.get_logger(__name__)


def slug_taken_message(slug: str) -> str:
    return f"Tenant slug '{slug}' is already in use."


def create_tenant(
    db: Session, name: str, slug: str, country_code: str | None = None, timezone_name: str | None = None
) -> Tenant:
    """Add a new tenant to the session and flush it; the caller owns the commit.

    `slug` must already be normalized (schemas.auth.RegisterRequest does it). The subdomain is
    the slug (SPEC-BE-037 open decision 1). Soft-deleted tenants still hold their slug, since
    the live UNIQUE constraints on slug/subdomain cover them too. Every other column takes its
    database default (status 'trial', currency 'USD', timezone 'UTC'), except what sign-up
    detected (SPEC-BE-072): a validated country (whose currency becomes the company currency)
    and timezone.
    """
    if get_tenant_by_slug(db, slug, include_deleted=True) is not None:
        raise ConflictError(slug_taken_message(slug))

    detected: dict[str, str] = {}
    if country_code:
        detected["country_code"] = country_code
        currency = locale_data.countries()[country_code]["currency"]
        if currency:
            detected["currency"] = currency
    if timezone_name:
        detected["timezone"] = timezone_name
    tenant = Tenant(name=name, slug=slug, subdomain=slug, **detected)
    db.add(tenant)
    db.flush()
    return tenant


def get_tenant_by_slug(db: Session, slug: str, include_deleted: bool = False) -> Tenant | None:
    query = select(Tenant).where(Tenant.slug == slug)
    if not include_deleted:
        query = query.where(Tenant.deleted_at.is_(None))
    return db.scalars(query).first()


# ---------------------------------------------------------------------------
# Organization Settings (SPEC-BE-051)
# ---------------------------------------------------------------------------
BrandingSlot = Literal["logo", "banner", "head_photo"]
MAX_IMAGE_BYTES = 1024 * 1024  # 1 MB


def _tenant(db: Session, tenant_id: str) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundError("Tenant not found.")
    return tenant


def _branding(tenant: Tenant) -> dict[str, Any]:
    return dict((tenant.extra_metadata or {}).get("branding") or {})


def branding_payload(tenant: Tenant) -> dict[str, Any]:
    b = _branding(tenant)
    return {
        "logo_url": b.get("logo"),
        "banner_url": b.get("banner"),
        "head": {"name": b.get("head_name"), "title": b.get("head_title"), "photo_url": b.get("head_photo")},
    }


def tenant_payload(tenant: Tenant) -> dict[str, Any]:
    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "subdomain": tenant.subdomain,
        "status": tenant.status,
        "currency": tenant.currency,
        "timezone": tenant.timezone,
        "country_code": tenant.country_code,
        "default_language": tenant.default_language,
        "branding": branding_payload(tenant),
        "created_at": tenant.created_at,
    }


def _save_branding(db: Session, tenant: Tenant, actor_user_id: str, changes: dict[str, Any], what: str) -> dict[str, Any]:
    # Reassign a new dict so SQLAlchemy sees the jsonb change.
    meta = dict(tenant.extra_metadata or {})
    branding = dict(meta.get("branding") or {})
    for key, value in changes.items():
        if value is None:
            branding.pop(key, None)
        else:
            branding[key] = value
    meta["branding"] = branding
    tenant.extra_metadata = meta
    write_audit_log(
        db,
        tenant_id=str(tenant.id),
        actor_user_id=actor_user_id,
        action="tenant.branding_update",
        resource_type="tenant",
        resource_id=str(tenant.id),
        metadata={"changed": what},
    )
    db.refresh(tenant)
    return branding_payload(tenant)


def update_profile(db: Session, tenant_id: str, actor_user_id: str, payload: TenantUpdate) -> dict[str, Any]:
    tenant = _tenant(db, tenant_id)
    changed = {}
    for field in ("name", "country_code", "currency", "timezone", "default_language"):
        if field in payload.model_fields_set and getattr(payload, field) is not None:
            setattr(tenant, field, getattr(payload, field))
            changed[field] = getattr(payload, field)
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="tenant.update",
        resource_type="tenant",
        resource_id=tenant_id,
        metadata=changed,
    )
    db.refresh(tenant)
    return tenant_payload(tenant)


def _image_mime(data: bytes) -> str | None:
    # The type comes from the file's magic bytes, never from the client's claim.
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def set_branding_image(
    db: Session, tenant_id: str, actor_user_id: str, slot: BrandingSlot, data: bytes
) -> dict[str, Any]:
    # Stored as a data URL in tenants.metadata["branding"]: no file storage or
    # extra folder, tenant-scoped, and it survives restarts (<= 1 MB each).
    if not data:
        raise AppError("The file is empty.", 422)
    if len(data) > MAX_IMAGE_BYTES:
        raise AppError("The image must be 1 MB or smaller.", 422)
    mime = _image_mime(data)
    if mime is None:
        raise AppError("Only PNG, JPEG or WebP images are allowed.", 422)
    url = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    return _save_branding(db, _tenant(db, tenant_id), actor_user_id, {slot: url}, slot)


def clear_branding_image(db: Session, tenant_id: str, actor_user_id: str, slot: BrandingSlot) -> dict[str, Any]:
    return _save_branding(db, _tenant(db, tenant_id), actor_user_id, {slot: None}, f"{slot} removed")


def set_branding_text(
    db: Session, tenant_id: str, actor_user_id: str, payload: BrandingTextUpdate
) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for field in ("head_name", "head_title"):
        if field in payload.model_fields_set:
            value = getattr(payload, field)
            changes[field] = value.strip() if value and value.strip() else None
    return _save_branding(db, _tenant(db, tenant_id), actor_user_id, changes, "head text")


# Reset company data. Deletes all of ONE tenant's business data, children
# before parents (FK order checked against the live schema). Kept: the tenant
# itself, users, roles, integrations and AI-model keys, api_keys, settings and
# branding, audit_log (plus system tables: usage_metrics, system_logs,
# rate_limit_buckets, auth tokens). Every DELETE is filtered by tenant_id.
RESET_TABLES = (
    "ai_campaign_runs",  # SPEC-BE-071 F15
    "action_executions",
    "workflow_runs",
    "workflows",
    "scheduled_posts",
    "ads",
    "ad_groups",
    "audiences",
    "content_assets",
    "content_templates",
    "campaigns",
    "approval_queue",
    "notifications",
    "orchestrator_plans",
    "orchestrator_messages",
    "messages",
    "conversations",
    "abandoned_carts",
    "order_items",
    "orders",
    "inventory_movements",
    "inventory",
    "inventory_locations",
    "pricing_rules",
    "shipping_policies",
    "shipping_zones",
    "product_variants",
    "products",
    "product_categories",
    "customers",
    "faqs",
    "macros",
    "policies",
    "kb_documents",
    "brand_settings",
    "analytics_events",
    "analytics_daily_rollups",
    "webhook_events",
)


def reset_company_data(
    db: Session, tenant_id: str, actor: User, confirm_slug: str, password: str
) -> dict[str, Any]:
    # Lazy import: auth_service imports this module (create_tenant).
    from app.services.auth_service import _locked_message, _record_failed_attempt

    tenant = _tenant(db, tenant_id)
    if confirm_slug.strip() != tenant.slug:
        raise AppError("The workspace name you typed doesn't match.", 422)
    now = datetime.now(timezone.utc)
    if actor.locked_until is not None and actor.locked_until > now:
        raise AppError(_locked_message(actor.locked_until, now), status_code=429)
    if not verify_password(password, actor.password_hash):
        # A wrong password counts toward the login lockout (SPEC-BE-039). 422,
        # not 403: 403 on this route means "not the owner".
        _record_failed_attempt(db, str(actor.id), now)
        raise AppError("Incorrect password.", 422)

    deleted: dict[str, int] = {}
    for table in RESET_TABLES:
        result = cast(
            CursorResult[Any],
            db.execute(
                text(f"DELETE FROM {table} WHERE tenant_id = :tenant_id"),  # noqa: S608 - fixed names
                {"tenant_id": tenant_id},
            ),
        )
        deleted[table] = result.rowcount
    # write_audit_log commits: every delete and the audit row land together.
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=str(actor.id),
        action="tenant.reset",
        resource_type="tenant",
        resource_id=tenant_id,
        metadata={"deleted": {k: v for k, v in deleted.items() if v}},
    )
    logger.warning("tenant_data_reset", tenant_id=tenant_id, deleted=sum(deleted.values()))
    return {"deleted": deleted, "reset_at": now}
