"""Inventory schemas."""
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

# Live uuid columns come back as uuid.UUID; coerce to str for the API. Without this, any
# non-empty inventory list failed response validation (500) - unnoticed while the table
# was empty; found when demo data was seeded (2026-09-29).
UUIDStr = Annotated[str, BeforeValidator(lambda v: str(v) if v is not None else v)]


class InventoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUIDStr
    variant_id: UUIDStr
    location_id: UUIDStr
    on_hand: int
    available: int
    reorder_point: int
    # SPEC-BE-005 amendment (2026-09-30): what the Inventory tab shows per row.
    committed: int
    sku: str
    product_title: str
    variant_label: str | None
    location_name: str
    low_stock: bool


class InventoryAdjust(BaseModel):
    on_hand: int = Field(ge=0, description="New absolute on_hand quantity; must not be negative.")
    reason: str | None = Field(default=None, max_length=500)
