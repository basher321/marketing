"""AI Ad Autopilot runs (SPEC-BE-069): one row per prompt-to-campaign run.

Maps the additive `ai_campaign_runs` table (created 2026-10-02). `stages` is
the per-stage log [{name, status, started_at, ended_at, provider, usage,
output, error}]; `campaign_ids` are the drafts the run assembled.
"""
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TenantScopedModel

RUN_STATUSES = ("queued", "running", "needs_input", "ready_for_review", "publishing", "awaiting_approval", "published", "failed", "cancelled")


class AICampaignRun(Base, TenantScopedModel):
    __tablename__ = "ai_campaign_runs"

    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    request: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    stages: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    campaign_ids: Mapped[list[str]] = mapped_column(ARRAY(UUID(as_uuid=False)), nullable=False, default=list)
    cost_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
