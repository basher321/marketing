"""Order schemas."""
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator


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
    # SPEC-BE-107 FR7: the SMS reply position (see order_service.confirmation_state).
    confirmation_state: str


class OrderList(BaseModel):
    """GET /orders: `total` counts every matching order, before limit/offset."""

    total: int
    items: list[OrderListItem]


# ---- SPEC-BE-107: order lifecycle ----------------------------------------

_STRICT = ConfigDict(extra="forbid")

# The live order_status enum after SPEC-BE-107's DDL.
OrderStatusValue = Literal[
    "pending", "awaiting_confirmation", "confirmed", "processing", "shipped", "delivered",
    "returned", "cancelled", "refunded",
]
ConfirmationState = Literal["not_sent", "waiting", "confirmed", "cancelled"]


class OrderCustomerIn(BaseModel):
    """An existing customer (`id`) or a new/matched one (name + phone or email)."""

    model_config = _STRICT
    id: str | None = None
    name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None = None
    email: EmailStr | None = None
    address: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _identified(self) -> "OrderCustomerIn":
        if not self.id and not (self.phone or self.email):
            raise ValueError("A customer needs an id, a phone number or an email.")
        return self


class OrderItemIn(BaseModel):
    model_config = _STRICT
    variant_id: str | None = None
    product_id: str | None = None
    quantity: Annotated[int, Field(ge=1, le=10000)]
    unit_price: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)] | None = None

    @model_validator(mode="after")
    def _one_ref(self) -> "OrderItemIn":
        if bool(self.variant_id) == bool(self.product_id):
            raise ValueError("Each line needs exactly one of variant_id or product_id.")
        return self


Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]


class OrderCreate(BaseModel):
    model_config = _STRICT
    customer: OrderCustomerIn
    items: Annotated[list[OrderItemIn], Field(min_length=1, max_length=200)]
    discount: Money = Decimal(0)
    shipping: Money = Decimal(0)
    tax: Money = Decimal(0)
    payment_method: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None = None
    payment_status: Literal["unpaid", "paid", "cod"] = "unpaid"
    channel: Literal[
        "facebook", "instagram", "tiktok", "whatsapp", "messenger", "email", "sms", "web",
        "google", "linkedin", "x", "snapchat", "pinterest",
    ] = "web"
    notes: Annotated[str, StringConstraints(max_length=2000)] | None = None
    shipping_address: dict[str, Any] | None = None


class OrderStatusChange(BaseModel):
    model_config = _STRICT
    to: OrderStatusValue
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None
    tracking_number: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None
    tracking_url: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None


class OrderPatch(BaseModel):
    """Never status or totals (SPEC-BE-107 FR6)."""

    model_config = _STRICT
    notes: Annotated[str, StringConstraints(max_length=2000)] | None = None
    tags: Annotated[list[Annotated[str, StringConstraints(max_length=50)]], Field(max_length=30)] | None = None
    tracking_number: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None
    tracking_url: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None
    shipping_address: dict[str, Any] | None = None
    payment_status: Literal["unpaid", "paid", "cod", "refunded"] | None = None


class OrderLine(BaseModel):
    id: str
    variant_id: str | None
    product_id: str | None
    sku: str | None
    title: str | None
    variant: str | None
    quantity: int
    unit_price: float
    line_total: float
    unit_cost: float | None


class OrderCustomerSummary(BaseModel):
    id: str
    name: str | None
    phone: str | None
    email: str | None


class StatusEventRead(BaseModel):
    id: str
    from_status: str | None
    to_status: str
    actor_type: str
    actor_name: str | None
    reason: str | None
    at: datetime


class SmsBrief(BaseModel):
    id: str
    direction: str
    kind: str
    body: str
    status: str
    interpreted: str | None
    error: str | None
    at: datetime


class OrderConfirmation(BaseModel):
    state: ConfirmationState
    last_sms: SmsBrief | None
    sms_count: int
    replies: list[SmsBrief]
    can_send: bool
    send_blocked_reason: str | None


class OrderDetail(BaseModel):
    id: str
    order_number: str
    status: str
    channel: str
    placed_at: datetime
    currency: str
    subtotal: float
    discount: float
    shipping: float
    tax: float
    total: float
    payment_method: str | None
    payment_status: str | None
    tracking_number: str | None
    tracking_url: str | None
    shipping_address: dict[str, Any]
    notes: str | None
    tags: list[str]
    fulfilled_at: datetime | None
    delivered_at: datetime | None
    cancelled_at: datetime | None
    customer: OrderCustomerSummary | None
    items: list[OrderLine]
    status_history: list[StatusEventRead]
    confirmation: OrderConfirmation
    allowed_next: list[str]
