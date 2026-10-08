"""AuditLog model.

Maps the live `audit_log` table (partitioned by occurred_at; primary key
id + occurred_at). The attribute names core/audit.write_audit_log() passes are
kept and mapped to the live columns: actor_user_id -> actor_id,
extra_metadata -> metadata. The live table has no created_at/updated_at, so
the model uses the id mixin plus an explicit nullable tenant_id.
"""
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine.default import DefaultExecutionContext
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import UUIDPrimaryKeyMixin


def _actor_type(context: DefaultExecutionContext) -> str:
    # actor_type is NOT NULL in the live table but write_audit_log() does not
    # pass it: 'human' when an acting user is recorded, otherwise 'system'.
    params = context.get_current_parameters()
    return "human" if params.get("actor_id") or params.get("actor_user_id") else "system"


class AuditLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "audit_log"

    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_type: Mapped[str] = mapped_column(
        Enum("human", "ai", "system", "webhook", name="actor_type", create_type=False),
        default=_actor_type,
        nullable=False,
    )
    actor_user_id: Mapped[str | None] = mapped_column("actor_id", String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
