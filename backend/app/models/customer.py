"""Customer model.

Mapped to the live `customers` table (SPEC-BE-007). The old full_name and JSON-typed
tags/extra_metadata mappings did not match it: the live table has first_name/last_name,
tags text[] and metadata jsonb. `email` is citext (case-insensitive in the database).
SPEC-BE-107/109 map the address, consent and order stats they keep up to date.
Columns not mapped here (external ids) keep their database defaults.
"""
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TenantScopedModel


class Customer(Base, TenantScopedModel):
    __tablename__ = "customers"

    email: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_address: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    accepts_marketing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # consent.sms = false once the customer texts STOP (SPEC-BE-108).
    consent: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    lifetime_value_cents: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    order_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    first_order_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_order_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
