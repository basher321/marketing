"""Organic Marketing schemas (SPEC-BE-076)."""
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Platform = Literal["facebook", "instagram", "tiktok", "linkedin"]
PostFormat = Literal["post", "carousel", "reel", "story", "video"]
Part = Literal["caption", "hashtags", "cta", "title"]
_STRICT = ConfigDict(extra="forbid")


def _https(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not value.startswith("https://") or " " in value or len(value) > 2000:
        raise ValueError("Use a full https:// link.")
    return value


class Target(BaseModel):
    model_config = _STRICT

    platform: Platform
    post_format: PostFormat | None = None
    # e.g. TikTok: privacy_level, disable_comment; Instagram: share_to_feed.
    platform_options: dict[str, Any] = Field(default_factory=dict)


class ManualCreate(BaseModel):
    model_config = _STRICT

    title: str | None = Field(default=None, max_length=200)
    caption: str = Field(min_length=1, max_length=63206)
    hashtags: list[str] = Field(default_factory=list, max_length=60)
    cta: str | None = Field(default=None, max_length=200)
    link_url: str | None = None
    media_ids: list[str] = Field(default_factory=list, max_length=20)
    targets: list[Target] = Field(min_length=1, max_length=4)
    adapt: Literal["rules", "ai"] = "rules"

    _link = field_validator("link_url")(classmethod(lambda cls, v: _https(v)))


class AIMedia(BaseModel):
    model_config = _STRICT

    mode: Literal["none", "use", "generate_photo", "generate_video"] = "none"
    media_ids: list[str] = Field(default_factory=list, max_length=20)
    # SPEC-BE-077 request fields (prompt defaults to the post's visual brief).
    generation: dict[str, Any] = Field(default_factory=dict)


class AICreate(BaseModel):
    model_config = _STRICT

    prompt: str = Field(min_length=3, max_length=4000)
    product_ids: list[str] = Field(default_factory=list, max_length=10)
    tone: str | None = Field(default=None, max_length=100)
    link_url: str | None = None
    targets: list[Target] = Field(min_length=1, max_length=4)
    media: AIMedia = Field(default_factory=AIMedia)

    _link = field_validator("link_url")(classmethod(lambda cls, v: _https(v)))


class ContentPatch(BaseModel):
    model_config = _STRICT

    title: str | None = Field(default=None, max_length=200)
    caption: str | None = Field(default=None, min_length=1, max_length=63206)
    hashtags: list[str] | None = Field(default=None, max_length=60)
    cta: str | None = Field(default=None, max_length=200)
    link_url: str | None = None
    media_ids: list[str] | None = Field(default=None, max_length=20)
    readapt: bool = False

    _link = field_validator("link_url")(classmethod(lambda cls, v: _https(v)))


class TargetsPatch(BaseModel):
    model_config = _STRICT

    add: list[Target] = Field(default_factory=list, max_length=4)
    remove: list[Platform] = Field(default_factory=list, max_length=4)


class VersionPatch(BaseModel):
    model_config = _STRICT

    caption: str | None = Field(default=None, max_length=63206)
    hashtags: list[str] | None = Field(default=None, max_length=60)
    cta: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    media_ids: list[str] | None = Field(default=None, max_length=20)
    post_format: PostFormat | None = None
    platform_options: dict[str, Any] | None = None


class RegenerateIn(BaseModel):
    model_config = _STRICT

    parts: list[Part] = Field(min_length=1, max_length=4)
    instruction: str | None = Field(default=None, max_length=500)
    # Always true: regenerating copy never touches the media.
    keep_media: Literal[True] = True


class RevertIn(BaseModel):
    model_config = _STRICT

    variant_index: int = Field(ge=0)


class ScheduleIn(BaseModel):
    model_config = _STRICT

    scheduled_at_local: datetime = Field(description="Wall-clock time without offset, e.g. 2026-10-04T20:00")
    timezone: str | None = Field(default=None, max_length=64)

    @field_validator("scheduled_at_local")
    @classmethod
    def naive(cls, v: datetime) -> datetime:
        if v.tzinfo is not None:
            raise ValueError("Send the local wall-clock time without an offset, plus a timezone.")
        return v


class ScheduleItem(ScheduleIn):
    version_id: str


class BulkSchedule(BaseModel):
    model_config = _STRICT

    items: list[ScheduleItem] = Field(min_length=1, max_length=8)


class MediaRef(BaseModel):
    id: str
    kind: str
    url: str
    width: int | None
    height: int | None
    duration_ms: int | None


class PostOut(BaseModel):
    id: str
    version_id: str
    content_id: str | None
    platform: str
    status: str
    scheduled_at: datetime
    timezone: str
    local_time: str | None
    published_at: datetime | None
    external_post_id: str | None
    external_url: str | None
    error_message: str | None
    retry_count: int
    title: str | None
    excerpt: str


class VersionOut(BaseModel):
    id: str
    platform: Platform
    status: str
    post_format: str
    caption: str
    hashtags: list[str]
    cta: str | None
    title: str | None
    link_url: str | None
    media: list[MediaRef]
    platform_options: dict[str, Any]
    warnings: list[str]
    edited: bool
    variant_index: int
    variant_count: int
    account: dict[str, Any]
    post: PostOut | None


class ContentOut(BaseModel):
    id: str
    title: str | None
    mode: Literal["manual", "ai"]
    prompt: str | None
    caption: str
    hashtags: list[str]
    cta: str | None
    link_url: str | None
    media: list[MediaRef]
    product_ids: list[str]
    status: str
    approved_at: datetime | None
    media_pending: list[str]
    warnings: list[str]
    # SPEC-BE-081: the AI copy was written with the company's recent results.
    performance_used: bool = False
    versions: list[VersionOut]
    created_at: datetime
    updated_at: datetime


class ContentListItem(BaseModel):
    id: str
    title: str | None
    mode: str
    status: str
    excerpt: str
    platforms: list[str]
    thumbnail_url: str | None
    next_post_at: datetime | None
    published_count: int
    created_at: datetime


class ContentList(BaseModel):
    count: int
    items: list[ContentListItem]


class Preview(BaseModel):
    version_id: str
    platform: str
    post_format: str
    text: str
    title: str | None
    link_url: str | None
    media: list[MediaRef]
    account: dict[str, Any]
    warnings: list[str]
    errors: list[str]
    caption_max: int
    more_cutoff: int | None


class CalendarDay(BaseModel):
    date: date
    posts: list[PostOut]


class Calendar(BaseModel):
    timezone: str
    start: date
    end: date
    days: list[CalendarDay]


class History(BaseModel):
    count: int
    items: list[PostOut]


class Summary(BaseModel):
    timezone: str
    scheduled_next_7d: int
    published_30d: int
    failed_open: int
    awaiting_approval: int
    by_platform: dict[str, dict[str, int]]
    upcoming: list[PostOut]
    recent: list[PostOut]
    scheduler: dict[str, Any]


# --- Insights (SPEC-BE-081) -------------------------------------------------
class InsightHour(BaseModel):
    hour: int  # local hour 0-23 in the company timezone
    label: str  # "19:00–20:00"
    avg_engagement_rate: float
    posts: int


class InsightFormat(BaseModel):
    post_format: str
    avg_engagement_rate: float
    posts: int


class InsightPlatform(BaseModel):
    platform: str
    posts_with_results: int
    avg_engagement_rate: float
    best_hours: list[InsightHour]
    best_format: InsightFormat | None
    formats: list[InsightFormat]
    hashtags_top_third: float | None
    hashtags_bottom_third: float | None


class InsightPost(BaseModel):
    post_id: str
    platform: str
    post_format: str
    excerpt: str
    engagement_rate: float
    engagements: float
    impressions: float
    published_at: datetime
    external_url: str | None


class InsightLine(BaseModel):
    platform: str
    text: str


class Insights(BaseModel):
    has_data: bool
    reason: str | None
    days: int
    timezone: str
    platforms: list[InsightPlatform]
    top_posts: list[InsightPost]
    bottom_posts: list[InsightPost]
    lines: list[InsightLine]
    generated_at: datetime
