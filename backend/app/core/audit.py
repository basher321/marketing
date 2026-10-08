"""Audit log writer utility."""
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def write_audit_log(
    db: Session,
    *,
    tenant_id: str,
    actor_user_id: Optional[str],
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> AuditLog:
    entry = AuditLog(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        extra_metadata=metadata or {},
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
