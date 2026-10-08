"""Customer model.

Mapped to the live `customers` table (SPEC-BE-007). The old full_name and JSON-typed
tags/extra_metadata mappings did not match it: the live table has first_name/last_name,
tags text[] and metadata jsonb. `email` is citext (case-insensitive in the database).
Columns not mapped here (address, consent, lifetime value, order stats, external ids, ...)
keep their database defaults.
"""
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text
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
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
