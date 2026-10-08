"""Base model with common columns (id, created_at, updated_at, tenant_id).

Primary keys are stored as string UUIDs (portable across Postgres and the
SQLite test database) rather than a Postgres-only UUID column type.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UUIDPrimaryKeyMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class TenantScopedMixin:
    """Mixin for models that belong to a single tenant.

    tenant_id is a plain column (not a ForeignKey on every subclass) so it
    can be declared once here; subclasses that need FK integrity add an
    explicit ForeignKey via `tenant_fk()`.
    """

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )


class BaseModel(UUIDPrimaryKeyMixin, TimestampMixin):
    """Common base for non-tenant-scoped models (e.g. Tenant itself)."""

    pass


class TenantScopedModel(UUIDPrimaryKeyMixin, TimestampMixin, TenantScopedMixin):
    """Common base for tenant-scoped domain models."""

    pass
