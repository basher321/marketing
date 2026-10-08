"""Tenant Pydantic schemas."""
from datetime import datetime, timezone
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from app.utils import locale_data

# Live uuid columns come back as uuid.UUID; coerce to str for the API.
UUIDStr = Annotated[str, BeforeValidator(lambda v: str(v) if v is not None else v)]


class TenantCreate(BaseModel):
    name: str
    slug: str


class BrandingHead(BaseModel):
    name: str | None
    title: str | None
    photo_url: str | None


class Branding(BaseModel):
    """Stored in tenants.metadata["branding"] (SPEC-BE-051); images are data URLs."""

    logo_url: str | None
    banner_url: str | None
    head: BrandingHead


class TenantRead(BaseModel):
    """GET /tenants/me (SPEC-BE-037, extended by SPEC-BE-051)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUIDStr
    name: str
    slug: str
    subdomain: str
    # Live tenant_status enum: active, suspended, trial, cancelled.
    status: str
    currency: str
    timezone: str
    country_code: str | None
    default_language: str
    branding: Branding
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def to_utc(cls, value: datetime) -> datetime:
        # The Postgres server runs in Asia/Dhaka; responses are always UTC.
        return value.astimezone(timezone.utc)

    @field_validator("currency", "country_code")
    @classmethod
    def strip_char(cls, value: str | None) -> str | None:
        # bpchar columns may come back space-padded.
        return value.strip() if value else value


class TenantUpdate(BaseModel):
    """PATCH /tenants/me: only the fields sent are changed."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    timezone: str | None = Field(default=None, max_length=64)
    default_language: str | None = Field(default=None, min_length=2, max_length=10)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Company name cannot be blank.")
        return value.strip() if value else value

    # SPEC-BE-072: checked against the worldwide lists in utils/locale_data (the same
    # lists GET /tenants/locale-options serves). TenantRead isn't checked, so a value
    # saved before this still loads.
    @field_validator("country_code")
    @classmethod
    def valid_country(cls, value: str | None) -> str | None:
        return check_country(value)

    @field_validator("currency")
    @classmethod
    def valid_currency(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip().upper()
        if not locale_data.is_currency(value):
            raise ValueError(f"Unknown currency: {value}. Use a current ISO 4217 code such as USD, EUR or BDT.")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value: str | None) -> str | None:
        return check_timezone(value)

    @field_validator("default_language")
    @classmethod
    def valid_language(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not locale_data.is_language(value):
            raise ValueError(f"Unknown language: {value}. Use a code such as en, bn, pt-BR or zh-Hant.")
        return value


def check_country(value: str | None) -> str | None:
    """ISO 3166-1 alpha-2 country from the worldwide list, upper-cased (SPEC-BE-072)."""
    if value is None:
        return value
    value = value.strip().upper()
    if not locale_data.is_country(value):
        raise ValueError(f"Unknown country code: {value}. Use a two-letter code such as BD, US or DE.")
    return value


def check_timezone(value: str | None) -> str | None:
    """A current IANA zone (SPEC-BE-072); legacy aliases are refused with a hint."""
    if value is None:
        return value
    value = value.strip()
    if locale_data.is_timezone(value):
        return value
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"Unknown timezone: {value}") from None
    current = locale_data.TIMEZONE_ALIASES.get(value)
    if current:
        raise ValueError(f"{value} is an old timezone name; use {current} instead.")
    raise ValueError(
        f"{value} is an old timezone name; choose a current Area/City zone from the list "
        "(for example America/New_York or Asia/Kolkata)."
    )


class CountryOption(BaseModel):
    code: str
    name: str
    currency: str | None
    timezones: list[str]


class CurrencyOption(BaseModel):
    code: str
    name: str
    symbol: str
    decimals: int


class LanguageOption(BaseModel):
    code: str
    name: str
    native_name: str


class TimezoneOption(BaseModel):
    name: str
    offset: str


class LocaleOptions(BaseModel):
    """GET /tenants/locale-options (SPEC-BE-072)."""

    countries: list[CountryOption]
    currencies: list[CurrencyOption]
    languages: list[LanguageOption]
    timezones: list[TimezoneOption]


class BrandingTextUpdate(BaseModel):
    head_name: str | None = Field(default=None, max_length=120)
    head_title: str | None = Field(default=None, max_length=120)


class TenantResetRequest(BaseModel):
    confirm_slug: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class TenantResetResult(BaseModel):
    deleted: dict[str, int]
    reset_at: datetime
