"""ContentTemplate, ContentAsset models."""
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TenantScopedModel
from app.models.product import CHANNEL_TYPES

CONTENT_STATUSES = ("draft", "pending_approval", "approved", "rejected", "published", "archived")


class ContentTemplate(Base, TenantScopedModel):
    __tablename__ = "content_templates"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    template_type: Mapped[str] = mapped_column(String(50), default="social_post")
    body: Mapped[str] = mapped_column(String(8000), default="")


class ContentAsset(Base, TenantScopedModel):
    # Aligned with the live content_assets table (SPEC-BE-030). The former
    # asset_type / url / extra_metadata columns did not exist live and were
    # removed; `metadata` is mapped as extra_metadata (reserved name).
    # campaign_id has no FK in the live table - services validate it.
    __tablename__ = "content_assets"

    template_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    campaign_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    channel: Mapped[str] = mapped_column(
        Enum(*CHANNEL_TYPES, name="channel_type", create_type=False), nullable=False
    )
    format: Mapped[str] = mapped_column(String(50), nullable=False)
    variants: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    selected_variant_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    media_urls: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    generated_by_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    generation_prompt_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    generation_cost_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(*CONTENT_STATUSES, name="content_status", create_type=False),
        default="draft",
        nullable=False,
    )
    moderation_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    moderation_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    owner_approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    owner_approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )
