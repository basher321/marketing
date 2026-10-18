"""Command Chat message and plan schemas (SPEC-BE-023/033/059)."""
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints

# Leading/trailing whitespace is stripped first, so an empty or
# whitespace-only body fails min_length=1 with a 422 before any write.
MessageBody = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]


class VoiceInfo(BaseModel):
    """A voice command (SPEC-BE-095): the language the transcript was heard in."""

    language: str | None = Field(default=None, max_length=12)


class ChatMessageCreate(BaseModel):
    body: MessageBody
    voice: VoiceInfo | None = None
    # Files uploaded with POST /orchestrator/files (SPEC-BE-096 FR5).
    file_ids: list[str] = Field(default_factory=list, max_length=20)
    # The chat to continue (SPEC-BE-099). Without it: a new chat when `new_chat` (or a
    # `project_id`) is given, else the user's latest chat (older clients keep one thread).
    chat_id: str | None = Field(default=None, max_length=36)
    new_chat: bool = False
    project_id: str | None = Field(default=None, max_length=36)


class MessageFile(BaseModel):
    """A file attached to a user message, as the bubble shows it."""

    id: str
    name: str
    kind: str
    bytes: int
    summary: str = ""
    media_ids: list[str] = []


class ResultMedia(BaseModel):
    """A generated image/video (SPEC-BE-092). No URL: signed URLs expire, so
    the chat fetches a fresh one with GET /media/{id}."""

    id: str
    kind: Literal["image", "video"]


class FixHint(BaseModel):
    """How to fix a failed step (SPEC-BE-100 FR3); href is an app page, or null."""

    text: str
    href: str | None = None
    link_label: str | None = None


class ResultItem(BaseModel):
    index: int
    label: str
    status: str
    summary: str | None = None
    link: str | None = None
    fix: FixHint | None = None
    data: list[dict[str, Any]] | None = None
    media: ResultMedia | None = None


class ChatMessage(BaseModel):
    """One Command Chat message. kind: message | plan | clarification | summary
    (SPEC-BE-059); plan_id links plan and summary replies to their plan."""

    id: str
    sender: Literal["user", "ai"]
    body: str
    sent_at: datetime
    # The chat it belongs to (SPEC-BE-099).
    chat_id: str | None = None
    # progress = a job list's progress / failure line (SPEC-BE-097).
    kind: Literal["message", "plan", "clarification", "summary", "progress"] = "message"
    plan_id: str | None = None
    waiting_for: list[str] = []
    results: list[ResultItem] = []
    # SPEC-BE-095: a user message that came from a voice command.
    voice: bool = False
    voice_language: str | None = None
    # SPEC-BE-095 Amendment C: a reply language the user asked for ("reply in English").
    reply_language: str | None = None
    # SPEC-BE-096: files attached to a user message.
    files: list[MessageFile] = []


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
    # draft / needs_input: a job list before it is submitted (SPEC-BE-097).
    status: Literal["draft", "needs_input", "pending_approval", "approved", "running", "succeeded", "failed", "skipped", "rejected"]
    result: dict[str, Any] | None
    error: str | None
    fix: FixHint | None = None
    started_at: str | None
    finished_at: str | None
    # Job lists (SPEC-BE-097)
    item_key: str | None = None
    run_at: str | None = None
    missing: list[dict[str, str]] = []


class PlanItem(BaseModel):
    """One item of a job list (a spreadsheet row, a product found in a document, a photo)."""

    key: str
    label: str
    fields: dict[str, Any]
    media_ids: list[str] = []
    source: str = ""


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
    # Job lists (SPEC-BE-097)
    job_list: bool = False
    mode: str | None = None
    start_at: datetime | None = None
    concurrency: int | None = None
    submitted_at: datetime | None = None
    paused_at: datetime | None = None
    items: list[PlanItem] = []
    schedule: dict[str, Any] = {}
    removed: list[int] = []


class SendMessageResult(ChatMessage):
    """POST /orchestrator/messages: the stored user message, the AI reply and
    the stored plan (null when no plan was stored)."""

    reply: ChatMessage
    plan: PlanRead | None


class PlanActionEdit(BaseModel):
    params: dict[str, Any]
    # A job list's job time: ISO with offset, or company-local "YYYY-MM-DD HH:MM" (SPEC-BE-097).
    run_at: str | None = Field(default=None, max_length=40)


class JobCreate(BaseModel):
    """POST /orchestrator/plans/{id}/actions: a new job in a draft job list."""

    type: str = Field(min_length=1, max_length=60)
    params: dict[str, Any] = Field(default_factory=dict)
    description: str | None = Field(default=None, max_length=300)
    item_key: str | None = Field(default=None, max_length=20)
    depends_on: list[int] = Field(default_factory=list, max_length=20)
    run_at: str | None = Field(default=None, max_length=40)


class ItemEdit(BaseModel):
    fields: dict[str, Any]


class JobSchedule(BaseModel):
    """PATCH /orchestrator/plans/{id}/schedule (SPEC-BE-097 FR4)."""

    mode: Literal["sequential", "parallel", "scheduled"]
    start_at: str | None = Field(default=None, max_length=40)
    concurrency: int | None = Field(default=None, ge=1, le=5)
    item_daily_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    item_every_minutes: int | None = Field(default=None, ge=1, le=10080)
    per_job: dict[str, str] = Field(default_factory=dict)


class TranscriptRead(BaseModel):
    """POST /orchestrator/voice/transcribe (SPEC-BE-095)."""

    text: str
    language: str | None
    provider: str


class SpeechRequest(BaseModel):
    language: str | None = Field(default=None, max_length=12)


class SpeechRead(BaseModel):
    """POST /orchestrator/messages/{id}/speech: base64 audio plus the spoken text."""

    audio: str
    mime: str
    text: str
    language: str | None
    provider: str
    note: str | None = None


class FileRead(BaseModel):
    """POST /orchestrator/files (SPEC-BE-096): a stored, extracted file."""

    id: str
    name: str
    kind: Literal["pdf", "docx", "xlsx", "csv", "text", "json", "image", "zip"]
    mime: str
    bytes: int
    status: str
    summary: str
    items_count: int
    media_ids: list[str]
    warnings: list[str]
    created_at: datetime | None = None


class FileDetail(FileRead):
    """GET /orchestrator/files/{id}: plus a short preview."""

    preview_text: str = ""
    preview_records: list[dict[str, Any]] = []


# ---- Chat history and projects (SPEC-BE-099) ----
class ChatProjectRef(BaseModel):
    id: str
    name: str
    emoji: str


class ChatRead(BaseModel):
    id: str
    title: str
    title_source: Literal["auto", "ai", "manual"]
    project: ChatProjectRef | None = None
    pinned: bool
    archived: bool
    message_count: int
    preview: str
    last_message_at: datetime | None
    created_at: datetime | None


class ChatList(BaseModel):
    items: list[ChatRead]
    has_more: bool


class ChatCreate(BaseModel):
    project_id: str | None = Field(default=None, max_length=36)


class ChatUpdate(BaseModel):
    """Only the fields sent change; `project_id: null` takes the chat out of its project."""

    title: str | None = Field(default=None, max_length=200)
    pinned: bool | None = None
    project_id: str | None = Field(default=None, max_length=36)
    archived: bool | None = None


class ProjectRead(BaseModel):
    id: str
    name: str
    description: str
    instructions: str
    emoji: str
    archived: bool
    chat_count: int
    last_activity_at: datetime | None
    created_at: datetime | None
    files: list[FileRead] = []


class ProjectCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    description: str | None = Field(default=None, max_length=500)
    instructions: str | None = Field(default=None, max_length=4000)
    emoji: str | None = Field(default=None, max_length=8)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    instructions: str | None = Field(default=None, max_length=4000)
    emoji: str | None = Field(default=None, max_length=8)
    archived: bool | None = None


class ProjectFileAdd(BaseModel):
    file_id: str = Field(max_length=36)
