"""Content generation and template schemas."""
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.ai.prompts.content_generator import MAX_BRIEF_CHARS, MAX_SKUS


class ContentGenerateRequest(BaseModel):
    prompt: str
    template_type: str = "social_post"


class ContentGenerateResponse(BaseModel):
    content: str


class ContentTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    template_type: str
    body: str


# Campaign Wizard creative variants (SPEC-BE-030). Input limits reuse
# SPEC-BE-029's constants so the boundary check cannot drift from the
# generator's own validation.
CampaignObjective = Literal[
    "awareness", "traffic", "engagement", "conversions", "message_replies", "reach"
]
ChannelType = Literal[
    "facebook", "instagram", "tiktok", "whatsapp", "messenger", "email", "sms", "web"
]


class CreativeGenerateRequest(BaseModel):
    objective: CampaignObjective
    skus: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]] = Field(
        min_length=1, max_length=MAX_SKUS
    )
    brief: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_BRIEF_CHARS)
    ]
    channel: ChannelType
    campaign_id: uuid.UUID | None = None
    title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None


class CreativeVariantRead(BaseModel):
    index: int
    headline: str
    description: str


class CreativeAssetRead(BaseModel):
    id: str
    campaign_id: str | None
    title: str | None
    channel: str
    format: str
    status: str
    variants: list[CreativeVariantRead]
    selected_variant_index: int | None
    generated_by_model: str | None
    created_at: datetime


class VariantSelectRequest(BaseModel):
    variant_index: int = Field(ge=0)


# Hand-written ad copy (SPEC-BE-046): works without an LLM provider.
Headline = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class ManualVariant(BaseModel):
    headline: Headline
    description: Description = ""


class CreativeManualCreate(BaseModel):
    channel: ChannelType
    campaign_id: uuid.UUID | None = None
    title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None
    variants: list[ManualVariant] = Field(min_length=1, max_length=5)


class VariantEditRequest(BaseModel):
    """Only the fields sent are changed."""

    headline: Headline | None = None
    description: Description | None = None
