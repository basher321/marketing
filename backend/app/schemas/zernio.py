"""Zernio paid ads (SPEC-BE-084): request/response models.

Per-platform rules (goals, CTAs, targeting fields, text limits, media kinds)
come from integrations/zernio.PLATFORMS and are enforced here, at the route
boundary; Zernio's own message is shown for anything it refuses beyond that.
Money is Decimal major units (Zernio takes whole units, not cents).
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.integrations.zernio import BID_STRATEGIES, PLATFORMS

PlatformKey = Literal["facebook", "instagram", "tiktok", "linkedin", "pinterest", "twitter", "googleads"]
Id = Field(min_length=1, max_length=200)
OptId = Field(default=None, min_length=1, max_length=200)
Unit = Literal["mile", "kilometer"]


def _rules(platform: str) -> dict[str, Any]:
    return PLATFORMS[platform]


# --- Status, platforms, connect ------------------------------------------------
class Status(BaseModel):
    configured: bool
    profile_ready: bool
    account_count: int | None


class ZAccount(BaseModel):
    id: str
    # Zernio's kind: posting (facebook, instagram, …) or ads (metaads, tiktokads, …)
    kind: str
    username: str | None
    display_name: str | None
    picture_url: str | None
    needs_reconnection: bool
    parent_account_id: str | None


class Goal(BaseModel):
    key: str
    label: str


class PlatformInfo(BaseModel):
    key: str
    label: str
    connected: bool
    ads_accounts: list[ZAccount]
    posting_accounts: list[ZAccount]
    goals: list[Goal]
    ctas: list[str]
    media: list[str]
    targeting: list[str]
    limits: dict[str, int]
    bid: bool
    bid_strategies: list[str]
    validate_supported: bool
    preview_supported: bool
    campaign_types: list[str]
    placements: dict[str, list[str]]
    special_ad_categories: list[str]
    income_tiers: list[str]


class PlatformList(BaseModel):
    configured: bool
    platforms: list[PlatformInfo]


class ConnectRequest(BaseModel):
    platform: PlatformKey


class ConnectResult(BaseModel):
    # step "posting": X needs its posting account first; connect again for ads afterwards.
    auth_url: str | None
    already_connected: bool
    step: Literal["ads", "posting"]


class CallbackRequest(BaseModel):
    """The query string Zernio appends to our redirect_url (plus our signed `zs`)."""
    zs: str = Field(min_length=1, max_length=4096)
    connected: str | None = Field(default=None, max_length=60)
    account_id: str | None = Field(default=None, max_length=200)
    error: str | None = Field(default=None, max_length=200)
    error_message: str | None = Field(default=None, max_length=1000)
    error_reason: str | None = Field(default=None, max_length=200)


class CallbackResult(BaseModel):
    platform: str
    step: str
    connected: bool
    account_id: str | None
    message: str


# --- Ad accounts, identities, targeting ---------------------------------------
class AdAccount(BaseModel):
    id: str
    name: str | None
    currency: str | None
    timezone: str | None
    status: str | None
    selectable: bool
    unusable_reason: str | None
    min_daily_budget: float | None
    business_name: str | None


class AdAccountList(BaseModel):
    items: list[AdAccount]


class IdentityOption(BaseModel):
    id: str
    name: str | None
    kind: str
    detail: str | None


class Identities(BaseModel):
    pages: list[IdentityOption]
    instagram_accounts: list[IdentityOption]
    tiktok_identities: list[IdentityOption]
    default_page_id: str | None
    default_instagram_id: str | None


class SearchHit(BaseModel):
    id: str
    name: str
    type: str | None
    path: str | None
    country_code: str | None
    audience_size: int | None


class SearchResult(BaseModel):
    items: list[SearchHit]


class GeoRef(BaseModel):
    key: str = Field(min_length=1, max_length=120)
    name: str | None = Field(default=None, max_length=200)


class CityRef(GeoRef):
    radius: float | None = Field(default=None, gt=0, le=500)
    distance_unit: Unit | None = None

    @model_validator(mode="after")
    def _pair(self) -> "CityRef":
        if (self.radius is None) != (self.distance_unit is None):
            raise ValueError("A city radius needs both a distance and a unit.")
        return self


class CustomLocation(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius: float = Field(gt=0, le=500)
    distance_unit: Unit
    name: str | None = Field(default=None, max_length=200)


class Entity(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)


class Excluded(BaseModel):
    countries: list[str] = Field(default_factory=list, max_length=250)
    regions: list[GeoRef] = Field(default_factory=list, max_length=200)
    cities: list[GeoRef] = Field(default_factory=list, max_length=200)
    zips: list[GeoRef] = Field(default_factory=list, max_length=500)


class Targeting(BaseModel):
    countries: list[str] = Field(default_factory=list, max_length=250)
    regions: list[GeoRef] = Field(default_factory=list, max_length=200)
    cities: list[CityRef] = Field(default_factory=list, max_length=250)
    zips: list[GeoRef] = Field(default_factory=list, max_length=1000)
    metros: list[GeoRef] = Field(default_factory=list, max_length=200)
    custom_locations: list[CustomLocation] = Field(default_factory=list, max_length=200)
    excluded: Excluded | None = None
    age_min: int | None = Field(default=None, ge=13, le=100)
    age_max: int | None = Field(default=None, ge=13, le=100)
    gender: Literal["all", "male", "female"] = "all"
    languages: list[str] = Field(default_factory=list, max_length=50)
    interests: list[Entity] = Field(default_factory=list, max_length=200)
    behaviors: list[Entity] = Field(default_factory=list, max_length=200)
    income_tier: Literal["top_5", "top_10", "top_10_25", "top_25_50"] | None = None

    @field_validator("countries")
    @classmethod
    def _iso2(cls, v: list[str]) -> list[str]:
        out = [c.strip().upper() for c in v]
        if any(len(c) != 2 or not c.isalpha() for c in out):
            raise ValueError("Countries are 2-letter ISO codes (e.g. BD, US).")
        return list(dict.fromkeys(out))

    @model_validator(mode="after")
    def _ages(self) -> "Targeting":
        if self.age_min is not None and self.age_max is not None and self.age_min > self.age_max:
            raise ValueError("The minimum age can't be above the maximum age.")
        return self

    def used(self) -> set[str]:
        """Capability names (PLATFORMS[...]['targeting']) this spec uses."""
        used: set[str] = set()
        for name in ("countries", "regions", "cities", "zips", "metros", "custom_locations", "languages",
                     "interests", "behaviors"):
            if getattr(self, name):
                used.add(name)
        if any(c.radius for c in self.cities):
            used.add("city_radius")
        if self.excluded and any((self.excluded.countries, self.excluded.regions, self.excluded.cities,
                                  self.excluded.zips)):
            used.add("excluded_locations")
        if self.age_min is not None or self.age_max is not None:
            used.add("age")
        if self.gender != "all":
            used.add("gender")
        if self.income_tier:
            used.add("income_tier")
        return used


class ReachRequest(BaseModel):
    platform: PlatformKey
    account_id: str = Id
    ad_account_id: str = Id
    targeting: Targeting = Field(default_factory=Targeting)
    optimization_goal: str | None = Field(default=None, max_length=60)


class Reach(BaseModel):
    available: bool
    lower: int | None
    upper: int | None
    daily: int | None


# --- Create -------------------------------------------------------------------
class Budget(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    type: Literal["daily", "lifetime"]


class Bid(BaseModel):
    strategy: Literal["LOWEST_COST_WITHOUT_CAP", "LOWEST_COST_WITH_BID_CAP", "COST_CAP", "LOWEST_COST_WITH_MIN_ROAS"]
    amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    roas_floor: Decimal | None = Field(default=None, gt=0, max_digits=8, decimal_places=3)

    @model_validator(mode="after")
    def _fields(self) -> "Bid":
        if self.strategy in ("LOWEST_COST_WITH_BID_CAP", "COST_CAP") and self.amount is None:
            raise ValueError("This bid strategy needs a bid amount.")
        if self.strategy == "LOWEST_COST_WITH_MIN_ROAS" and self.roas_floor is None:
            raise ValueError("A minimum-ROAS strategy needs a ROAS floor (e.g. 2.0).")
        if self.strategy == "LOWEST_COST_WITHOUT_CAP" and (self.amount is not None or self.roas_floor is not None):
            raise ValueError("Automatic bidding takes no bid amount or ROAS floor.")
        return self


class Placements(BaseModel):
    publisher_platforms: list[Literal["facebook", "instagram", "threads", "messenger", "audience_network", "whatsapp"]] = Field(default_factory=list)
    facebook_positions: list[Literal["feed", "right_hand_column", "marketplace", "video_feeds", "story", "search",
                                     "instream_video", "facebook_reels", "facebook_reels_overlay", "profile_feed",
                                     "notification"]] = Field(default_factory=list)
    instagram_positions: list[Literal["stream", "story", "explore", "explore_home", "reels", "profile_feed",
                                      "ig_search", "profile_reels"]] = Field(default_factory=list)
    messenger_positions: list[Literal["messenger_home", "sponsored_messages", "story"]] = Field(default_factory=list)
    audience_network_positions: list[Literal["classic", "rewarded_video"]] = Field(default_factory=list)
    threads_positions: list[Literal["threads_stream"]] = Field(default_factory=list)
    whatsapp_positions: list[Literal["status"]] = Field(default_factory=list)
    device_platforms: list[Literal["mobile", "desktop"]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _parent(self) -> "Placements":
        if not self.publisher_platforms:
            raise ValueError("Manual placements need at least one platform (or use automatic placements).")
        for parent in ("facebook", "instagram", "messenger", "audience_network", "threads", "whatsapp"):
            if getattr(self, f"{parent}_positions") and parent not in self.publisher_platforms:
                raise ValueError(f"Positions on {parent} need {parent} among the platforms.")
        return self


class PromotedObject(BaseModel):
    pixel_id: str | None = Field(default=None, max_length=100)
    custom_event_type: str | None = Field(default=None, max_length=60)
    custom_conversion_id: str | None = Field(default=None, max_length=100)
    application_id: str | None = Field(default=None, max_length=100)
    object_store_url: str | None = Field(default=None, max_length=2000)


class Keyword(BaseModel):
    text: str = Field(min_length=1, max_length=80)
    match: Literal["exact", "phrase", "broad"] = "broad"


class Creative(BaseModel):
    headline: str | None = Field(default=None, max_length=400)
    long_headline: str | None = Field(default=None, max_length=90)
    body: str | None = Field(default=None, max_length=5000)
    description: str | None = Field(default=None, max_length=255)
    call_to_action: str | None = Field(default=None, max_length=40)
    link_url: str | None = Field(default=None, max_length=2000)
    # Our media library ids: one image or one video (Google Display: landscape here + square below).
    media_id: str | None = Field(default=None, max_length=64)
    square_media_id: str | None = Field(default=None, max_length=64)

    @field_validator("link_url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        if v is not None and not v.startswith(("https://", "http://")):
            raise ValueError("The link must start with https:// (or http://).")
        return v


_NO_LINK_GOALS = {"lead_generation", "page_likes", "page_visits"}
_COPY_OPTIONAL_GOALS = {"page_likes"}  # Meta derives the creative from the Page


class CampaignCreate(BaseModel):
    platform: PlatformKey
    account_id: str = Id  # the Zernio ads account (metaads, tiktokads, …) in this company's profile
    ad_account_id: str = Id
    name: str = Field(min_length=1, max_length=255)
    campaign_name: str | None = Field(default=None, max_length=255)
    ad_set_name: str | None = Field(default=None, max_length=255)
    goal: str = Field(min_length=1, max_length=40)
    campaign_type: Literal["display", "search"] | None = None
    budget: Budget
    start_at: datetime | None = None
    end_at: datetime | None = None
    bid: Bid | None = None
    targeting: Targeting = Field(default_factory=Targeting)
    placements: Placements | None = None
    special_ad_categories: list[Literal["HOUSING", "EMPLOYMENT", "CREDIT", "FINANCIAL_PRODUCTS_SERVICES",
                                        "ISSUES_ELECTIONS_POLITICS", "ONLINE_GAMBLING_AND_GAMING"]] = Field(default_factory=list)
    creative: Creative = Field(default_factory=Creative)
    page_id: str | None = OptId
    instagram_account_id: str | None = OptId
    identity_id: str | None = OptId
    organization_id: str | None = OptId
    board_id: str | None = OptId
    promoted_object: PromotedObject | None = None
    lead_gen_form_id: str | None = OptId
    keywords: list[Keyword] = Field(default_factory=list, max_length=1000)
    status: Literal["ACTIVE", "PAUSED"] = "PAUSED"
    # Client-made id for this attempt: sent as Zernio's Idempotency-Key so a retried click never makes two campaigns.
    request_id: str | None = Field(default=None, min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")

    @model_validator(mode="after")
    def _platform_rules(self) -> "CampaignCreate":
        r = _rules(self.platform)
        label = r["label"]
        if self.goal not in r["goals"]:
            raise ValueError(f"{label} doesn't offer the goal '{self.goal}'.")
        # Google campaign type
        if self.platform == "googleads":
            self.campaign_type = self.campaign_type or "display"
        elif self.campaign_type:
            raise ValueError("Display / Search is a Google Ads choice only.")
        # Schedule
        now = datetime.now(timezone.utc)
        for name in ("start_at", "end_at"):
            v = getattr(self, name)
            if v is not None and v.tzinfo is None:
                raise ValueError(f"{name} needs a timezone.")
        if self.start_at and self.start_at < now - timedelta(minutes=5):
            raise ValueError("The start time is in the past.")
        if self.budget.type == "lifetime" and self.end_at is None:
            raise ValueError("A lifetime budget needs an end date.")
        if self.end_at:
            if self.end_at <= (self.start_at or now):
                raise ValueError("The end must be after the start.")
        # Bidding
        if self.bid and not r["bid"]:
            raise ValueError(f"{label} sets its bidding automatically here; leave the bid strategy empty.")
        if self.bid and self.bid.strategy not in BID_STRATEGIES:
            raise ValueError("Unknown bid strategy.")
        # Targeting fields the platform can't honour (Zernio rejects them too)
        unsupported = sorted(self.targeting.used() - set(r["targeting"]))
        if unsupported:
            raise ValueError(f"{label} can't target by: {', '.join(unsupported)}.")
        if self.platform == "googleads" and self.targeting.income_tier not in (None, "top_10"):
            raise ValueError("Google Ads only targets the top 10% income tier.")
        if self.placements and "placements" not in r["targeting"]:
            raise ValueError("Manual placements are a Facebook/Instagram option only.")
        if self.special_ad_categories and "special_ad_categories" not in r["targeting"]:
            raise ValueError("Special ad categories are a Facebook/Instagram option only.")
        # Keywords: Google Search only, and Search needs them
        if self.keywords and not (self.platform == "googleads" and self.campaign_type == "search"):
            raise ValueError("Keywords are for Google Search campaigns only.")
        if self.platform == "googleads" and self.campaign_type == "search" and not self.keywords:
            raise ValueError("A Google Search campaign needs at least one keyword.")
        # Identity fields belong to one platform each
        family = r["family"]
        for name, owner in (("page_id", "meta"), ("instagram_account_id", "meta"), ("identity_id", "tiktok"),
                            ("organization_id", "linkedin"), ("board_id", "pinterest")):
            if getattr(self, name) and family != owner:
                raise ValueError(f"{name} doesn't apply to {label}.")
        self._creative_rules(r)
        self._goal_fields(r)
        return self

    def _creative_rules(self, r: dict[str, Any]) -> None:
        c, label, limits = self.creative, r["label"], r["limits"]
        copy_optional = r["family"] == "meta" and self.goal in _COPY_OPTIONAL_GOALS
        # CTA
        if c.call_to_action:
            if not r["ctas"]:
                raise ValueError(f"{label} doesn't use a call-to-action button.")
            if c.call_to_action not in r["ctas"]:
                raise ValueError(f"{label} doesn't offer the button '{c.call_to_action}'.")
        elif r["family"] == "meta" and not copy_optional:
            raise ValueError("Facebook/Instagram ads need a call-to-action button.")
        # Headline / body
        needs_headline = r["family"] in ("meta", "google", "pinterest", "linkedin", "x") and not copy_optional
        if self.platform == "googleads" and self.campaign_type == "search":
            needs_headline = True
        if needs_headline and not (c.headline or "").strip():
            raise ValueError(f"{label} ads need a headline.")
        if r["family"] == "tiktok" and c.headline:
            raise ValueError("TikTok ads have no headline; use the ad text.")
        if not copy_optional and not (c.body or "").strip():
            raise ValueError("The ad needs its main text.")
        for field, limit in limits.items():
            value = getattr(c, field, None)
            if value and len(value) > limit:
                raise ValueError(f"{label}: the {field.replace('_', ' ')} is {len(value)} characters; the limit is {limit}.")
        if c.long_headline and self.platform != "googleads":
            raise ValueError("A long headline is a Google Ads field only.")
        if c.description and r["family"] != "meta":
            raise ValueError("The link description is a Facebook/Instagram field only.")
        # Link
        if not c.link_url and self.goal not in _NO_LINK_GOALS:
            if r["family"] in ("meta", "google", "x") or (r["family"] == "linkedin" and self.goal == "traffic") \
                    or self.goal == "traffic":
                raise ValueError("The ad needs a link (where people go when they tap it).")
        # Media
        search = self.platform == "googleads" and self.campaign_type == "search"
        if search and (c.media_id or c.square_media_id):
            raise ValueError("Google Search ads are text only; remove the media.")
        if self.platform == "googleads" and self.campaign_type == "display" and not (c.media_id and c.square_media_id):
            raise ValueError("Google Display needs a landscape (1.91:1) and a square (1:1) image.")
        if c.square_media_id and not (self.platform == "googleads" and self.campaign_type == "display"):
            raise ValueError("A second (square) image is for Google Display only.")
        if not search and not copy_optional and not c.media_id:
            raise ValueError(f"{label} ads need {'a video' if r['media'] == ['video'] else 'an image or video' if 'video' in r['media'] else 'an image'}.")

    def _goal_fields(self, r: dict[str, Any]) -> None:
        po, family = self.promoted_object or PromotedObject(), r["family"]
        if family == "meta" and self.goal in ("conversions", "lead_conversion"):
            if not (po.custom_conversion_id or (po.pixel_id and po.custom_event_type)):
                raise ValueError("This goal needs your Meta pixel and the event to optimise for (or a custom conversion).")
        if family == "tiktok" and self.goal == "conversions" and not po.pixel_id:
            raise ValueError("TikTok conversions need your TikTok pixel id.")
        if family == "meta" and self.goal == "app_promotion" and not (po.application_id and po.object_store_url):
            raise ValueError("App promotion needs the app id and its store URL.")
        if self.goal == "lead_generation" and family in ("meta", "linkedin") and not self.lead_gen_form_id:
            raise ValueError("Lead generation needs a lead form id.")
        if self.lead_gen_form_id and self.goal != "lead_generation":
            raise ValueError("A lead form only applies to the lead generation goal.")


class CreateResult(BaseModel):
    platform: str
    campaign_id: str | None
    ad_set_id: str | None
    ad_id: str | None
    status: str | None
    review_status: str | None
    message: str


class ValidateResult(BaseModel):
    supported: bool
    ok: bool
    message: str


class PreviewItem(BaseModel):
    format: str
    html: str | None


class PreviewResult(BaseModel):
    supported: bool
    items: list[PreviewItem]


# --- Boost ----------------------------------------------------------------------
class PostOption(BaseModel):
    id: str
    message: str | None
    created_at: datetime | None
    permalink: str | None
    picture: str | None
    media_type: str | None


class PostList(BaseModel):
    items: list[PostOption]


class BoostTargeting(BaseModel):
    countries: list[str] = Field(default_factory=list, max_length=250)
    regions: list[GeoRef] = Field(default_factory=list, max_length=200)
    cities: list[CityRef] = Field(default_factory=list, max_length=250)
    age_min: int | None = Field(default=None, ge=13, le=65)
    age_max: int | None = Field(default=None, ge=13, le=65)
    gender: Literal["all", "male", "female"] = "all"
    languages: list[str] = Field(default_factory=list, max_length=50)
    interests: list[Entity] = Field(default_factory=list, max_length=200)

    @field_validator("countries")
    @classmethod
    def _iso2(cls, v: list[str]) -> list[str]:
        out = [c.strip().upper() for c in v]
        if any(len(c) != 2 or not c.isalpha() for c in out):
            raise ValueError("Countries are 2-letter ISO codes (e.g. BD, US).")
        return list(dict.fromkeys(out))

    @model_validator(mode="after")
    def _ages(self) -> "BoostTargeting":
        if self.age_min is not None and self.age_max is not None and self.age_min > self.age_max:
            raise ValueError("The minimum age can't be above the maximum age.")
        return self


class BoostCreate(BaseModel):
    platform: Literal["facebook", "instagram", "tiktok", "linkedin", "pinterest", "twitter"]
    account_id: str = Id  # the posting account the post belongs to
    ad_account_id: str = Id
    post_id: str = Field(min_length=1, max_length=200)  # the platform's own post id
    name: str = Field(min_length=1, max_length=255)
    goal: Literal["engagement", "traffic", "awareness", "video_views", "lead_generation", "conversions", "app_promotion"]
    budget: Budget
    start_at: datetime | None = None
    end_at: datetime | None = None
    targeting: BoostTargeting = Field(default_factory=BoostTargeting)
    status: Literal["ACTIVE", "PAUSED"] = "PAUSED"
    request_id: str | None = Field(default=None, min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")

    @model_validator(mode="after")
    def _schedule(self) -> "BoostCreate":
        now = datetime.now(timezone.utc)
        for name in ("start_at", "end_at"):
            v = getattr(self, name)
            if v is not None and v.tzinfo is None:
                raise ValueError(f"{name} needs a timezone.")
        if self.start_at and self.start_at < now - timedelta(minutes=5):
            raise ValueError("The start time is in the past.")
        if self.budget.type == "lifetime" and self.end_at is None:
            raise ValueError("A lifetime budget needs an end date.")
        if self.end_at and self.end_at <= (self.start_at or now):
            raise ValueError("The end must be after the start.")
        return self


# --- Campaign tree and management --------------------------------------------
class Metrics(BaseModel):
    # Zernio's numbers as reported; anything it didn't report stays null (never estimated).
    spend: float | None
    impressions: int | None
    reach: int | None
    clicks: int | None
    ctr: float | None
    cpc: float | None
    cpm: float | None
    conversions: float | None
    roas: float | None


class MoneyAmount(BaseModel):
    amount: float | None
    type: str | None


class AdNode(BaseModel):
    id: str
    name: str | None
    status: str | None
    review_status: str | None
    metrics: Metrics | None


class AdSetNode(BaseModel):
    id: str
    name: str | None
    status: str | None
    budget: MoneyAmount | None
    metrics: Metrics | None
    ads: list[AdNode]


class CampaignNode(BaseModel):
    id: str
    platform: str
    name: str | None
    status: str | None
    review_status: str | None
    objective: str | None
    budget: MoneyAmount | None
    currency: str | None
    ad_account_id: str | None
    ad_account_name: str | None
    created_at: datetime | None
    metrics: Metrics | None
    ad_sets: list[AdSetNode]


class CampaignList(BaseModel):
    items: list[CampaignNode]
    page: int
    pages: int
    total: int
    backfill_pending: bool


class StatusResult(BaseModel):
    status: str | None
    message: str


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    budget: Budget | None = None

    @model_validator(mode="after")
    def _something(self) -> "CampaignUpdate":
        if self.name is None and self.budget is None:
            raise ValueError("Change the name or the budget.")
        return self


class DeleteResult(BaseModel):
    deleted: bool
    ad_count: int | None


class DailyPoint(BaseModel):
    day: str
    spend: float | None
    impressions: int | None
    clicks: int | None
    conversions: float | None


class BreakdownRow(BaseModel):
    dimension: str
    value: str
    spend: float | None
    impressions: int | None
    clicks: int | None


class CampaignAnalytics(BaseModel):
    campaign_id: str
    platform: str
    currency: str | None
    start: str
    end: str
    backfill_pending: bool
    summary: Metrics | None
    daily: list[DailyPoint]
    breakdowns: list[BreakdownRow]
