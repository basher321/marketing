"""Order schemas."""
from datetime import datetime

from pydantic import BaseModel


class OrderMetrics(BaseModel):
    """Order counts for the Dashboard / E-Commerce / Analytics cards (SPEC-BE-006)."""

    total: int
    last_24h: int
    last_7d: int
    last_7d_delta_pct: float


class OrderRevenue24h(BaseModel):
    """Dashboard "Revenue (24h)" card (SPEC-BE-018)."""

    revenue_24h: float
    revenue_24h_delta_pct: float


class OrderListItem(BaseModel):
    """One row of the E-Commerce Orders tab (SPEC-BE-041)."""

    id: str
    order_number: str
    placed_at: datetime
    customer_name: str | None
    channel: str
    item_count: int
    total: float
    currency: str
    payment_method: str | None
    payment_status: str | None
    status: str
    tracking_number: str | None


class OrderList(BaseModel):
    """GET /orders: `total` counts every matching order, before limit/offset."""

    total: int
    items: list[OrderListItem]
