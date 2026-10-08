"""FAQ schemas (SPEC-BE-013): the Knowledge Base page's FAQs card."""
from pydantic import BaseModel, field_validator

from app.schemas.content import ChannelType


class FAQCreate(BaseModel):
    question: str
    answer: str
    # Empty (or omitted) means the FAQ applies to all channels ("Applied to: All channels").
    channels: list[ChannelType] = []

    @field_validator("question", "answer")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Must not be empty.")
        return value

    @field_validator("channels")
    @classmethod
    def dedupe_channels(cls, value: list[ChannelType]) -> list[ChannelType]:
        return list(dict.fromkeys(value))


class FAQUpdate(BaseModel):
    """PATCH /faqs/{id} (SPEC-BE-048): only the fields sent are changed."""

    question: str | None = None
    answer: str | None = None
    channels: list[ChannelType] | None = None
    enabled: bool | None = None

    @field_validator("question", "answer")
    @classmethod
    def not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Must not be empty.")
        return value

    @field_validator("channels")
    @classmethod
    def dedupe_channels(cls, value: list[ChannelType] | None) -> list[ChannelType] | None:
        return list(dict.fromkeys(value)) if value is not None else None


class FAQItem(BaseModel):
    id: str
    question: str
    # SPEC-BE-048: the full answer and the enabled flag, so the KB tab can edit them.
    answer: str
    enabled: bool
    # Live channel_type values; [] = all channels.
    channels: list[str]


class FAQList(BaseModel):
    # Always len(items): the "FAQs (N)" heading.
    count: int
    items: list[FAQItem]
