"""Conversation, Message models."""
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TenantScopedModel, UUIDPrimaryKeyMixin, TimestampMixin


class Conversation(Base, TenantScopedModel):
    __tablename__ = "conversations"

    customer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("customers.id"), nullable=True)
    channel: Mapped[str] = mapped_column(String(50), default="webchat")
    status: Mapped[str] = mapped_column(String(50), default="open")
    # The live column is assignee_id; the attribute name is kept for existing
    # callers (SPEC-BE-028 fixed the mapping so the list route works).
    assigned_user_id: Mapped[str | None] = mapped_column("assignee_id", String(36), nullable=True)
    # Live conversations.csat_score (int4, nullable; no range constraint) -
    # the CSAT (7d) source for SPEC-BE-021.
    csat_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Live column set when a reply is sent (SPEC-BE-026).
    last_agent_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Inbox columns (SPEC-BE-007): the Topic cell, and the jsonb where the
    # handoff marker (handed_off_at / handed_off_by) is recorded.
    topic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "messages"

    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE")
    )
    sender_type: Mapped[str] = mapped_column(String(20), default="customer")
    body: Mapped[str] = mapped_column(String(8000), default="")
    # Live messages columns used by SPEC-BE-021's avg. response.
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    direction: Mapped[str] = mapped_column(
        Enum("inbound", "outbound", name="message_direction", create_type=False),
        nullable=False,
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Live messages columns used by SPEC-BE-026's draft send. The live table has
    # no updated_at, so the column inherited from TimestampMixin is removed
    # (ORM inserts/updates would otherwise reference a missing column).
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at = None  # type: ignore[assignment]
    # Live messages columns used by SPEC-BE-028's draft generation:
    # ai_confidence = SPEC-BE-027's confidence, ai_model = the model that
    # drafted it, ai_draft_of_id = the customer message being answered,
    # metadata = grounding sources and generation details.
    ai_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_draft_of_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
