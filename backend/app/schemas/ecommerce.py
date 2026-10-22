"""E-Commerce business type, hand-made products, categories and payments (SPEC-BE-111)."""
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

BusinessType = Literal["online_retail", "physical_store", "catalog", "digital", "other"]
Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
Text255 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class TabInfo(BaseModel):
    key: str
    label: str
    label_bn: str


class FieldInfo(BaseModel):
    key: str
    label: str
    label_bn: str | None = None
    type: str | None = None
    required: bool


class TypeChoice(BaseModel):
    key: BusinessType
    label: str
    description: str


class Suggestion(BaseModel):
    type: BusinessType | None
    reasons: list[str]


class EcommerceConfig(BaseModel):
    business_type: BusinessType
    confirmed: bool
    confirmed_at: datetime | None
    suggestion: Suggestion
    tabs: list[TabInfo]
    product_fields: list[FieldInfo]
    order_fields: list[FieldInfo]
    types: list[TypeChoice]


class EcommerceConfigSave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    business_type: BusinessType


class _ProductFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Text255 | None = None
    description: Annotated[str, StringConstraints(max_length=20000)] | None = None
    sku: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] | None = None
    category_id: str | None = None
    price: Money | None = None
    compare_at_price: Money | None = None
    cost: Money | None = None
    stock: Annotated[int, Field(ge=0, le=10_000_000)] | None = None
    weight_grams: Annotated[int, Field(ge=0, le=10_000_000)] | None = None
    media_ids: Annotated[list[str], Field(max_length=20)] | None = None
    delivery_note: Annotated[str, StringConstraints(max_length=2000)] | None = None


class ProductCreate(_ProductFields):
    status: Literal["draft", "active", "out_of_stock"] | None = None


class ProductPatch(_ProductFields):
    status: Literal["draft", "active", "out_of_stock", "archived"] | None = None


class ProductImage(BaseModel):
    media_id: str | None = None
    url: str | None = None
    alt: str | None = None


class ProductDetail(BaseModel):
    id: str
    sku: str
    title: str
    description: str | None
    category_id: str | None
    category: str | None
    price: float | None
    price_on_request: bool
    compare_at_price: float | None
    cost: float | None
    currency: str
    stock: int | None
    weight_grams: int | None
    images: list[ProductImage]
    status: str
    delivery_note: str | None
    updated_at: datetime


class CategoryRead(BaseModel):
    id: str
    name: str
    slug: str
    description: str | None
    parent_id: str | None
    product_count: int


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    description: Annotated[str, StringConstraints(max_length=1000)] | None = None
    parent_id: str | None = None


class CategoryPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)] | None = None
    description: Annotated[str, StringConstraints(max_length=1000)] | None = None


PaymentStatus = Literal["unpaid", "paid", "cod", "refunded"]


class PaymentRow(BaseModel):
    order_id: str
    order_number: str
    customer_name: str | None
    placed_at: datetime
    status: str
    payment_method: str | None
    payment_status: str | None
    reference: str | None
    total: float
    currency: str


class PaymentList(BaseModel):
    total: int
    sums: dict[str, float]
    items: list[PaymentRow]


class PaymentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payment_status: PaymentStatus
    method: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None = None
    reference: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
