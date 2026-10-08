"""BrandSettings model.

Mapped to the live `brand_settings` table (SPEC-BE-012): one row per tenant
(UNIQUE tenant_id). Only the columns the Brand Settings card uses are mapped;
tagline, palette, logos, typography, disclaimers, competitor policy and social
handles keep their database defaults. The old tone/voice_guidelines/colors
mappings did not exist in the live table and were removed.

Tone and style have no columns of their own: they live in the `voice_config`
jsonb as integers 0-100 under the keys "tone" and "style" - the same
convention ai/retrieval.get_brand_voice() reads for reply drafting.
"""
from typing import Any

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TenantScopedModel


class BrandSettings(Base, TenantScopedModel):
    __tablename__ = "brand_settings"

    brand_name: Mapped[str] = mapped_column(String(255), nullable=False)
    voice_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    forbidden_terms: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    primary_language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    supported_languages: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=lambda: ["en"], nullable=False
    )
