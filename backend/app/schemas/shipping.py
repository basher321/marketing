"""Shipping zone & rate schemas (SPEC-BE-043)."""
import re
from datetime import time
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
    PlainSerializer,
    field_validator,
    model_validator,
)

UUIDStr = Annotated[str, BeforeValidator(lambda v: str(v) if v is not None else v)]
# cutoff_time goes out as "HH:MM".
HHMM = Annotated[time, PlainSerializer(lambda t: t.strftime("%H:%M"), return_type=str)]

_COUNTRY = re.compile(r"^[A-Z]{2}$")


class ShippingZoneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    country_codes: list[str] = Field(min_length=1, max_length=50)
    regions: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("country_codes")
    @classmethod
    def check_countries(cls, value: list[str]) -> list[str]:
        # Two-letter ISO 3166-1 alpha-2 format, upper-cased, de-duplicated.
        codes = list(dict.fromkeys(c.strip().upper() for c in value))
        bad = [c for c in codes if not _COUNTRY.match(c)]
        if bad:
            raise ValueError(f"Country codes must be two letters (e.g. BD): {', '.join(bad)}")
        return codes

    @field_validator("regions")
    @classmethod
    def clean_regions(cls, value: list[str]) -> list[str]:
        regions = list(dict.fromkeys(r.strip() for r in value if r.strip()))
        if any(len(r) > 100 for r in regions):
            raise ValueError("A region name can be at most 100 characters.")
        return regions


MethodType = Literal["flat_rate", "free_shipping", "carrier_calculated", "local_pickup", "local_delivery"]


class RateConditions(BaseModel):
    """Checkout conditions in major units / grams (SPEC-BE-058)."""

    min_subtotal: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    max_subtotal: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    min_weight_g: int | None = Field(default=None, ge=0)
    max_weight_g: int | None = Field(default=None, gt=0)


class ShippingRateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    carrier: str = Field(min_length=1, max_length=255)
    # Major units of the tenant currency; 0 means free shipping.
    rate: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    free_over: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    sla_days_min: int | None = Field(default=None, ge=0, le=365)
    sla_days_max: int | None = Field(default=None, ge=0, le=365)
    cutoff_time: time | None = None
    method_type: MethodType = "flat_rate"
    conditions: RateConditions | None = None
    # local_pickup / local_delivery details (instructions, location, radius).
    pickup_instructions: str | None = Field(default=None, max_length=1000)
    pickup_location: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def check_sla(self) -> "ShippingRateCreate":
        if (
            self.sla_days_min is not None
            and self.sla_days_max is not None
            and self.sla_days_max < self.sla_days_min
        ):
            raise ValueError("Maximum delivery days cannot be less than the minimum.")
        return self


class ShippingRateToggle(BaseModel):
    active: bool


class ShippingRateUpdate(BaseModel):
    """PATCH /shipping/rates/{id} (SPEC-BE-058): any subset; only sent fields change."""

    active: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    rate: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    free_over: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    conditions: RateConditions | None = None
    sla_days_min: int | None = Field(default=None, ge=0, le=365)
    sla_days_max: int | None = Field(default=None, ge=0, le=365)


class SetupMethod(ShippingRateCreate):
    carrier: str = Field(default="Own delivery", min_length=1, max_length=255)


class SetupZone(ShippingZoneCreate):
    country_codes: list[str] = Field(min_length=1, max_length=50)
    methods: list[SetupMethod] = Field(min_length=1, max_length=20)


class ShippingSetup(BaseModel):
    """POST /shipping/setup: the guided setup (3B)."""

    zones: list[SetupZone] = Field(min_length=1, max_length=50)
    push_to_store: bool = False


class ValidationIssue(BaseModel):
    zone_id: str | None = None
    rate_id: str | None = None
    zone: str | None = None
    rate: str | None = None
    code: str
    message: str
    severity: Literal["error", "warning"]


class ValidationResult(BaseModel):
    ok: bool
    issues: list[ValidationIssue]


class StoreInfo(BaseModel):
    provider: str
    connected: bool
    account_name: str | None


class ShippingStatus(BaseModel):
    store: StoreInfo | None
    detected: bool | None
    mode: Literal["synced", "local", "setup_required"]
    last_sync_at: str | None
    last_sync_status: Literal["ok", "partial", "failed"] | None
    errors: list[dict[str, Any]]
    counts: dict[str, int]
    unsupported: list[str]


class DetectResult(BaseModel):
    detected: bool
    provider: str
    currency: str | None
    preview: dict[str, Any]
    unsupported: list[str]
    warnings: list[str]


class SyncResult(BaseModel):
    created: int
    updated: int
    deactivated: int
    errors: list[str]
    last_sync_at: str
    # Guided setup returns the resulting zones too.
    zones: list["ShippingZoneRead"] = []


class ShippingRateRead(BaseModel):
    id: UUIDStr
    name: str
    carrier: str
    rate: float
    free_over: float | None
    sla_days_min: int | None
    sla_days_max: int | None
    cutoff_time: HHMM | None
    active: bool
    # SPEC-BE-058
    source: str = "local"
    external_id: str | None = None
    method_type: str = "flat_rate"
    conditions: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    validation: ValidationResult | None = None
    # True when the store API can't apply edits to this row (open decision 2).
    read_only: bool = False


class ShippingZoneRead(BaseModel):
    id: UUIDStr
    name: str
    country_codes: list[str]
    regions: list[str]
    active: bool
    rates: list[ShippingRateRead]
    source: str = "local"
    external_id: str | None = None
    rest_of_world: bool = False
    validation: ValidationResult | None = None


class ShippingZoneList(BaseModel):
    # Tenant currency: every rate / free_over amount is in these major units.
    currency: str
    zones: list[ShippingZoneRead]


SyncResult.model_rebuild()
