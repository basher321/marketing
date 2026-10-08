"""AI Ad Autopilot schemas (SPEC-BE-069).

The form fields are the only source of budget, platforms and dates: the free
text prompt can't change them, and there is no publish/auto-publish field
(user decision 2026-10-02: every run stops for review).
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator

from app.schemas.ads_builder import PlatformKey

Goal = Literal["sales", "traffic", "leads", "awareness", "app"]


class Budget(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    mode: Literal["daily", "total"] = "total"


class Schedule(BaseModel):
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def order(self) -> "Schedule":
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("The end must be after the start.")
        return self


class AICampaignCreate(BaseModel):
    prompt: str = Field(min_length=10, max_length=2000)
    platforms: list[PlatformKey] = Field(min_length=1, max_length=3)
    goal: Goal | None = None
    budget: Budget
    schedule: Schedule = Field(default_factory=Schedule)
    skus: list[str] = Field(default_factory=list, max_length=10)
    landing_url: str = Field(min_length=12, max_length=2048)
    # generate = AI images; products = the featured products' own images;
    # builder = no images now, add them in the builder before publishing.
    visuals: Literal["generate", "products", "builder"] = "generate"
    youtube_video: str | None = Field(default=None, max_length=300)
    variants_per_group: int = Field(default=2, ge=1, le=3)

    @field_validator("prompt")
    @classmethod
    def prompt_text(cls, value: str) -> str:
        if len(value.strip()) < 10:
            raise ValueError("Describe what you want to advertise in at least 10 characters.")
        return value.strip()

    @field_validator("platforms")
    @classmethod
    def unique(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))

    @field_validator("landing_url")
    @classmethod
    def https(cls, value: str) -> str:
        if not value.strip().startswith("https://"):
            raise ValueError("The landing page must start with https://.")
        return value.strip()

    @model_validator(mode="after")
    def products_need_skus(self) -> "AICampaignCreate":
        if self.visuals == "products" and not self.skus:
            raise ValueError("Pick at least one product to use its images.")
        return self


class AnswerRequest(BaseModel):
    answers: list[str] = Field(min_length=1, max_length=3)


class RetryRequest(BaseModel):
    from_stage: Literal["context", "plan", "targeting", "copy", "visuals", "safety", "assemble"] | None = None


class PublishRequest(BaseModel):
    acknowledge_warnings: bool = False
    mode: Literal["active", "paused"] = "active"


class RegenerateRequest(BaseModel):
    ref: str = Field(min_length=3, max_length=60)  # "<platform>:g<i>:a<j>"
    what: Literal["copy", "image"]


class Stage(BaseModel):
    name: str
    status: Literal["pending", "running", "done", "failed", "skipped"]
    started_at: datetime | None = None
    ended_at: datetime | None = None
    provider: str | None = None
    note: str | None = None
    error: str | None = None


class SafetyIssue(BaseModel):
    ref: str
    severity: Literal["error", "warning"]
    rule: str
    message: str
    source: str


class PreviewAd(BaseModel):
    ref: str
    platform: str
    format: str
    group: str
    copy_fields: dict[str, Any] = Field(alias="copy")
    images: list[dict[str, Any]]
    angle: str | None = None

    model_config = {"populate_by_name": True}


class PreviewCampaign(BaseModel):
    platform: str
    label: str
    campaign_id: str | None
    name: str
    objective: str
    campaign_type: str | None
    budget: float
    budget_mode: str
    status: str | None
    groups: list[dict[str, Any]]


class AICampaignRunRead(BaseModel):
    id: str
    status: str
    stage: str | None
    prompt: str
    request: dict[str, Any]
    stages: list[Stage]
    questions: list[str]
    summary: str | None
    campaigns: list[PreviewCampaign]
    ads: list[PreviewAd]
    safety: list[SafetyIssue]
    can_publish: bool
    publish_note: str | None
    cost_cents: int
    error: str | None
    created_by: str | None
    created_at: datetime
    updated_at: datetime


class ReadyPlatform(BaseModel):
    key: str
    label: str
    usable: bool
    reason: str | None


class TextAI(BaseModel):
    ready: bool
    models: list[dict[str, Any]]
    reason: str | None


class ImageAI(BaseModel):
    ready: bool
    sources: list[dict[str, Any]]
    reason: str | None


class ReadyProduct(BaseModel):
    sku: str
    title: str
    status: str
    price: float
    compare_at: float | None
    discount_pct: int
    currency: str
    has_photo: bool
    selectable: bool
    reason: str | None


class Readiness(BaseModel):
    platforms: list[ReadyPlatform]
    text_ai: TextAI
    image_ai: ImageAI
    products: list[ReadyProduct]
    brand: dict[str, Any]
    currency: str
    country: str


class AICampaignRunList(BaseModel):
    items: list[dict[str, Any]]
