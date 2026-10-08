"""Audience schemas (SPEC-BE-045)."""
import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, Field, field_validator, model_validator

UUIDStr = Annotated[str, BeforeValidator(lambda v: str(v) if v is not None else v)]

_COUNTRY = re.compile(r"^[A-Z]{2}$")


def _clean(values: list[str], max_len: int) -> list[str]:
    # Trimmed, blanks dropped, de-duplicated (order kept).
    cleaned = list(dict.fromkeys(v.strip() for v in values if v.strip()))
    if any(len(v) > max_len for v in cleaned):
        raise ValueError(f"Each entry can be at most {max_len} characters.")
    return cleaned


class AudienceTargeting(BaseModel):
    countries: list[str] = Field(min_length=1, max_length=50)
    regions: list[str] = Field(default_factory=list, max_length=100)
    age_min: int = Field(default=18, ge=13, le=65)
    age_max: int = Field(default=65, ge=13, le=65)
    # Empty = all genders.
    genders: list[Literal["male", "female"]] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list, max_length=50)
    languages: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("countries")
    @classmethod
    def check_countries(cls, value: list[str]) -> list[str]:
        codes = list(dict.fromkeys(c.strip().upper() for c in value if c.strip()))
        bad = [c for c in codes if not _COUNTRY.match(c)]
        if not codes or bad:
            raise ValueError("Countries must be two-letter codes (e.g. BD).")
        return codes

    @field_validator("regions", "interests")
    @classmethod
    def clean_text_lists(cls, value: list[str]) -> list[str]:
        return _clean(value, 100)

    @field_validator("languages")
    @classmethod
    def clean_languages(cls, value: list[str]) -> list[str]:
        return [v.lower() for v in _clean(value, 10)]

    @field_validator("genders")
    @classmethod
    def dedupe_genders(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def check_ages(self) -> "AudienceTargeting":
        if self.age_max < self.age_min:
            raise ValueError("Maximum age cannot be less than the minimum age.")
        return self


class AudienceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    targeting: AudienceTargeting

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Name is required.")
        return value.strip()


class AudienceRead(BaseModel):
    id: UUIDStr
    name: str
    description: str | None
    targeting: dict[str, Any]
    # Always null: no ad-platform data exists to estimate reach.
    estimated_size: int | None
    created_at: datetime


class AudienceList(BaseModel):
    count: int
    items: list[AudienceRead]
