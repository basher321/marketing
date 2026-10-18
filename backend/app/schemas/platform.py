"""Super admin schemas (SPEC-BE-101): PilotSonic's own keys and app credentials."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SettingGroup = Literal["socialapi", "zernio", "meta_app", "tiktok_app", "linkedin_app"]


class PlatformMe(BaseModel):
    super_admin: bool


class SettingField(BaseModel):
    field: str
    label: str
    secret: bool
    set: bool
    # "admin" = saved on the Super admin screen, "server" = from backend/.env, null = not set.
    source: Literal["admin", "server"] | None
    # A secret only masked ("••••" + last 4); a plain value (an app id) as it is.
    value: str | None


class SettingGroupRead(BaseModel):
    group: SettingGroup
    label: str
    fields: list[SettingField]
    last_ok_at: str | None = None
    last_error: str | None = None


class SettingGroupSave(BaseModel):
    """Only the fields sent with a value change; `clear` removes saved ones (the .env value then applies)."""

    values: dict[str, str | None] = Field(default_factory=dict)
    clear: list[str] = Field(default_factory=list, max_length=10)


class SettingTest(BaseModel):
    ok: bool
    message: str


# ---- Company access to the software's keys (SPEC-BE-103) ----
AccessGroup = Literal["ai", "socialapi", "zernio", "meta_app", "tiktok_app", "linkedin_app"]


class AccessGroupInfo(BaseModel):
    group: AccessGroup
    label: str


class CompanyAccess(BaseModel):
    ai: bool
    socialapi: bool
    zernio: bool
    meta_app: bool
    tiktok_app: bool
    linkedin_app: bool


class CompanyRow(BaseModel):
    tenant_id: str
    name: str
    slug: str
    status: str
    created_at: datetime | None = None
    access: CompanyAccess
    # What the company holds at the shared services (made on its first use).
    socialapi_brand: bool
    socialapi_error: str | None = None
    zernio_profile: bool


class CompanyList(BaseModel):
    items: list[CompanyRow]
    total: int
    page: int
    page_size: int
    groups: list[AccessGroupInfo]


class CompanyAccessSave(BaseModel):
    """Only the groups to change: true = may use PilotSonic's key, false = blocked."""

    access: dict[AccessGroup, bool] = Field(min_length=1)
