"""Photo / video generation schemas (SPEC-BE-077)."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.media import MediaOut
from app.schemas.organic import Target

Ratio = Literal["1:1", "4:5", "9:16", "16:9", "1.91:1", "2:3", "3:2"]
TargetPlatform = Literal["facebook", "instagram", "tiktok", "linkedin"]
_STRICT = ConfigDict(extra="forbid")


class PhotoRequest(BaseModel):
    model_config = _STRICT

    prompt: str = Field(min_length=3, max_length=4000)
    product_ids: list[str] = Field(default_factory=list, max_length=5)
    reference_media_ids: list[str] = Field(default_factory=list, max_length=3)
    aspect_ratio: Ratio | None = None
    style: str | None = Field(default=None, max_length=200)
    target_platform: TargetPlatform | None = None
    count: int = Field(default=1, ge=1, le=4)


class VideoRequest(BaseModel):
    model_config = _STRICT

    prompt: str = Field(min_length=3, max_length=4000)
    product_ids: list[str] = Field(default_factory=list, max_length=5)
    reference_media_ids: list[str] = Field(default_factory=list, max_length=3)
    aspect_ratio: Literal["9:16", "16:9", "1:1"] | None = None
    duration_s: int = Field(default=8, ge=2, le=60)
    style: str | None = Field(default=None, max_length=200)
    negative_prompt: str | None = Field(default=None, max_length=500)
    target_platform: TargetPlatform | None = None


class RegenerateRequest(BaseModel):
    """Same request as the original, with any of these fields changed."""

    model_config = _STRICT

    prompt: str | None = Field(default=None, min_length=3, max_length=4000)
    aspect_ratio: str | None = Field(default=None, max_length=10)
    duration_s: int | None = Field(default=None, ge=2, le=60)
    style: str | None = Field(default=None, max_length=200)
    negative_prompt: str | None = Field(default=None, max_length=500)


class EditRequest(BaseModel):
    model_config = _STRICT

    instruction: str = Field(min_length=3, max_length=1000)


class CreateContentFromMedia(BaseModel):
    model_config = _STRICT

    caption: str | None = Field(default=None, max_length=63206)
    targets: list[Target] = Field(min_length=1, max_length=4)
    adapt: Literal["rules", "ai"] = "rules"


class ApproveRequest(BaseModel):
    model_config = _STRICT

    create_content: CreateContentFromMedia | None = None


class JobOut(BaseModel):
    id: str
    kind: Literal["image", "video"]
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    request: dict[str, Any]
    effective: dict[str, Any]
    provider: str | None
    model: str | None
    attempts: list[dict[str, Any]]
    media: MediaOut | None
    parent_job_id: str | None
    approved_at: datetime | None
    cost_cents: int
    error: str | None
    notes: list[str]
    content_id: str | None
    created_at: datetime
    finished_at: datetime | None


class JobList(BaseModel):
    count: int
    items: list[JobOut]


class StartResult(BaseModel):
    jobs: list[JobOut]


class ProviderReadiness(BaseModel):
    key: str
    label: str
    ready: bool
    reason: str | None
    model: str | None
    durations: list[int]
    aspect_ratios: list[str]
    reference_images: bool


class Readiness(BaseModel):
    image: list[ProviderReadiness]
    video: list[ProviderReadiness]
    image_ready: bool
    video_ready: bool
    setup_hint: str
