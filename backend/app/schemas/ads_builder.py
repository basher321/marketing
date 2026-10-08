"""Multi-platform Ad Manager schemas (SPEC-BE-062).

One shape serves TikTok, Google Ads, YouTube, LinkedIn, X, Snapchat and Pinterest. The
platform-specific settings travel in `fields` / `targeting` / `creative` dicts
whose keys each platform spec (SPEC-BE-063..068) defines; the service checks
them in `validate`. Meta keeps its own builder (schemas/meta.py).
"""
import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, Field, field_validator

PlatformKey = Literal["meta", "tiktok", "google", "youtube", "linkedin", "x", "snapchat", "pinterest"]
BuilderPlatform = Literal["tiktok", "google", "youtube", "linkedin", "x", "snapchat", "pinterest"]
BudgetMode = Literal["daily", "total", "none"]
Level = Literal["campaign", "group", "ad"]

MAX_DICT_BYTES = 20_000


def _small(value: dict[str, Any] | None) -> dict[str, Any] | None:
    # Free-form platform settings are bounded so a client can't store megabytes.
    if value is not None and len(json.dumps(value, default=str)) > MAX_DICT_BYTES:
        raise ValueError("Too many settings in one request.")
    return value


def _name(value: str | None) -> str | None:
    if value is not None and not value.strip():
        raise ValueError("Name is required.")
    return value.strip() if value else value


# --- registry ----------------------------------------------------------------
class PlatformObjective(BaseModel):
    key: str
    label: str
    description: str
    available: bool
    reason: str | None = None


class Hierarchy(BaseModel):
    campaign: str
    group: str
    ad: str


class Platform(BaseModel):
    key: PlatformKey
    label: str
    runs_on: str
    channels: list[str]
    hierarchy: Hierarchy
    connected: bool
    account_name: str | None
    connect_hint: str
    objectives: list[PlatformObjective]
    campaign_types: list[PlatformObjective] = []
    creative: dict[str, Any]
    # "live": publishing works once connected; "needs_connection": connect first;
    # "not_built": this platform's publishing spec isn't implemented yet.
    publishing: Literal["live", "needs_connection", "not_built"]


class PlatformList(BaseModel):
    platforms: list[Platform]


# --- requests ------------------------------------------------------------------
class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    objective: str = Field(min_length=1, max_length=50)
    campaign_type: str | None = Field(default=None, max_length=50)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        return _name(value)


class CampaignFields(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    objective: str | None = Field(default=None, min_length=1, max_length=50)
    campaign_type: str | None = Field(default=None, max_length=50)
    budget_mode: BudgetMode | None = None
    # Major units of the tenant currency; stored as integer cents.
    budget: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    fields: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        return _name(value)

    @field_validator("fields")
    @classmethod
    def bounded(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return _small(value)


class GroupFields(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    budget_mode: BudgetMode | None = None
    budget: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    targeting: dict[str, Any] | None = None
    fields: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        return _name(value)

    @field_validator("targeting", "fields")
    @classmethod
    def bounded(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return _small(value)


class AdFields(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    creative: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        return _name(value)

    @field_validator("creative")
    @classmethod
    def bounded(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return _small(value)


class PublishRequest(BaseModel):
    mode: Literal["active", "paused"] = "active"


# --- responses -----------------------------------------------------------------
class Issue(BaseModel):
    level: Level
    id: str | None
    path: str
    message: str
    severity: Literal["error", "warning"] = "error"


class TreeAd(BaseModel):
    id: str
    name: str
    status: str
    external_id: str | None
    creative: dict[str, Any]


class TreeGroup(BaseModel):
    id: str
    name: str
    status: str
    external_id: str | None
    budget_mode: BudgetMode
    budget: float | None
    starts_at: datetime | None
    ends_at: datetime | None
    targeting: dict[str, Any]
    fields: dict[str, Any]
    ads: list[TreeAd]


class TreeCampaign(BaseModel):
    id: str
    name: str
    objective: str
    objective_label: str
    campaign_type: str | None
    status: str
    currency: str
    budget_mode: BudgetMode
    budget: float | None
    starts_at: datetime | None
    ends_at: datetime | None
    fields: dict[str, Any]
    external_id: str | None
    last_error: str | None
    pending_approval_id: str | None


class PlatformTree(BaseModel):
    platform: BuilderPlatform
    label: str
    hierarchy: Hierarchy
    campaign: TreeCampaign
    groups: list[TreeGroup]
    issues: list[Issue]
    connection: dict[str, Any]
    approval: dict[str, Any] | None


class ValidateResult(BaseModel):
    ok: bool
    issues: list[Issue]


class StatusResult(BaseModel):
    id: str
    name: str
    level: Level
    status: str


class LookupItem(BaseModel):
    id: str
    name: str
    type: str | None = None
    extra: dict[str, Any] = {}


class SyncError(BaseModel):
    campaign_id: str | None
    message: str
    at: str


class ResultsSync(BaseModel):
    synced_campaigns: int
    rows_written: int
    last_sync_at: datetime
    errors: list[SyncError]


class MediaResult(BaseModel):
    media_id: str
    kind: Literal["image", "video"]
    name: str
    thumbnail_url: str | None = None
