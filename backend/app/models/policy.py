"""Policy model.

Maps the live `policies` table (SPEC-BE-048): the business's written policies
(returns, refunds, shipping, ...) that the AI may cite in replies.
`structured_rules` keeps its database default ({}); nothing reads it yet.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TenantScopedModel

POLICY_TYPES = (
    "returns",
    "refunds",
    "exchanges",
    "warranty",
    "shipping",
    "payment",
    "privacy",
    "terms",
    "other",
)


class Policy(Base, TenantScopedModel):
    __tablename__ = "policies"

    policy_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
