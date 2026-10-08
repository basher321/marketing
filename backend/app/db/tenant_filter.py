"""SQLAlchemy helpers for tenant_id auto-filter.

Rather than relying on fragile global ORM events, the app scopes tenant data
by explicitly filtering `tenant_id` in the service layer (see
`validators/tenant_scope.py`). This module provides a small helper used by
services to apply that filter consistently, plus an event listener that
guards against accidentally committing a row with no tenant_id set on
tenant-scoped models.
"""
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.base import TenantScopedMixin


def apply_tenant_filter(query, model, tenant_id: str):
    return query.filter(model.tenant_id == tenant_id)


@event.listens_for(Session, "before_flush")
def _guard_tenant_id(session: Session, flush_context, instances) -> None:
    for obj in session.new:
        if isinstance(obj, TenantScopedMixin) and getattr(obj, "tenant_id", None) is None:
            raise ValueError(
                f"{obj.__class__.__name__} instance is missing tenant_id before insert."
            )
