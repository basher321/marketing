"""ApprovalQueue model.

Maps the live `approval_queue` columns needed for the per-engine pending
counts (SPEC-BE-020). The live table has created_at but no updated_at, so the
model uses the id + tenant mixins rather than TenantScopedModel. Columns not
needed yet stay unmapped.
"""
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TenantScopedMixin, UUIDPrimaryKeyMixin

APPROVAL_SUBJECT_TYPES = ("plan", "action", "content", "campaign", "reply", "pricing_change")
APPROVAL_DECISIONS = ("pending", "approved", "rejected", "expired")


class ApprovalQueue(Base, UUIDPrimaryKeyMixin, TenantScopedMixin):
    __tablename__ = "approval_queue"

    subject_type: Mapped[str] = mapped_column(
        Enum(*APPROVAL_SUBJECT_TYPES, name="approval_subject_type", create_type=False),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(
        Enum(*APPROVAL_DECISIONS, name="approval_decision", create_type=False),
        default="pending",
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Live columns used to record decisions (SPEC-BE-024).
    subject_id: Mapped[str] = mapped_column(String(36), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Live requested_at, used by the Pending Approvals list (SPEC-BE-025).
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
