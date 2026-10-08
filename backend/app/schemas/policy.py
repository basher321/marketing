"""Policy schemas (SPEC-BE-048)."""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, BeforeValidator, Field, field_validator, model_validator

UUIDStr = Annotated[str, BeforeValidator(lambda v: str(v) if v is not None else v)]

PolicyType = Literal[
    "returns", "refunds", "exchanges", "warranty", "shipping", "payment", "privacy", "terms", "other"
]


def _strip_required(value: str | None) -> str | None:
    if value is None:
        return value
    value = value.strip()
    if not value:
        raise ValueError("Must not be empty.")
    return value


class PolicyCreate(BaseModel):
    policy_type: PolicyType
    title: str = Field(max_length=255)
    body: str = Field(max_length=20000)
    enabled: bool = True
    effective_from: AwareDatetime | None = None
    effective_until: AwareDatetime | None = None

    @field_validator("title", "body")
    @classmethod
    def not_blank(cls, value: str) -> str:
        return _strip_required(value) or ""

    @model_validator(mode="after")
    def check_dates(self) -> "PolicyCreate":
        if self.effective_from and self.effective_until and self.effective_until <= self.effective_from:
            raise ValueError("'Effective until' must be after 'effective from'.")
        return self


class PolicyUpdate(BaseModel):
    """Only the fields sent are changed; effective dates may be sent as null to clear them."""

    policy_type: PolicyType | None = None
    title: str | None = Field(default=None, max_length=255)
    body: str | None = Field(default=None, max_length=20000)
    enabled: bool | None = None
    effective_from: AwareDatetime | None = None
    effective_until: AwareDatetime | None = None

    @field_validator("title", "body")
    @classmethod
    def not_blank(cls, value: str | None) -> str | None:
        return _strip_required(value)


class PolicyRead(BaseModel):
    id: UUIDStr
    policy_type: str
    title: str
    body: str
    enabled: bool
    effective_from: datetime | None
    effective_until: datetime | None
    updated_at: datetime


class PolicyList(BaseModel):
    count: int
    items: list[PolicyRead]
