"""Command Chat message and plan schemas (SPEC-BE-023/033/059)."""
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, StringConstraints

# Leading/trailing whitespace is stripped first, so an empty or
# whitespace-only body fails min_length=1 with a 422 before any write.
MessageBody = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]


class ChatMessageCreate(BaseModel):
    body: MessageBody


class ResultMedia(BaseModel):
    """A generated image/video (SPEC-BE-092). No URL: signed URLs expire, so
    the chat fetches a fresh one with GET /media/{id}."""

    id: str
    kind: Literal["image", "video"]


class ResultItem(BaseModel):
    index: int
    label: str
    status: str
    summary: str | None = None
    link: str | None = None
    data: list[dict[str, Any]] | None = None
    media: ResultMedia | None = None


class ChatMessage(BaseModel):
    """One Command Chat message. kind: message | plan | clarification | summary
    (SPEC-BE-059); plan_id links plan and summary replies to their plan."""

    id: str
    sender: Literal["user", "ai"]
    body: str
    sent_at: datetime
    kind: Literal["message", "plan", "clarification", "summary"] = "message"
    plan_id: str | None = None
    waiting_for: list[str] = []
    results: list[ResultItem] = []


class PlanAction(BaseModel):
    """One step of a plan with its live status (SPEC-BE-059 §5)."""

    index: int
    type: str
    label: str
    module: Literal["ecommerce", "shipping", "marketing", "meta", "organic", "workflows", "general"]
    risk: Literal["read", "draft", "change", "spend"]
    # auto = runs without approval; approval = a manager+; owner = owner only.
    approval_mode: Literal["auto", "approval", "owner"]
    description: str
    params: dict[str, Any]
    depends_on: list[int]
    cost_estimate_cents: int | None
    approval_id: str | None
    status: Literal["pending_approval", "approved", "running", "succeeded", "failed", "skipped", "rejected"]
    result: dict[str, Any] | None
    error: str | None
    started_at: str | None
    finished_at: str | None


class PlanRead(BaseModel):
    id: str
    status: str
    title: str
    estimated_cost_cents: int | None
    created_at: datetime
    # A plan stored before SPEC-BE-059 has no per-step status; its steps are
    # only actionable in the Pending Approvals panel.
    legacy: bool = False
    actions: list[PlanAction]
    dropped_count: int = 0


class SendMessageResult(ChatMessage):
    """POST /orchestrator/messages: the stored user message, the AI reply and
    the stored plan (null when no plan was stored)."""

    reply: ChatMessage
    plan: PlanRead | None


class PlanActionEdit(BaseModel):
    params: dict[str, Any]
