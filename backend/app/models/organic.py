"""OrganicContent: the master of an organic post (SPEC-BE-076).

Maps the additive `organic_contents` table (DDL in specs/SPEC-BE-076.md).
Platform versions are content_assets rows (format 'organic_post',
metadata.organic_content_id); schedules are scheduled_posts rows.
"""
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TenantScopedModel

ORGANIC_MODES = ("manual", "ai")
ORGANIC_STATUSES = ("draft", "needs_approval", "approved", "archived")


class OrganicContent(Base, TenantScopedModel):
    __tablename__ = "organic_contents"

    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    caption: Mapped[str] = mapped_column(Text, nullable=False, default="")
    hashtags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    cta: Mapped[str | None] = mapped_column(Text, nullable=True)
    link_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_ids: Mapped[list[str]] = mapped_column(ARRAY(String(36)), nullable=False, default=list)
    product_ids: Mapped[list[str]] = mapped_column(ARRAY(String(36)), nullable=False, default=list)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
