"""ScheduledPost model.

Follows the live `scheduled_posts` table columns (SPEC-BE-010). Since
SPEC-BE-076 the publishing columns are mapped too: external_post_id,
external_url, error_message, retry_count, metadata (as extra_metadata;
timezone, local time, attempts, async publish ref, next_attempt_at) and
created_by.
"""
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models import content  # noqa: F401 - registers content_assets for the FK below
from app.models.base import TenantScopedModel
from app.models.product import CHANNEL_TYPES

POST_STATUSES = ("pending", "scheduled", "publishing", "published", "failed", "cancelled")


class ScheduledPost(Base, TenantScopedModel):
    __tablename__ = "scheduled_posts"

    content_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("content_assets.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(
        Enum(*CHANNEL_TYPES, name="channel_type", create_type=False), nullable=False
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(*POST_STATUSES, name="post_status", create_type=False),
        default="pending",
        nullable=False,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_post_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
