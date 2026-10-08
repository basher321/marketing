"""MediaAsset: the company's own images and videos (SPEC-BE-074).

Maps the additive `media_assets` table (DDL in specs/SPEC-BE-074.md). The
table has created_at only (no updated_at), so the timestamp mixin isn't used.
created_by / generation_job_id are plain columns: their targets aren't always
imported where this model is, and the FKs live in the DDL.
"""
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TenantScopedMixin, UUIDPrimaryKeyMixin, _utcnow

MEDIA_KINDS = ("image", "video")
MEDIA_SOURCES = ("upload", "ai_image", "ai_video", "catalog", "derived")


class MediaAsset(Base, UUIDPrimaryKeyMixin, TenantScopedMixin):
    __tablename__ = "media_assets"

    kind: Mapped[str] = mapped_column(Text, nullable=False)
    mime: Mapped[str] = mapped_column(Text, nullable=False)
    bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    generation_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
