"""Order, OrderItem models.

Order maps the live `orders` columns needed by SPEC-BE-006 (order counts),
SPEC-BE-015 (sales analytics) and SPEC-BE-041 (orders list): order_number,
channel, status, total_cents, currency, payment_method, payment_status,
tracking_number, placed_at. Columns not needed yet stay unmapped. OrderItem
follows the live `order_items` columns (SPEC-BE-016, top products).
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TenantScopedMixin, TenantScopedModel, UUIDPrimaryKeyMixin
from app.models.product import CHANNEL_TYPES

ORDER_STATUSES = (
    "pending",
    "confirmed",
    "processing",
    "shipped",
    "delivered",
    "cancelled",
    "refunded",
)


class Order(Base, TenantScopedModel):
    __tablename__ = "orders"

    customer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("customers.id"), nullable=True)
    order_number: Mapped[str] = mapped_column(String(50), nullable=False)
    channel: Mapped[str] = mapped_column(
        Enum(*CHANNEL_TYPES, name="channel_type", create_type=False), nullable=False
    )
    status: Mapped[str] = mapped_column(
        Enum(*ORDER_STATUSES, name="order_status", create_type=False),
        default="pending",
        nullable=False,
    )
    total_cents: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payment_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    placed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base, UUIDPrimaryKeyMixin, TenantScopedMixin):
    # Follows the live `order_items` table (SPEC-BE-016). There is no
    # product_id column: the product is reached via variant_id ->
    # product_variants.product_id. variant_id becomes NULL if the variant is
    # deleted. The table has created_at only (no updated_at).
    __tablename__ = "order_items"

    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True
    )
    product_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discount_cents: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    line_total_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    order: Mapped["Order"] = relationship(back_populates="items")
