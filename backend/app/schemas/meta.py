"""Meta Ads Manager-style builder schemas (SPEC-BE-055)."""
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator

BuilderObjective = Literal["awareness", "traffic", "engagement", "leads", "app_promotion", "sales"]
BudgetType = Literal["daily", "lifetime"]
Money = Decimal


def _https(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("The link must start with https://.")
    return value.strip()


class TargetRef(BaseModel):
    """A Meta targeting entity picked from Meta's own search."""

    key: str = Field(min_length=1, max_length=100)
    name: str = Field(default="", max_length=255)
    type: str | None = Field(default=None, max_length=50)
    radius: int | None = Field(default=None, ge=1, le=80)
    distance_unit: Literal["kilometer", "mile"] | None = None


class Targeting(BaseModel):
    countries: list[str] = Field(default_factory=list, max_length=50)
    regions: list[TargetRef] = Field(default_factory=list, max_length=200)
    cities: list[TargetRef] = Field(default_factory=list, max_length=250)
    zips: list[TargetRef] = Field(default_factory=list, max_length=500)
    age_min: int = Field(default=18, ge=13, le=65)
    age_max: int = Field(default=65, ge=13, le=65)
    genders: Literal["all", "male", "female"] = "all"
    locales: list[TargetRef] = Field(default_factory=list, max_length=50)
    # Detailed targeting: interests, behaviors, demographics (type = Meta's).
    detailed: list[TargetRef] = Field(default_factory=list, max_length=200)
    custom_audiences: list[TargetRef] = Field(default_factory=list, max_length=50)
    excluded_custom_audiences: list[TargetRef] = Field(default_factory=list, max_length=50)
    advantage_audience: bool = False

    @field_validator("countries")
    @classmethod
    def upper(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(c.strip().upper() for c in value if c.strip()))


class Placements(BaseModel):
    mode: Literal["advantage", "manual"] = "advantage"
    platforms: list[Literal["facebook", "instagram", "messenger", "audience_network"]] = Field(default_factory=list)
    positions: dict[str, list[str]] = Field(default_factory=dict)
    devices: list[Literal["mobile", "desktop"]] = Field(default_factory=list)


class CampaignFields(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    objective: BuilderObjective | None = None
    special_ad_categories: list[Literal["HOUSING", "EMPLOYMENT", "FINANCIAL_PRODUCTS_SERVICES", "ISSUES_ELECTIONS_POLITICS"]] | None = None
    special_ad_category_country: list[str] | None = None
    buying_type: Literal["AUCTION"] | None = None
    budget_mode: Literal["campaign", "ad_set"] | None = None
    budget_type: BudgetType | None = None
    # Campaign budget (Advantage+ campaign budget), major units.
    budget: Money | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    bid_strategy: Literal["LOWEST_COST_WITHOUT_CAP", "LOWEST_COST_WITH_BID_CAP", "COST_CAP", "LOWEST_COST_WITH_MIN_ROAS"] | None = None
    bid_amount: Money | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    roas_floor: Decimal | None = Field(default=None, gt=0, max_digits=8, decimal_places=4)
    spend_cap: Money | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)


class CampaignCreate(CampaignFields):
    name: str = Field(min_length=1, max_length=255)
    objective: BuilderObjective


class AdSetFields(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    conversion_location: Literal["none", "website", "app", "instant_form", "on_ad", "video", "page"] | None = None
    optimization_goal: str | None = Field(default=None, max_length=50)
    pixel_id: str | None = Field(default=None, max_length=50)
    custom_event_type: str | None = Field(default=None, max_length=50)
    app_id: str | None = Field(default=None, max_length=50)
    app_store_url: str | None = Field(default=None, max_length=2048)
    budget_type: BudgetType | None = None
    budget: Money | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    bid_strategy: Literal["LOWEST_COST_WITHOUT_CAP", "LOWEST_COST_WITH_BID_CAP", "COST_CAP", "LOWEST_COST_WITH_MIN_ROAS"] | None = None
    bid_amount: Money | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    targeting: Targeting | None = None
    placements: Placements | None = None
    audience_id: str | None = None  # load a saved audience (SPEC-BE-045) as a start

    @field_validator("app_store_url")
    @classmethod
    def _https_only(cls, value: str | None) -> str | None:
        return _https(value)


class AdSetCreate(AdSetFields):
    name: str = Field(default="New ad set", min_length=1, max_length=255)


class Card(BaseModel):
    # SPEC-BE-082: a card is an image (image_hash) or a video (video_id; the
    # thumbnail becomes Meta's `picture`). Old rows have no `type` -> image.
    type: Literal["image", "video"] = "image"
    image_hash: str | None = Field(default=None, max_length=100)
    video_id: str | None = Field(default=None, max_length=100)
    thumbnail_url: str | None = None
    status: str | None = None
    headline: str = Field(default="", max_length=255)
    description: str = Field(default="", max_length=255)
    link: str | None = Field(default=None, max_length=2048)

    @field_validator("link")
    @classmethod
    def _https_only(cls, value: str | None) -> str | None:
        return _https(value)

    @model_validator(mode="after")
    def _has_media(self) -> "Card":
        if self.type == "image" and not self.image_hash:
            raise ValueError("An image card needs an uploaded image.")
        if self.type == "video" and not self.video_id:
            raise ValueError("A video card needs an uploaded video.")
        return self


class ProductSet(BaseModel):
    id: str = Field(min_length=1, max_length=50)
    name: str = Field(default="", max_length=255)
    catalog_id: str = Field(min_length=1, max_length=50)
    catalog_name: str = Field(default="", max_length=255)
    product_count: int | None = None


class ExistingPost(BaseModel):
    """A Facebook Page post ({page_id}_{post_id}) or an Instagram media id."""

    platform: Literal["facebook", "instagram"]
    id: str = Field(min_length=1, max_length=100)
    message: str = ""
    picture: str | None = None
    permalink_url: str | None = None
    created_time: str | None = None


class PostList(BaseModel):
    items: list[ExistingPost]
    next_cursor: str | None = None


class PostCreate(BaseModel):
    """A new Facebook Page post (always published on the Page, SPEC-BE-082)."""

    message: str = Field(min_length=1, max_length=5000)
    link: str | None = Field(default=None, max_length=2048)
    image_url: str | None = Field(default=None, max_length=2048)

    @field_validator("link", "image_url")
    @classmethod
    def _https_only(cls, value: str | None) -> str | None:
        return _https(value)


class Media(BaseModel):
    type: Literal["image", "video"]
    image_hash: str | None = None
    video_id: str | None = None
    thumbnail_url: str | None = None
    name: str = ""


class Destination(BaseModel):
    type: Literal["website", "app", "instant_form", "none"] = "website"
    url: str | None = Field(default=None, max_length=2048)
    app_store_url: str | None = Field(default=None, max_length=2048)
    lead_form_id: str | None = Field(default=None, max_length=50)

    @field_validator("url", "app_store_url")
    @classmethod
    def _https_only(cls, value: str | None) -> str | None:
        return _https(value)


class AdFields(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    format: Literal["image", "video", "carousel", "existing_post"] | None = None
    media: list[Media] | None = Field(default=None, max_length=1)
    cards: list[Card] | None = Field(default=None, max_length=10)
    carousel_source: Literal["manual", "product_set"] | None = None
    product_set: ProductSet | None = None
    existing_post: ExistingPost | None = None
    primary_text: str | None = Field(default=None, max_length=2200)
    headline: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=255)
    call_to_action: str | None = Field(default=None, max_length=40)
    destination: Destination | None = None
    url_tags: str | None = Field(default=None, max_length=1000)
    use_instagram: bool | None = None
    content_asset_id: str | None = None  # import AI copy (SPEC-BE-046)


class AdCreate(AdFields):
    name: str = Field(default="New ad", min_length=1, max_length=255)


class Issue(BaseModel):
    level: Literal["campaign", "ad_set", "ad"]
    id: str | None
    field: str
    message: str
    source: Literal["local", "meta"] = "local"


class BuilderAd(BaseModel):
    id: str
    name: str
    status: str
    external_ad_id: str | None
    effective_status: str | None = None
    review_feedback: dict[str, Any] | None = None
    last_error: str | None = None
    format: str
    media: list[dict[str, Any]]
    cards: list[dict[str, Any]]
    carousel_source: str = "manual"
    product_set: dict[str, Any] | None = None
    existing_post: dict[str, Any] | None = None
    primary_text: str
    headline: str
    description: str
    call_to_action: str
    destination: dict[str, Any]
    url_tags: str
    use_instagram: bool
    content_asset_id: str | None


class BuilderAdSet(BaseModel):
    id: str
    name: str
    status: str
    external_id: str | None
    effective_status: str | None = None
    last_error: str | None = None
    conversion_location: str
    optimization_goal: str | None
    pixel_id: str | None
    custom_event_type: str | None
    app_id: str | None
    app_store_url: str | None
    budget_type: str
    budget: float | None
    bid_strategy: str | None
    bid_amount: float | None
    starts_at: datetime | None
    ends_at: datetime | None
    targeting: dict[str, Any]
    placements: dict[str, Any]
    ads: list[BuilderAd]


class BuilderCampaign(BaseModel):
    id: str
    name: str
    objective: str
    status: str
    currency: str
    special_ad_categories: list[str]
    special_ad_category_country: list[str]
    buying_type: str
    budget_mode: str
    budget_type: str
    budget: float | None
    bid_strategy: str
    bid_amount: float | None
    roas_floor: float | None
    spend_cap: float | None
    spent: float
    starts_at: datetime | None
    ends_at: datetime | None
    pending_approval_id: str | None
    effective_status: str | None = None


class BuilderTree(BaseModel):
    campaign: BuilderCampaign
    ad_sets: list[BuilderAdSet]
    missing: list[Issue]
    meta: dict[str, Any] | None
    approval: dict[str, Any] | None = None


class ValidateResult(BaseModel):
    ok: bool
    errors: list[Issue]


class PublishRequest(BaseModel):
    mode: Literal["active", "paused"] = "active"


class PreviewResult(BaseModel):
    format: str
    iframe_html: str


class MediaResult(BaseModel):
    type: Literal["image", "video"]
    image_hash: str | None = None
    video_id: str | None = None
    thumbnail_url: str | None = None
    status: str
    name: str


class ObjectiveInfo(BaseModel):
    key: str
    label: str
    description: str
    meta_objective: str
    available: bool
    reason: str | None
    conversion_locations: dict[str, list[str]]
    unavailable_locations: dict[str, str]


class ObjectivesResult(BaseModel):
    objectives: list[ObjectiveInfo]
    bid_strategies: list[str]
    special_ad_categories: list[str]
    placements: dict[str, list[str]]
    calls_to_action: list[str]
    event_types: list[str]
    preview_formats: list[str]
    connection: dict[str, Any]


class LookupItem(BaseModel):
    id: str
    name: str
    type: str | None = None
    extra: dict[str, Any] = {}


class ReachRequest(BaseModel):
    targeting: Targeting
    optimization_goal: str = "REACH"
    placements: Placements | None = None


class ReachResult(BaseModel):
    available: bool
    reason: str | None = None
    daily_reach_lower: int | None = None
    daily_reach_upper: int | None = None


class BudgetUpdate(BaseModel):
    budget: Money = Field(gt=0, max_digits=12, decimal_places=2)
    budget_type: BudgetType = "daily"


class StatusResult(BaseModel):
    id: str
    name: str
    level: str
    status: str
