"""Campaign, AdGroup, Ad models."""
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TenantScopedModel
from app.models.product import CHANNEL_TYPES

CAMPAIGN_OBJECTIVES = (
    "awareness",
    "traffic",
    "engagement",
    "conversions",
    "message_replies",
    "reach",
    # SPEC-BE-055 (additive enum values): Meta OUTCOME_LEADS / OUTCOME_APP_PROMOTION.
    "leads",
    "app_promotion",
)
CAMPAIGN_STATUSES = ("draft", "scheduled", "running", "paused", "completed", "failed")


class Campaign(Base, TenantScopedModel):
    """Mapped to the live `campaigns` table (SPEC-BE-009, SPEC-BE-044).

    The live table has `channels` (channel_type[]) and integer-cent money columns;
    `objective` / `status` are the live campaign_objective / campaign_status enums.
    `metadata` (attribute `extra_metadata`) holds the Campaign Wizard's state under
    "wizard": audience_id, creative_asset_id, pending_approval_id (SPEC-BE-044/047).
    """

    __tablename__ = "campaigns"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    objective: Mapped[str] = mapped_column(
        Enum(*CAMPAIGN_OBJECTIVES, name="campaign_objective", create_type=False), nullable=False
    )
    channels: Mapped[list[str]] = mapped_column(
        ARRAY(Enum(*CHANNEL_TYPES, name="channel_type", create_type=False)), nullable=False, default=list
    )
    budget_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    daily_cap_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    spent_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    status: Mapped[str] = mapped_column(
        Enum(*CAMPAIGN_STATUSES, name="campaign_status", create_type=False),
        nullable=False,
        default="draft",
    )
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    # users.id columns; no ORM ForeignKey so the User model needn't be registered.
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    owner_approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    owner_approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    launched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    ad_groups: Mapped[list["AdGroup"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )


class AdGroup(Base, TenantScopedModel):
    """Live `ad_groups` (an ad set): audience, targeting and budget (SPEC-BE-047).
    external_id stays NULL: no ad-platform adapter publishes it yet."""

    __tablename__ = "ad_groups"

    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # audiences.id (ON DELETE SET NULL live); no ORM FK so Audience needn't be imported.
    audience_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    targeting: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    budget_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    bid_strategy: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(*CAMPAIGN_STATUSES, name="campaign_status", create_type=False),
        nullable=False,
        default="draft",
    )
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # SPEC-BE-055 (additive live column): ad-set settings that have no column of
    # their own (budget type, schedule, goal, placements, promoted object, Meta
    # effective status...).
    extra_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    campaign: Mapped["Campaign"] = relationship(back_populates="ad_groups")
    ads: Mapped[list["Ad"]] = relationship(back_populates="ad_group", cascade="all, delete-orphan")


class Ad(Base, TenantScopedModel):
    """Live `ads`: one creative in an ad set (SPEC-BE-047). metadata holds the
    selected variant's text; external_ad_id / external_url stay NULL until an
    ad-platform integration publishes the ad."""

    __tablename__ = "ads"

    ad_group_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ad_groups.id", ondelete="CASCADE"), nullable=False
    )
    # content_assets.id (ON DELETE SET NULL live).
    content_asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(*CAMPAIGN_STATUSES, name="campaign_status", create_type=False),
        nullable=False,
        default="draft",
    )
    external_ad_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )

    ad_group: Mapped["AdGroup"] = relationship(back_populates="ads")
