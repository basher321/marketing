"""SmsMessage: the live `sms_messages` table (SPEC-BE-108 DDL)."""
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TenantScopedMixin, UUIDPrimaryKeyMixin


class SmsMessage(Base, UUIDPrimaryKeyMixin, TenantScopedMixin):
    # direction: outbound | inbound. kind: order_confirmation, follow_up, auto_reply,
    # manual, inbound. status: queued, sent, delivered, undelivered, failed, received.
    # interpreted (inbound only): confirm, cancel, ambiguous, unrelated.
    __tablename__ = "sms_messages"

    order_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    customer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    from_number: Mapped[str] = mapped_column(Text, nullable=False)
    to_number: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, default="twilio", nullable=False)
    provider_sid: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    interpreted: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
