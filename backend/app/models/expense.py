"""Expense: the live `expenses` table (SPEC-BE-110 DDL)."""
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TenantScopedModel

# Other costs for profit & loss. There is deliberately no "product cost" category:
# product costs come from the products / order items, so they can't be counted twice.
EXPENSE_CATEGORIES = ("shipping", "operating", "other")


class Expense(Base, TenantScopedModel):
    __tablename__ = "expenses"

    category: Mapped[str] = mapped_column(Text, nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    incurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    vendor: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
