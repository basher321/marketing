"""Saved audiences for the Campaign Wizard (SPEC-BE-045)."""
from datetime import timezone
from typing import Any

import structlog
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.exceptions import ConflictError
from app.models.audience import Audience
from app.schemas.audience import AudienceCreate

logger = structlog.get_logger(__name__)


def _to_dict(audience: Audience) -> dict[str, Any]:
    return {
        "id": audience.id,
        "name": audience.name,
        "description": audience.description,
        "targeting": audience.targeting or {},
        # No ad-platform data exists to estimate reach, so this is never guessed.
        "estimated_size": None,
        "created_at": audience.created_at.astimezone(timezone.utc),
    }


def get_audience(db: Session, tenant_id: str, audience_id: str) -> Audience | None:
    return (
        db.query(Audience)
        .filter(Audience.tenant_id == tenant_id, Audience.id == audience_id)
        .first()
    )


def list_audiences(db: Session, tenant_id: str) -> dict[str, Any]:
    audiences = (
        db.query(Audience)
        .filter(Audience.tenant_id == tenant_id)
        .order_by(func.lower(Audience.name), Audience.id)
        .all()
    )
    return {"count": len(audiences), "items": [_to_dict(a) for a in audiences]}


def create_audience(
    db: Session, tenant_id: str, actor_user_id: str, payload: AudienceCreate
) -> dict[str, Any]:
    # Names are unique per tenant (case-insensitive), checked here: the live
    # table has no unique constraint.
    exists = (
        db.query(Audience.id)
        .filter(Audience.tenant_id == tenant_id, func.lower(Audience.name) == payload.name.lower())
        .first()
    )
    if exists:
        raise ConflictError(f'An audience named "{payload.name}" already exists.')
    audience = Audience(
        tenant_id=tenant_id,
        name=payload.name,
        description=payload.description,
        targeting=payload.targeting.model_dump(),
        created_by=actor_user_id,
    )
    db.add(audience)
    db.flush()
    # write_audit_log commits: the audience and its audit row land together.
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="audience.create",
        resource_type="audience",
        resource_id=audience.id,
        metadata={"name": audience.name},
    )
    db.refresh(audience)
    logger.info("audience_created", tenant_id=tenant_id, audience_id=str(audience.id))
    return _to_dict(audience)
