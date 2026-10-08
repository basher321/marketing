"""Workflow, WorkflowRun, ActionExecution models.

Workflow and WorkflowRun follow the live `workflows` / `workflow_runs` table
columns (SPEC-BE-014). Python attribute names used by app/workflow_engine are
kept where the live table has an equivalent column (`is_active` -> `enabled`,
`trigger_payload` -> `input`). `Workflow.conditions` is not mapped: the live
table only has `condition_dsl` (text), which has no list-shaped equivalent.
ActionExecution is out of scope for SPEC-BE-014 and is left as-is.
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import (
    TenantScopedMixin,
    TenantScopedModel,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

WORKFLOW_TRIGGER_TYPES = (
    "product_created",
    "product_updated",
    "inventory_low",
    "order_placed",
    "order_fulfilled",
    "order_refunded",
    "order_abandoned_cart",
    "message_received",
    "schedule_cron",
    "ad_threshold_crossed",
    "content_published",
    "manual_owner_command",
)
RUN_STATUSES = ("pending", "running", "succeeded", "failed", "cancelled", "retrying")


class Workflow(Base, TenantScopedModel):
    __tablename__ = "workflows"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    trigger_type: Mapped[str] = mapped_column(
        Enum(*WORKFLOW_TRIGGER_TYPES, name="workflow_trigger_type", create_type=False),
        nullable=False,
    )
    trigger_config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    actions: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column("enabled", Boolean, default=True, nullable=False)
    # Live columns read by the detail view and the test run (SPEC-BE-034): the raw
    # condition text (never parsed) and the version stamped on each run.
    condition_dsl: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Versioning (SPEC-BE-049): saving an edit inserts a new row pointing at the
    # old one; a row some other row points at is "superseded" (history).
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workflows.id"), nullable=True
    )
    # users.id; no ORM ForeignKey so the User model needn't be registered.
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    runs: Mapped[list["WorkflowRun"]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )


class WorkflowRun(Base, UUIDPrimaryKeyMixin, TenantScopedMixin):
    __tablename__ = "workflow_runs"

    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        Enum(*RUN_STATUSES, name="run_status", create_type=False),
        default="pending",
        nullable=False,
    )
    trigger_payload: Mapped[dict] = mapped_column("input", JSONB, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    workflow: Mapped["Workflow"] = relationship(back_populates="runs")
    action_executions: Mapped[list["ActionExecution"]] = relationship(
        back_populates="workflow_run", cascade="all, delete-orphan"
    )


class ActionExecution(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "action_executions"

    workflow_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_runs.id", ondelete="CASCADE")
    )
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    result: Mapped[dict] = mapped_column(JSON, default=dict)

    workflow_run: Mapped["WorkflowRun"] = relationship(back_populates="action_executions")
