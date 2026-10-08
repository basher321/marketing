"""PricingRule model.

Maps the live `pricing_rules` table (SPEC-BE-042). The earlier mapping
(rule_type string, `actions`, `is_active`) matched no live column. `scope` and
`rule_type` are the live Postgres enums; `value` is numeric: a percentage for
percent_discount, an amount in major units of the tenant currency for
fixed_discount / fixed_price. For scope `sku`, `scope_ids` holds product ids.
"""
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TenantScopedModel

PRICING_SCOPES = ("sku", "category", "all", "tag")
PRICING_RULE_TYPES = ("percent_discount", "fixed_discount", "tiered", "fixed_price")


class PricingRule(Base, TenantScopedModel):
    __tablename__ = "pricing_rules"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope: Mapped[str] = mapped_column(
        Enum(*PRICING_SCOPES, name="pricing_scope", create_type=False), nullable=False
    )
    scope_ids: Mapped[list[str]] = mapped_column(
        ARRAY(UUID(as_uuid=False)), nullable=False, default=list
    )
    rule_type: Mapped[str] = mapped_column(
        Enum(*PRICING_RULE_TYPES, name="pricing_rule_type", create_type=False), nullable=False
    )
    value: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    min_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # users.id; no ORM ForeignKey so this module doesn't need the User model registered.
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
