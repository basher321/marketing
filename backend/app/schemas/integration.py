"""Integration schemas."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class IntegrationStatus(BaseModel):
    """One card on the Integrations page (SPEC-BE-017, extended by SPEC-BE-052).
    Secrets are never returned: only which fields are set and a masked hint."""

    provider: str
    name: str
    category: str
    status: Literal["connected", "needs_reconnect", "not_connected"]
    last_synced_at: datetime | None
    account_name: str | None
    # Keys of the fields that have a saved value.
    configured_fields: list[str]
    # Non-secret values as saved; secret values as "••••" + last 4 characters.
    masked: dict[str, str]
    last_error: str | None
    verified_at: datetime | None


class CatalogField(BaseModel):
    key: str
    label: str
    secret: bool
    required: bool
    help: str


class CatalogProvider(BaseModel):
    provider: str
    label: str
    category: str
    fields: list[CatalogField]
    test: bool
    docs_url: str
    # SPEC-BE-101: no token form; connect with the sign-in button, Zernio or SocialAPI.
    connect_only: bool = False


class IntegrationSave(BaseModel):
    """PUT /integrations/{provider}. A secret field sent empty keeps its saved value."""

    account_name: str | None = Field(default=None, max_length=255)
    fields: dict[str, str] = Field(default_factory=dict, max_length=20)


class IntegrationTestResult(BaseModel):
    status: Literal["connected", "needs_reconnect", "not_connected"]
    ok: bool
    message: str
    last_error: str | None
    verified_at: datetime | None
    account_name: str | None


# ---- "Connect with Facebook" (SPEC-BE-054). The token is never returned.
class MetaConnectUrl(BaseModel):
    login_url: str


class MetaCallback(BaseModel):
    code: str = Field(min_length=1, max_length=2048)
    state: str = Field(min_length=1, max_length=4096)


class MetaAdAccount(BaseModel):
    id: str
    name: str
    currency: str
    account_status: int


class MetaInstagram(BaseModel):
    id: str
    username: str | None


class MetaPage(BaseModel):
    id: str
    name: str
    instagram: MetaInstagram | None


class MetaPixel(BaseModel):
    id: str
    name: str
    ad_account_id: str


class MetaChoices(BaseModel):
    """What the connected token can reach; the user picks one of each next."""

    connection_id: str
    ad_accounts: list[MetaAdAccount]
    pages: list[MetaPage]
    pixels: list[MetaPixel]


class MetaSelect(BaseModel):
    ad_account_id: str = Field(min_length=1, max_length=64)
    page_id: str = Field(min_length=1, max_length=64)
    instagram_id: str | None = Field(default=None, max_length=64)
    pixel_id: str | None = Field(default=None, max_length=64)
