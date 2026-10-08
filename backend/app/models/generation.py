"""GenerationJob: one photo or video generation (SPEC-BE-077).

Maps the additive `generation_jobs` table (DDL in specs/SPEC-BE-077.md),
which has created_at and finished_at only (no updated_at).
"""
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models import media  # noqa: F401 - registers media_assets for the FK below
from app.models.base import TenantScopedMixin, UUIDPrimaryKeyMixin, _utcnow

GENERATION_KINDS = ("image", "video")
GENERATION_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")


class GenerationJob(Base, UUIDPrimaryKeyMixin, TenantScopedMixin):
    __tablename__ = "generation_jobs"

    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    request: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    effective: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    result_media_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    parent_job_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("generation_jobs.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    cost_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
