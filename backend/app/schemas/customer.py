"""Customer schemas (SPEC-BE-007, SPEC-BE-109)."""
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

from app.schemas.order import StatusEventRead


class CustomerCreate(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def contact_required(self) -> "CustomerCreate":
        # Mirrors the live CHECK customer_contact_required (email IS NOT NULL OR phone IS NOT
        # NULL), so a request without either is a 422 here rather than a database error.
        if not self.email and not (self.phone and self.phone.strip()):
            raise ValueError("A customer needs an email or a phone number.")
        return self


class CustomerRead(BaseModel):
    id: str
    first_name: str | None
    last_name: str | None
    email: str | None
    phone: str | None
    created_at: datetime
    # SPEC-BE-109 (added fields; the list keeps its shape).
    order_count: int = 0
    lifetime_value: float = 0.0
    currency: str | None = None
    last_order_at: datetime | None = None


class CustomerPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    first_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None
    last_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None
    email: EmailStr | None = None
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None = None
    address: dict[str, Any] | None = None
    city: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None
    tags: Annotated[list[Annotated[str, StringConstraints(max_length=50)]], Field(max_length=30)] | None = None
    accepts_marketing: bool | None = None


class CustomerProfile(BaseModel):
    id: str
    name: str | None
    first_name: str | None
    last_name: str | None
    phone: str | None
    email: str | None
    address: dict[str, Any] | None
    city: str | None
    country_code: str | None
    tags: list[str]
    accepts_marketing: bool
    sms_opt_out: bool
    order_count: int
    lifetime_value: float
    currency: str
    created_at: datetime


class CustomerOrderRow(BaseModel):
    id: str
    order_number: str
    status: str
    confirmation_state: str
    total: float
    currency: str
    placed_at: datetime
    tracking_number: str | None
    tracking_url: str | None


class CustomerHistoryEvent(StatusEventRead):
    order_id: str
    order_number: str


class CustomerSms(BaseModel):
    id: str
    direction: str
    kind: str
    body: str
    status: str
    interpreted: str | None
    error: str | None
    at: datetime
    order_number: str | None


class CustomerConversation(BaseModel):
    id: str
    channel: str
    status: str
    topic: str | None
    last_message: str | None
    last_message_at: datetime | None
    unread: int


class CustomerRecord(BaseModel):
    customer: CustomerProfile
    current_order: CustomerOrderRow | None
    orders: list[CustomerOrderRow]
    status_history: list[CustomerHistoryEvent]
    sms: list[CustomerSms]
    conversations: list[CustomerConversation]
