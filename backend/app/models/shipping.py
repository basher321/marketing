"""ShippingZone, ShippingPolicy models.

Map the live `shipping_zones` / `shipping_policies` tables (SPEC-BE-043). In
the live schema a zone (where you ship) has many policies (its rates) via
`shipping_policies.zone_id`; the earlier mapping had that relation reversed
and columns (description, rate, policy_id) that don't exist live. Money is
integer cents in the tenant currency (the tables have no currency column).
"""
from datetime import time

from sqlalchemy import BigInteger, Boolean, CHAR, ForeignKey, Integer, String, Time
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TenantScopedModel


class ShippingZone(Base, TenantScopedModel):
    __tablename__ = "shipping_zones"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # ISO 3166-1 alpha-2 codes, e.g. ["BD"].
    country_codes: Mapped[list[str]] = mapped_column(ARRAY(CHAR(2)), nullable=False, default=list)
    # Optional region names inside those countries; [] means the whole country.
    regions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # SPEC-BE-058 (additive live columns): where the zone came from (local |
    # shopify | woocommerce), the store's id for it, and store details
    # (profile name, rest_of_world, validation result).
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="local")
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extra_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    rates: Mapped[list["ShippingPolicy"]] = relationship(
        back_populates="zone",
        order_by="(ShippingPolicy.rate_cents, ShippingPolicy.name)",
        cascade="all, delete-orphan",
    )


class ShippingPolicy(Base, TenantScopedModel):
    """One shipping rate inside a zone (the UI calls these "rates")."""

    __tablename__ = "shipping_policies"

    zone_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shipping_zones.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    carrier: Mapped[str] = mapped_column(String(255), nullable=False)
    rate_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    free_over_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Local time of day (tenant timezone) after which orders ship next day.
    cutoff_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    sla_days_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sla_days_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # SPEC-BE-058: source/external_id as on zones; method_type is one of
    # flat_rate | free_shipping | carrier_calculated | local_pickup |
    # local_delivery; conditions = {min_subtotal_cents, max_subtotal_cents,
    # min_weight_g, max_weight_g}; metadata = carrier service, fees, pickup
    # instructions, cost formula, validation result.
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="local")
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    method_type: Mapped[str] = mapped_column(String(30), nullable=False, default="flat_rate")
    conditions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    extra_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    zone: Mapped["ShippingZone"] = relationship(back_populates="rates")
