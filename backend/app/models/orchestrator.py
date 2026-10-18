"""OrchestratorMessage, OrchestratorPlan models.

Maps the live `orchestrator_messages` columns needed for Command Chat history
and sending (SPEC-BE-023). The live table has created_at but no updated_at,
so the model uses the id + tenant mixins rather than TenantScopedModel.
session_id and cost_cents stay unmapped. SPEC-BE-033 adds the LLM columns
(parsed_intent, llm_model, tokens_*), filled on AI reply rows only, and maps
the live `orchestrator_plans` table.
"""
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TenantScopedMixin, TenantScopedModel, UUIDPrimaryKeyMixin

PLAN_STATUSES = ("proposed", "partially_approved", "approved", "rejected", "executed", "failed",
                 # SPEC-BE-097 job lists: a draft runs nothing until submitted; paused/cancelled by the user.
                 "draft", "submitted", "paused", "cancelled")


class OrchestratorMessage(Base, UUIDPrimaryKeyMixin, TenantScopedMixin):
    __tablename__ = "orchestrator_messages"

    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # The chat this message belongs to (SPEC-BE-099; the live column was unused before).
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Live LLM columns (SPEC-BE-033), set on AI reply rows only.
    parsed_intent: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tokens_input: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_output: Mapped[int | None] = mapped_column(Integer, nullable=True)


class OrchestratorPlan(Base, TenantScopedModel):
    # Live orchestrator_plans (SPEC-BE-033). One row per stored plan; its id is
    # the subject_id of every approval_queue row created for the plan.
    __tablename__ = "orchestrator_plans"

    triggering_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    actions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(*PLAN_STATUSES, name="plan_status", create_type=False),
        default="proposed",
        nullable=False,
    )
    estimated_cost_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Job lists (SPEC-BE-097): run settings, the items and the job template.
    mode: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    concurrency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    progress_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    items: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    template: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class OrchestratorFile(Base, UUIDPrimaryKeyMixin, TenantScopedMixin):
    """A file attached in Command Chat (SPEC-BE-096): the original in storage,
    what was extracted from it in `extracted` (text chunks, records, the media
    ids of its images, warnings)."""

    __tablename__ = "orchestrator_files"

    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    mime: Mapped[str] = mapped_column(Text, nullable=False)
    bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    # A project's knowledge file (SPEC-BE-099).
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="extracted")
    extracted: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OrchestratorProject(Base, UUIDPrimaryKeyMixin, TenantScopedMixin):
    """A Command Chat project (SPEC-BE-099): instructions and knowledge files
    for its chats. Private to its creator (the user's choice)."""

    __tablename__ = "orchestrator_projects"

    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    emoji: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OrchestratorChat(Base, UUIDPrimaryKeyMixin, TenantScopedMixin):
    """One Command Chat conversation (SPEC-BE-099); its messages carry
    session_id = this id. Private to its creator."""

    __tablename__ = "orchestrator_chats"

    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="New chat")
    # auto = may still be replaced by the AI title; manual = renamed by the user (or backfilled).
    title_source: Mapped[str] = mapped_column(Text, nullable=False, default="auto")
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
