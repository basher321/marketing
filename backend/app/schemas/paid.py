"""Paid Marketing lists across campaigns (SPEC-BE-079)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

PaidPlatform = Literal["meta", "tiktok", "google", "youtube", "linkedin", "x", "snapchat", "pinterest", "wizard"]
ResultsLevel = Literal["ad", "campaign"]


class Results(BaseModel):
    spend: float | None
    impressions: int | None
    clicks: int | None
    ctr: float | None
    # "ad": Meta per-ad rows; "campaign": the platform reports per campaign only
    # (results stay null at this level); null: legacy wizard rows.
    results_level: ResultsLevel | None


class AdSetItem(Results):
    id: str
    name: str
    campaign_id: str
    campaign_name: str
    platform: PaidPlatform
    status: str
    effective_status: str | None
    last_error: str | None
    budget: float | None
    budget_type: Literal["daily", "lifetime", "campaign"] | None
    currency: str
    starts_at: datetime | None
    ends_at: datetime | None
    performance_goal: str | None
    ads_count: int


class AdSetList(BaseModel):
    count: int
    items: list[AdSetItem]


class AdItem(Results):
    id: str
    name: str
    ad_set_id: str
    ad_set_name: str
    campaign_id: str
    campaign_name: str
    platform: PaidPlatform
    status: str
    effective_status: str | None
    review_feedback: str | None
    last_error: str | None
    headline: str | None
    text: str | None
    call_to_action: str | None
    destination_url: str | None
    thumbnail_url: str | None
    external_id: str | None
    currency: str


class AdList(BaseModel):
    count: int
    items: list[AdItem]


class StatusResult(BaseModel):
    id: str
    name: str
    level: str
    status: str
