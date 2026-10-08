"""Pricing rule schemas (SPEC-BE-042)."""
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, BeforeValidator, Field, model_validator

UUIDStr = Annotated[str, BeforeValidator(lambda v: str(v) if v is not None else v)]

PricingRuleState = Literal["active", "scheduled", "expired", "disabled"]


class PricingRuleCreate(BaseModel):
    """Creatable rules: tiered rules and category/tag scopes are list-only for now."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    rule_type: Literal["percent_discount", "fixed_discount", "fixed_price"]
    # A percentage for percent_discount; major units of the tenant currency otherwise.
    value: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    scope: Literal["all", "sku"]
    product_ids: list[UUID] = Field(default_factory=list, max_length=500)
    min_quantity: int | None = Field(default=None, ge=1)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    priority: int = Field(default=0, ge=0, le=1000)

    @model_validator(mode="after")
    def check_rule(self) -> "PricingRuleCreate":
        if self.rule_type == "percent_discount" and self.value > 100:
            raise ValueError("A percentage discount cannot exceed 100.")
        if self.scope == "sku" and not self.product_ids:
            raise ValueError("Choose at least one product.")
        if self.scope == "all" and self.product_ids:
            raise ValueError("product_ids must be empty when the rule applies to all products.")
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("The end must be after the start.")
        return self


class PricingRuleToggle(BaseModel):
    enabled: bool


class PricingRuleRead(BaseModel):
    id: UUIDStr
    name: str
    description: str | None
    rule_type: str
    value: float
    scope: str
    scope_count: int
    min_quantity: int | None
    starts_at: datetime | None
    ends_at: datetime | None
    priority: int
    enabled: bool
    state: PricingRuleState


class PricingRuleList(BaseModel):
    count: int
    # Tenant currency: fixed amounts are in these major units.
    currency: str
    items: list[PricingRuleRead]
