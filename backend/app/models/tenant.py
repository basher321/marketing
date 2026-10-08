"""Organization/tenant model.

Mapped to the live `tenants` table (SPEC-BE-036). Only the columns the app reads are mapped;
the rest (subscription_tier, caps, settings, metadata, ...) have database defaults. The
non-existent `is_active`/`plan` mappings were removed: activity is the `status` column (live
`tenant_status` enum: active, suspended, trial, cancelled), mapped as a plain string.
"""
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CHAR, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User


class Tenant(Base, BaseModel):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    subdomain: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="trial")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Organization Settings (SPEC-BE-051). metadata["branding"] holds the logo /
    # banner / company-head photo as data URLs plus the head's name and title;
    # settings["llm_providers"] holds the encrypted AI-model keys (SPEC-BE-053).
    country_code: Mapped[str | None] = mapped_column(CHAR(2), nullable=True)
    default_language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )

    users: Mapped[list["User"]] = relationship(back_populates="tenant")
