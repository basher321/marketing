"""Unified inbox (SPEC-BE-112)."""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class InboxChannel(BaseModel):
    key: str
    platform: str
    source: Literal["socialapi", "whatsapp_cloud", "twilio", "local"]
    account_id: str | None
    name: str
    status: Literal["connected", "needs_attention"]
    problem: str | None = None
    can_send: bool
    can_send_media: bool


class InboxChannelList(BaseModel):
    items: list[InboxChannel]


class InboxCustomer(BaseModel):
    id: str | None = None
    name: str | None = None
    handle: str | None = None
    phone: str | None = None
    email: str | None = None
    avatar: str | None = None


class InboxLastMessage(BaseModel):
    preview: str | None
    at: datetime | None
    direction: str | None


class InboxConversation(BaseModel):
    key: str
    channel: str
    platform: str
    conversation_id: str
    customer: InboxCustomer
    last_message: InboxLastMessage
    unread: int
    status: str | None
    assignee_id: str | None
    assignee_name: str | None
    topic: str | None
    is_sample: bool


class InboxConversationList(BaseModel):
    items: list[InboxConversation]
    next_cursor: str | None
    channel_errors: list[dict[str, str]] = []


class InboxAttachment(BaseModel):
    kind: str | None = None
    url: str | None = None
    name: str | None = None
    media_id: str | None = None


class InboxMessage(BaseModel):
    id: str
    direction: str
    sender: str | None
    body: str | None
    attachments: list[InboxAttachment]
    sent_at: datetime | None
    delivery: str | None
    error: str | None
    is_ai_draft: bool


class InboxOrderBadge(BaseModel):
    id: str
    order_number: str
    status: str
    confirmation_state: str
    total: float
    currency: str


class InboxCustomerPanel(BaseModel):
    id: str
    name: str | None
    phone: str | None
    email: str | None
    order_count: int
    lifetime_value: float
    currency: str
    orders: list[InboxOrderBadge]


class InboxThread(BaseModel):
    conversation: InboxConversation
    customer: InboxCustomerPanel | None
    can_send: bool
    can_send_media: bool
    send_blocked_reason: str | None
    items: list[InboxMessage]
    next_cursor: str | None


class InboxSend(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] = ""
    media_ids: Annotated[list[str], Field(max_length=4)] = []


class InboxSent(BaseModel):
    message: InboxMessage


class InboxPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["open", "pending", "resolved", "archived"] | None = None
    assignee_id: str | None = None
    tags: Annotated[list[Annotated[str, StringConstraints(max_length=50)]], Field(max_length=20)] | None = None


class InboxLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: str


class WhatsAppConnectInfo(BaseModel):
    app_id: str
    config_id: str
    graph_version: str
    state: str


class WhatsAppCallback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    state: Annotated[str, StringConstraints(min_length=1, max_length=4000)]
    waba_id: Annotated[str, StringConstraints(pattern=r"^\d{3,30}$")]
    phone_number_id: Annotated[str, StringConstraints(pattern=r"^\d{3,30}$")]


class WhatsAppAccount(BaseModel):
    id: str
    phone_number: str | None
    name: str | None
    status: str
    last_error: str | None
    connected_at: datetime | None


class WhatsAppStatus(BaseModel):
    available: bool
    reason: str | None
    accounts: list[WhatsAppAccount]
