"""Product response schemas."""
from datetime import datetime

from pydantic import BaseModel


class ProductListItem(BaseModel):
    id: str
    sku: str
    title: str
    # Major currency units as a float plus a currency code - the API's money
    # convention (DB stores integer cents; converted via Decimal / 100).
    price: float
    currency: str
    channels: list[str]
    status: str
    updated_at: datetime
    # Stock (added for SPEC-FE-011's Stock column): SUM(inventory.available) over the
    # product's variants and locations; null when the product has no inventory rows.
    stock: int | None
    # True when any of those inventory rows has available <= reorder_point - the same
    # rule as GET /inventory/low-stock (SPEC-BE-005), so the UI never invents a cutoff.
    low_stock: bool
