"""Campaign schemas."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import AwareDatetime, BaseModel, BeforeValidator, Field, field_validator

UUIDStr = Annotated[str, BeforeValidator(lambda v: str(v) if v is not None else v)]

CampaignObjective = Literal[
    "awareness", "traffic", "engagement", "conversions", "message_replies", "reach"
]
ChannelType = Literal[
    "facebook", "instagram", "tiktok", "whatsapp", "messenger", "email", "sms", "web"
]
# The ad's button on Meta (SPEC-BE-054); LEARN_MORE when not chosen.
CallToAction = Literal[
    "SHOP_NOW", "LEARN_MORE", "SIGN_UP", "ORDER_NOW", "CONTACT_US", "BOOK_NOW", "GET_OFFER"
]


class CampaignDraftCreate(BaseModel):
    """Campaign Wizard step 1 (SPEC-BE-044)."""

    name: str = Field(min_length=1, max_length=255)
    objective: CampaignObjective
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Name is required.")
        return value.strip()


class CampaignDraftUpdate(BaseModel):
    """Any subset of the wizard's fields; only the fields sent are changed.
    audience_id / creative_asset_id / description may be sent as null to clear them."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    objective: CampaignObjective | None = None
    description: str | None = Field(default=None, max_length=2000)
    audience_id: uuid.UUID | None = None
    creative_asset_id: uuid.UUID | None = None
    # Major units of the tenant currency (lifetime budget).
    total_budget: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    channels: list[ChannelType] | None = Field(default=None, max_length=8)
    # Where the ad sends people (SPEC-BE-054): https only; null or "" clears it.
    # The public-host check (no private/local address) runs in the service.
    destination_url: str | None = Field(default=None, max_length=2048)
    call_to_action: CallToAction | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Name cannot be blank.")
        return value.strip() if value else value

    @field_validator("destination_url")
    @classmethod
    def check_destination(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        parsed = urlparse(value.strip())
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("The destination link must start with https://.")
        return value.strip()

    @field_validator("channels")
    @classmethod
    def dedupe_channels(cls, value: list[str] | None) -> list[str] | None:
        return list(dict.fromkeys(value)) if value is not None else None


class ApprovalPreview(BaseModel):
    required: bool
    reason: str


class MetaPublishInfo(BaseModel):
    """Where the campaign lives on Meta (SPEC-BE-054). last_error is set when the
    last publish attempt failed (e.g. after an owner approval)."""

    published: bool
    campaign_id: str | None
    adset_id: str | None
    ad_id: str | None
    ads_manager_url: str | None
    last_error: str | None


class CampaignDetail(BaseModel):
    """One campaign as the Campaign Wizard sees it (SPEC-BE-044)."""

    id: UUIDStr
    name: str
    objective: str
    description: str | None
    status: str
    channels: list[str]
    currency: str
    total_budget: float
    daily_budget: float
    duration_days: int | None
    starts_at: datetime | None
    ends_at: datetime | None
    audience_id: str | None
    creative_asset_id: str | None
    # SPEC-BE-047's launch rule, previewed; null until budget + schedule are set.
    approval: ApprovalPreview | None
    pending_approval_id: str | None
    # Wizard steps still incomplete, in order: audience, creative, budget, channels.
    missing: list[str]
    created_at: datetime
    updated_at: datetime
    launched_at: datetime | None
    # SPEC-BE-054: the ad's link and button, and where it was published.
    destination_url: str | None = None
    call_to_action: str | None = None
    meta: MetaPublishInfo | None = None
    # Channels actually running on an ad platform (Meta: facebook/instagram/messenger).
    published_channels: list[str] = []
    # SPEC-BE-055: created in the Ads Manager-style builder.
    builder: bool = False


class CampaignMetrics(BaseModel):
    """Tenant-wide campaign summary (SPEC-BE-009): the Marketing page's "Active Campaigns" and
    "Avg. ROAS" cards and the Dashboard Marketing engine card read this same response."""

    active_campaigns: int
    # Null when no Meta results with purchase value were imported (SPEC-BE-056).
    avg_roas: float | None


class CampaignListItem(BaseModel):
    """One row of the Marketing page "Active Campaigns" table (SPEC-BE-038)."""

    id: str
    name: str
    objective: str
    channels: list[str]
    # Major units from budget_cents, plus the campaign's currency.
    budget: float
    currency: str
    # Whole days from starts_at to ends_at; null if either is missing.
    duration_days: int | None
    # Lifetime ROAS from imported Meta results; null without data (SPEC-BE-056).
    roas: float | None
    status: str
    spent: float = 0.0
    builder: bool = False
    effective_status: str | None = None


class AdSpend24h(BaseModel):
    """Dashboard "Ad Spend" card (SPEC-BE-019): trailing-24h spend in major units plus the
    tenant's currency, paired with SPEC-BE-009's avg ROAS (the same function's value)."""

    ad_spend_24h: float
    currency: str
    avg_roas: float | None


class AdCtr7d(BaseModel):
    """Tenant-wide 7-day CTR as a percentage (SPEC-BE-011)."""

    # Null when no impressions were imported in the last 7 days (SPEC-BE-056).
    ctr_7d_pct: float | None


class MetaSyncResult(BaseModel):
    """POST /campaigns/{id}/sync and /analytics/meta/sync (SPEC-BE-056)."""

    synced_campaigns: int
    rows_written: int
    last_sync_at: datetime
    errors: list[dict]


class ResultKpis(BaseModel):
    spend: float | None
    impressions: int | None
    reach: int | None
    clicks: int | None
    ctr: float | None
    results: int | None
    roas: float | None


class ResultDay(ResultKpis):
    date: str


class ResultRow(ResultKpis):
    id: str
    name: str
    status: str
    effective_status: str | None = None
    ad_set_id: str | None = None


class CampaignResults(BaseModel):
    """GET /campaigns/{id}/results (SPEC-BE-056): imported Meta results only."""

    campaign_id: str
    currency: str
    range: str
    source: str
    result_metric: str
    summary: str
    totals: ResultKpis
    daily: list[ResultDay]
    ad_sets: list[ResultRow]
    ads: list[ResultRow]
    effective_status: str | None
    last_sync_at: datetime | None
