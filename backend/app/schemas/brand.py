"""Brand settings schemas (SPEC-BE-012).

Exactly the Knowledge Base page's Brand Settings card: brand name, tone and
style sliders (0-100), primary language, forbidden terms. The language select's
three mockup options map onto (primary_language, supported_languages):
  "Bangla (default) + English" -> ("bn", ["bn", "en"])
  "English only"               -> ("en", ["en"])
  "Bangla only"                -> ("bn", ["bn"])
"""
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# The languages the mockup offers; primary_language is varchar(10) in the live table.
LanguageCode = Literal["en", "bn"]


class BrandSettingsRead(BaseModel):
    brand_name: str
    tone: int
    style: int
    primary_language: str
    supported_languages: list[str]
    forbidden_terms: list[str]


class BrandSettingsUpdate(BaseModel):
    """PUT /brand body: every field is required - one save replaces them all."""

    brand_name: str = Field(max_length=255)
    # Out-of-range values are rejected (422), never clamped.
    tone: int = Field(ge=0, le=100)
    style: int = Field(ge=0, le=100)
    primary_language: LanguageCode
    supported_languages: list[LanguageCode] = Field(min_length=1)
    # An empty list clears the stored terms.
    forbidden_terms: list[str]

    @field_validator("brand_name")
    @classmethod
    def brand_name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Brand name must not be empty.")
        return value

    @field_validator("supported_languages")
    @classmethod
    def dedupe_languages(cls, value: list[LanguageCode]) -> list[LanguageCode]:
        return list(dict.fromkeys(value))

    @field_validator("forbidden_terms")
    @classmethod
    def clean_terms(cls, value: list[str]) -> list[str]:
        # Stored as a text[] array, one term per element (no delimiter parsing): each term is
        # trimmed, blanks are dropped, and exact duplicates are removed keeping first order.
        return list(dict.fromkeys(t.strip() for t in value if t.strip()))

    @model_validator(mode="after")
    def primary_is_supported(self) -> "BrandSettingsUpdate":
        if self.primary_language not in self.supported_languages:
            raise ValueError("primary_language must be one of supported_languages.")
        return self
