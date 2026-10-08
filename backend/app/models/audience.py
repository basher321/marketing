"""Audience model.

Maps the live `audiences` table (SPEC-BE-045): a saved targeting definition
(countries, regions, age range, genders, interests, languages) in the
`targeting` jsonb. `channel` stays NULL (one audience serves every channel);
`estimated_size` stays NULL because no ad-platform data exists to estimate it.
"""
from typing import Any

from sqlalchemy import Enum, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TenantScopedModel
from app.models.product import CHANNEL_TYPES


class Audience(Base, TenantScopedModel):
    __tablename__ = "audiences"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    targeting: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    channel: Mapped[str | None] = mapped_column(
        Enum(*CHANNEL_TYPES, name="channel_type", create_type=False), nullable=True
    )
    estimated_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # users.id; no ORM ForeignKey so this module doesn't need the User model registered.
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
