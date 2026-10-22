"""Expense schemas (SPEC-BE-110)."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

ExpenseCategory = Literal["shipping", "operating", "other"]
Amount = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]


class ExpenseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: ExpenseCategory
    amount: Amount
    # Optional; must be the company's currency when given (no conversion).
    currency: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, min_length=3, max_length=3)] | None = None
    incurred_on: date
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    vendor: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None


class ExpensePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: ExpenseCategory | None = None
    amount: Amount | None = None
    incurred_on: date | None = None
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)] | None = None
    vendor: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None


class ExpenseRead(BaseModel):
    id: str
    category: ExpenseCategory
    amount: float
    currency: str
    incurred_on: date
    description: str
    vendor: str | None
    created_by_name: str | None
    created_at: datetime


class ExpenseList(BaseModel):
    total: int
    sum: float
    currency: str
    items: list[ExpenseRead]
