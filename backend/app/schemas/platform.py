"""Super admin schemas (SPEC-BE-101): PilotSonic's own keys and app credentials."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SettingGroup = Literal[
    "socialapi", "zernio", "meta_app", "tiktok_app", "linkedin_app", "twilio", "whatsapp_app"
]


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
AccessGroup = Literal["ai", "socialapi", "zernio", "meta_app", "tiktok_app", "linkedin_app", "sms", "whatsapp"]


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
    sms: bool = True
    whatsapp: bool = True


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



# ---- SPEC-BE-113: app branding and integration health -------------------------
class AppBranding(BaseModel):
    app_name: str
    tagline: str | None
    logo_url: str | None
    logo_dark_url: str | None
    favicon_url: str | None


class AppBrandingText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_name: str | None = Field(default=None, min_length=1, max_length=60)
    tagline: str | None = Field(default=None, max_length=160)


class IntegrationHealth(BaseModel):
    provider: str
    label: str
    configured: bool
    last_ok_at: str | None
    last_error: str | None
    companies_connected: int
    companies_with_errors: int


class IntegrationHealthList(BaseModel):
    items: list[IntegrationHealth]


class IntegrationErrorRow(BaseModel):
    at: datetime
    provider: str
    kind: str
    company_id: str | None
    company_name: str | None
    message: str


class IntegrationErrorList(BaseModel):
    items: list[IntegrationErrorRow]
    next_cursor: str | None
