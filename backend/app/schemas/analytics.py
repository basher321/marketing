"""Analytics response schemas."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class ActivityItem(BaseModel):
    """One Dashboard "Recent Activity" entry (SPEC-BE-022), traced to a real row."""

    id: str
    occurred_at: datetime
    # Dot color on the Dashboard: success (green), warning (amber), info (default accent).
    kind: Literal["success", "warning", "info"]
    message: str


class ActivityFeed(BaseModel):
    # Most recent first, last 24 hours only.
    items: list[ActivityItem]


class DailyRevenue(BaseModel):
    date: date
    revenue: float


class SalesSummary(BaseModel):
    """Analytics page Sales tab: four cards + Revenue by Day chart (SPEC-BE-015)."""

    revenue_7d: float
    revenue_7d_delta_pct: float
    orders_7d: int
    aov_7d: float
    refund_rate_7d_pct: float
    refund_rate_7d_delta_pp: float
    revenue_by_day: list[DailyRevenue]


class TopProduct(BaseModel):
    """One row of the Analytics page Top Products table (SPEC-BE-016)."""

    product_id: str
    product: str
    units_sold: int
    revenue: float
    trend_pct: float


# ---- SPEC-BE-050: Ads / Engagement / Customer Service reports. A None metric
# has no source data yet (the UI shows "—" with missing_reason); never estimated.
RangeKey = Literal["7d", "30d", "90d"]


class AdsTotals(BaseModel):
    spend: float
    active_campaigns: int
    budget_total: float
    budget_used_pct: float | None
    impressions: int | None
    clicks: int | None
    ctr: float | None
    roas: float | None
    # SPEC-BE-056 (imported Meta results; null when Meta reported none).
    reach: int | None = None
    conversions: int | None = None
    missing_reason: str
    source: str | None = None


class DailySpend(BaseModel):
    date: date
    spend: float
    impressions: int | None = None
    clicks: int | None = None
    ctr: float | None = None
    roas: float | None = None


class AdsCampaignRow(BaseModel):
    id: str
    name: str
    status: str
    channels: list[str]
    budget: float
    spend: float
    pacing_pct: float | None
    starts_at: datetime | None
    ends_at: datetime | None


class AdsReport(BaseModel):
    currency: str
    range: RangeKey
    totals: AdsTotals
    spend_by_day: list[DailySpend]
    campaigns: list[AdsCampaignRow]


class PostCounts(BaseModel):
    published: int
    scheduled: int
    pending: int
    failed: int


class PostsByChannel(BaseModel):
    channel: str
    published: int
    scheduled: int


class PostsByDay(BaseModel):
    date: date
    published: int
    scheduled: int


class ContentPipeline(BaseModel):
    draft: int
    pending_approval: int
    approved: int
    published: int


class EngagementReport(BaseModel):
    range: RangeKey
    posts: PostCounts
    posts_by_channel: list[PostsByChannel]
    # The window plus the next 7 days, so upcoming posts show.
    posts_by_day: list[PostsByDay]
    content: ContentPipeline
    likes: int | None
    comments: int | None
    shares: int | None
    reach: int | None
    missing_reason: str


class ConversationCounts(BaseModel):
    total: int
    open: int
    pending: int
    resolved: int
    escalated: int


class ConversationsByChannel(BaseModel):
    channel: str
    total: int
    resolved: int


class ConversationsByDay(BaseModel):
    date: date
    new: int
    resolved: int


class ReplyCounts(BaseModel):
    ai: int
    agent: int
    ai_share_pct: float | None


class ServiceReport(BaseModel):
    range: RangeKey
    conversations: ConversationCounts
    by_channel: list[ConversationsByChannel]
    by_day: list[ConversationsByDay]
    first_response_minutes_avg: float | None
    resolution_hours_avg: float | None
    csat_avg: float | None
    csat_responses: int
    replies: ReplyCounts
    deflection_pct: float | None


# --- Organic analytics (SPEC-BE-078) -------------------------------------------
class OrganicTotals(BaseModel):
    impressions: float | None
    reach: float | None
    likes: float | None
    comments: float | None
    shares: float | None
    saves: float | None
    clicks: float | None
    video_views: float | None
    engagements: float | None


class OrganicPlatformRow(BaseModel):
    platform: str
    posts_published: int
    impressions: float | None
    engagements: float | None
    engagement_rate: float | None


class OrganicDay(BaseModel):
    date: date
    posts: int
    impressions: float | None
    engagements: float | None


class OrganicTopPost(BaseModel):
    post_id: str
    platform: str
    excerpt: str
    external_url: str | None
    published_at: datetime
    engagements: float
    impressions: float | None


class OrganicReport(BaseModel):
    range: str
    timezone: str
    posts_published: int
    totals: OrganicTotals
    engagement_rate: float | None
    by_platform: list[OrganicPlatformRow]
    daily: list[OrganicDay]
    top_posts: list[OrganicTopPost]
    last_import_at: datetime | None
    missing_reason: str | None


class OrganicImportResult(BaseModel):
    posts: int
    rows: int
    platforms: dict[str, int]
    errors: list[str]
