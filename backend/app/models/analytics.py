"""AnalyticsEvent model, aligned with the live `analytics_events` table (SPEC-BE-056).

The live table is partitioned (primary key id + event_time). Writers use a
Core table (campaign_service) for bulk inserts; this mapping is for reads.
"""
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TenantScopedMixin, UUIDPrimaryKeyMixin


class AnalyticsEvent(Base, UUIDPrimaryKeyMixin, TenantScopedMixin):
    __tablename__ = "analytics_events"

    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    metric: Mapped[str | None] = mapped_column(String(100), nullable=True)
    value: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    dimensions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
