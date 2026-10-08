"""Integration model.

Maps the live `integrations` table (SPEC-BE-017, SPEC-BE-052). Credentials
entered in the app are one Fernet-encrypted JSON blob (utils/crypto, keyed by
ENCRYPTION_KEY) in `settings["secrets_enc"]`: the live `credentials_ref` is
varchar(255) NOT NULL - too short for the blob - so it holds the reference
"app:settings.secrets_enc" (or "" once disconnected). Non-secret fields live in
`settings["fields"]`; `metadata["verified_at"]` records the last successful test.
"""
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TenantScopedModel

INTEGRATION_PROVIDERS = (
    "facebook",
    "instagram",
    "tiktok",
    "meta_ads",
    "tiktok_ads",
    "google_ads",
    "whatsapp",
    "shopify",
    "woocommerce",
    "hubspot",
    "zoho",
    "salesforce",
    "smtp",
    "sendgrid",
    # Added for the multi-platform Ad Manager (SPEC-BE-062 DDL).
    "linkedin_ads",
    "x_ads",
    "snapchat_ads",
    "pinterest_ads",
    # LinkedIn company page organic posting (SPEC-BE-075 DDL).
    "linkedin",
)
INTEGRATION_STATUSES = ("connected", "disconnected", "expired", "error")


class Integration(Base, TenantScopedModel):
    __tablename__ = "integrations"

    provider: Mapped[str] = mapped_column(
        Enum(*INTEGRATION_PROVIDERS, name="integration_provider", create_type=False),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        Enum(*INTEGRATION_STATUSES, name="integration_status", create_type=False),
        default="connected",
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    account_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    credentials_ref: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    connected_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
