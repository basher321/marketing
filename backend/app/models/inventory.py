"""Inventory, InventoryLocation, InventoryMovement models.

Inventory and InventoryMovement follow the live `inventory` /
`inventory_movements` table columns (SPEC-BE-005). `inventory.available` is a
database-generated column (`on_hand - committed`), so it is mapped read-only
and never computed or written by application code. Neither table has the
created_at/updated_at pair from TimestampMixin, so these models compose the id
and tenant mixins directly instead of TenantScopedModel.
"""
from datetime import datetime

from sqlalchemy import Computed, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TenantScopedMixin, TenantScopedModel, UUIDPrimaryKeyMixin


class InventoryLocation(Base, TenantScopedModel):
    __tablename__ = "inventory_locations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(String(500), default="")


class Inventory(Base, UUIDPrimaryKeyMixin, TenantScopedMixin):
    __tablename__ = "inventory"

    variant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inventory_locations.id", ondelete="CASCADE"), nullable=False
    )
    on_hand: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    committed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available: Mapped[int] = mapped_column(Integer, Computed("on_hand - committed", persisted=True))
    reorder_point: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    reorder_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InventoryMovement(Base, UUIDPrimaryKeyMixin, TenantScopedMixin):
    __tablename__ = "inventory_movements"

    inventory_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inventory.id", ondelete="CASCADE"), nullable=False
    )
    movement_type: Mapped[str] = mapped_column(String(50), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    performed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
