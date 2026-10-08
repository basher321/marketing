"""Knowledge Base policies (SPEC-BE-048). Enabled policies that are in effect
ground the AI's reply drafts (ai/retrieval.retrieve_grounding)."""
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.exceptions import AppError, NotFoundError
from app.models.policy import Policy
from app.schemas.policy import PolicyCreate, PolicyUpdate

logger = structlog.get_logger(__name__)


def _utc(value: datetime | None) -> datetime | None:
    return value.astimezone(timezone.utc) if value else None


def _to_read(p: Policy) -> dict[str, Any]:
    return {
        "id": p.id,
        "policy_type": p.policy_type,
        "title": p.title,
        "body": p.body,
        "enabled": p.enabled,
        "effective_from": _utc(p.effective_from),
        "effective_until": _utc(p.effective_until),
        "updated_at": _utc(p.updated_at),
    }


def _get(db: Session, tenant_id: str, policy_id: str) -> Policy:
    policy = db.query(Policy).filter(Policy.tenant_id == tenant_id, Policy.id == policy_id).first()
    if policy is None:
        # Same 404 for a missing policy and another tenant's policy.
        raise NotFoundError("Policy not found.")
    return policy


def _audit(db: Session, tenant_id: str, actor: str, action: str, p: Policy, extra: dict[str, Any] | None = None) -> None:
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor,
        action=action,
        resource_type="policy",
        resource_id=str(p.id),
        metadata={"policy_type": p.policy_type, "title": p.title, **(extra or {})},
    )


def list_policies(db: Session, tenant_id: str) -> dict[str, Any]:
    rows = (
        db.query(Policy)
        .filter(Policy.tenant_id == tenant_id)
        .order_by(Policy.policy_type, Policy.title, Policy.id)
        .all()
    )
    return {"count": len(rows), "items": [_to_read(p) for p in rows]}


def create_policy(db: Session, tenant_id: str, actor: str, payload: PolicyCreate) -> dict[str, Any]:
    policy = Policy(tenant_id=tenant_id, **payload.model_dump())
    db.add(policy)
    db.flush()
    _audit(db, tenant_id, actor, "policy.create", policy)
    db.refresh(policy)
    logger.info("policy_created", tenant_id=tenant_id, policy_id=str(policy.id))
    return _to_read(policy)


def update_policy(
    db: Session, tenant_id: str, actor: str, policy_id: str, payload: PolicyUpdate
) -> dict[str, Any]:
    policy = _get(db, tenant_id, policy_id)
    sent = payload.model_fields_set
    for field in ("policy_type", "title", "body", "enabled"):
        if field in sent and getattr(payload, field) is not None:
            setattr(policy, field, getattr(payload, field))
    for field in ("effective_from", "effective_until"):
        if field in sent:
            setattr(policy, field, getattr(payload, field))
    if policy.effective_from and policy.effective_until and policy.effective_until <= policy.effective_from:
        raise AppError("'Effective until' must be after 'effective from'.", 422)
    _audit(db, tenant_id, actor, "policy.update", policy, {"fields": sorted(sent)})
    db.refresh(policy)
    return _to_read(policy)


def delete_policy(db: Session, tenant_id: str, actor: str, policy_id: str) -> None:
    policy = _get(db, tenant_id, policy_id)
    db.delete(policy)
    db.flush()
    _audit(db, tenant_id, actor, "policy.delete", policy)
