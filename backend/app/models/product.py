"""Product, ProductVariant models.

Product follows the live `products` table columns (SPEC-BE-008): `title`,
`default_price_cents`, `status`, `channels`, `deleted_at`. ProductVariant is
out of scope for SPEC-BE-008 and is left as-is.
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TenantScopedModel, TimestampMixin, UUIDPrimaryKeyMixin

PRODUCT_STATUSES = ("draft", "active", "archived", "out_of_stock")
# The last five were added for the multi-platform Ad Manager (SPEC-BE-062 DDL).
CHANNEL_TYPES = (
    "facebook", "instagram", "tiktok", "whatsapp", "messenger", "email", "sms", "web",
    "google", "linkedin", "x", "snapchat", "pinterest",
)


class Product(Base, TenantScopedModel):
    __tablename__ = "products"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sku: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    default_price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    # Stored status only - never derived from stock (SPEC-BE-008).
    status: Mapped[str] = mapped_column(
        Enum(*PRODUCT_STATUSES, name="product_status", create_type=False),
        default="draft",
        nullable=False,
    )
    # Channel mapping (SPEC-BE-008): the live table has a native
    # `products.channels` column (channel_type[]), so channels are returned
    # exactly as stored - no approximation from any other field, and an empty
    # array stays an empty list. channel_type only allows the CHANNEL_TYPES
    # values above; the HTML's "Shopify" and "All channels" labels are not
    # representable here and are never fabricated.
    channels: Mapped[list[str]] = mapped_column(
        ARRAY(Enum(*CHANNEL_TYPES, name="channel_type", create_type=False)),
        default=list,
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    variants: Mapped[list["ProductVariant"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class ProductVariant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "product_variants"

    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    product: Mapped["Product"] = relationship(back_populates="variants")
