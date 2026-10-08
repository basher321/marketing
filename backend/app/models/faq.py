"""FAQ, Macro models.

`FAQ` is mapped to the live `faqs` table (SPEC-BE-013). `channels` is a
channel_type[] array; an empty array means the FAQ applies to all channels.
tags, language, priority and times_used keep their database defaults.
"""
from sqlalchemy import Boolean, Enum, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TenantScopedModel
from app.models.product import CHANNEL_TYPES


class FAQ(Base, TenantScopedModel):
    __tablename__ = "faqs"

    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    channels: Mapped[list[str]] = mapped_column(
        ARRAY(Enum(*CHANNEL_TYPES, name="channel_type", create_type=False)),
        default=list,
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Macro(Base, TenantScopedModel):
    __tablename__ = "macros"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(String(4000), nullable=False)
