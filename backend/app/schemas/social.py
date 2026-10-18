"""Connected social accounts (SPEC-BE-075) and their sign-in (SPEC-BE-080)."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SocialFlow = Literal["meta", "tiktok", "linkedin"]


class SocialAccount(BaseModel):
    integration_id: str | None
    platform: Literal["facebook", "instagram", "tiktok", "linkedin"]
    label: str
    account_name: str | None
    handle: str | None
    avatar_url: str | None
    # not_connected: nothing saved; missing_permissions: connected, but a
    # needed permission isn't granted (named in missing_permissions).
    status: Literal["connected", "expired", "error", "missing_permissions", "not_connected"]
    missing_permissions: list[str]
    capabilities: dict[str, bool]
    limits: dict[str, Any]
    extra: dict[str, Any]
    last_error: str | None
    last_published_at: datetime | None
    notes: list[str]
    # SPEC-BE-080: connection details (null / empty when not connected).
    connected_via: Literal["oauth", "token", "socialapi"] | None
    account_id: str | None
    scopes: list[str]
    token_status: Literal["valid", "expiring_soon", "expired", "no_expiry", "unknown"] | None
    token_expires_at: datetime | None
    reconnect_by: datetime | None
    last_checked_at: datetime | None
    last_synced_at: datetime | None
    oauth_available: bool


class SocialAccountList(BaseModel):
    items: list[SocialAccount]


class UseMetaResult(BaseModel):
    facebook: bool
    instagram: bool
    message: str


class OAuthConnectUrl(BaseModel):
    login_url: str


class OAuthCallback(BaseModel):
    code: str = Field(min_length=1, max_length=2048)
    state: str = Field(min_length=1, max_length=4096)


class OAuthChoiceInstagram(BaseModel):
    id: str
    username: str | None


class OAuthChoice(BaseModel):
    id: str
    name: str
    handle: str | None
    avatar_url: str | None
    instagram: OAuthChoiceInstagram | None


class OAuthCallbackResult(BaseModel):
    flow: SocialFlow
    # TikTok: saved at once (one account per sign-in); meta / linkedin: choose.
    saved: bool
    ok: bool
    message: str
    choices: list[OAuthChoice]
    scopes: list[str]


class OAuthSelect(BaseModel):
    account_id: str = Field(min_length=1, max_length=200)
    include_instagram: bool = True


class OAuthSelectResult(BaseModel):
    saved: list[str]
    ok: bool
    message: str
