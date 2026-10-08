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

from sqlalchemy import BigInteger, DateTime, Enum, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TenantScopedMixin, TenantScopedModel, UUIDPrimaryKeyMixin

PLAN_STATUSES = ("proposed", "partially_approved", "approved", "rejected", "executed", "failed")


class OrchestratorMessage(Base, UUIDPrimaryKeyMixin, TenantScopedMixin):
    __tablename__ = "orchestrator_messages"

    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
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
