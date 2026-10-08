"""SocialAPI.ai: key, accounts, posts, analytics and inbox (SPEC-BE-083)."""
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

OAuthPlatform = Literal["instagram", "facebook", "threads", "tiktok", "linkedin", "youtube", "pinterest", "google", "twitter"]


# --- Key ----------------------------------------------------------------------
class KeyUpdate(BaseModel):
    api_key: str = Field(min_length=8, max_length=300)


class KeyStatus(BaseModel):
    # not_configured: no key saved; error: the last call with it failed (last_error).
    status: Literal["not_configured", "connected", "error"]
    key_masked: str | None
    last_ok_at: datetime | None
    last_error: str | None
    account_count: int | None
    docs_url: str


# --- Accounts -----------------------------------------------------------------
class Account(BaseModel):
    id: str
    platform: str
    name: str | None
    username: str | None
    # SocialAPI's own status: active | reconnect_required
    status: str
    avatar_url: str | None
    # Facebook: page_name is set only once one Page is active on the login;
    # login_id lists / assigns that login's Pages.
    page_name: str | None
    login_id: str | None = None
    reconnect_reason: str | None


class PlatformOption(BaseModel):
    platform: str
    label: str


class AccountList(BaseModel):
    configured: bool
    items: list[Account]
    connectable: list[PlatformOption]


class ConnectRequest(BaseModel):
    platform: OAuthPlatform


class ConnectResult(BaseModel):
    # OAuth: the browser goes to auth_url; direct auth: the account is connected at once.
    auth_url: str | None
    account: Account | None


class CallbackRequest(BaseModel):
    """The query string SocialAPI appends to our redirect_uri."""
    status: Literal["success", "error", "selection_required"]
    state: str = Field(min_length=1, max_length=4096)
    platform: str | None = Field(default=None, max_length=40)
    account_id: str | None = Field(default=None, max_length=200)
    connection_id: str | None = Field(default=None, max_length=200)
    error: str | None = Field(default=None, max_length=200)
    error_description: str | None = Field(default=None, max_length=1000)


class Choice(BaseModel):
    id: str
    name: str
    detail: str | None
    picture_url: str | None
    assignable: bool
    assigned_account_id: str | None


class CallbackResult(BaseModel):
    status: Literal["connected", "selection_required"]
    platform: str
    account_id: str | None
    connection_id: str | None
    choices: list[Choice]


class SelectRequest(BaseModel):
    platform: Literal["facebook", "google"]
    connection_id: str = Field(min_length=1, max_length=200)
    choice_id: str = Field(min_length=1, max_length=300)
    state: str = Field(min_length=1, max_length=4096)


class SelectResult(BaseModel):
    account_id: str | None


class ChoiceList(BaseModel):
    items: list[Choice]


class FacebookPageRequest(BaseModel):
    page_id: str = Field(min_length=1, max_length=200)


class Board(BaseModel):
    id: str
    board_id: str
    name: str
    privacy: str | None


class BoardList(BaseModel):
    items: list[Board]


# --- Posts --------------------------------------------------------------------
class TargetIn(BaseModel):
    account_id: str = Field(min_length=1, max_length=200)
    board_id: str | None = Field(default=None, max_length=200)  # Pinterest: required by SocialAPI


class PostCreate(BaseModel):
    text: str = Field(min_length=1, max_length=63206)
    title: str | None = Field(default=None, max_length=300)  # LinkedIn articles, YouTube, Google
    targets: list[TargetIn] = Field(min_length=1, max_length=50)
    # Ids from our own media library (/api/v1/media); uploaded to SocialAPI on send.
    media_ids: list[str] = Field(default_factory=list, max_length=20)
    first_comment: str | None = Field(default=None, max_length=2200)
    mode: Literal["now", "schedule", "draft"] = "now"
    scheduled_at: datetime | None = None

    @field_validator("scheduled_at")
    @classmethod
    def _aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("needs a timezone (e.g. 2026-10-08T09:00:00+06:00)")
        return value.astimezone(timezone.utc) if value else None

    @model_validator(mode="after")
    def _schedule(self) -> "PostCreate":
        if self.mode == "schedule":
            if self.scheduled_at is None:
                raise ValueError("scheduled_at is required to schedule a post")
            if self.scheduled_at <= datetime.now(timezone.utc):
                raise ValueError("scheduled_at must be in the future")
        if len({t.account_id for t in self.targets}) != len(self.targets):
            raise ValueError("each account may appear once")
        return self


class TargetMetrics(BaseModel):
    likes: int | None
    comments: int | None
    shares: int | None
    saves: int | None


class Target(BaseModel):
    account_id: str
    platform: str | None
    status: str | None
    permalink: str | None
    platform_post_id: str | None
    published_at: datetime | None
    scheduled_at: datetime | None
    error: str | None
    metrics: TargetMetrics | None
    metrics_synced_at: datetime | None


class Post(BaseModel):
    id: str
    # draft | scheduled | publishing | published | partial | failed | cancelled
    status: str
    text: str | None
    title: str | None
    media_count: int
    created_at: datetime | None
    scheduled_at: datetime | None
    published_at: datetime | None
    targets: list[Target]


class PostList(BaseModel):
    items: list[Post]
    next_cursor: str | None


class DeleteOutcome(BaseModel):
    account_id: str | None
    outcome: str | None  # deleted | not_supported | failed
    message: str | None


class DeleteResult(BaseModel):
    ok: bool
    results: list[DeleteOutcome]


class Constraint(BaseModel):
    platform: str
    text_max_length: int | None
    carousel_max_items: int | None
    max_video_duration_sec: int | None
    scheduling_supported: bool | None


class ConstraintList(BaseModel):
    items: list[Constraint]


class AnalyticsPoint(BaseModel):
    day: str
    value: float | None


class AnalyticsSeries(BaseModel):
    metric: str
    kind: str | None
    points: list[AnalyticsPoint]


class AccountAnalytics(BaseModel):
    account_id: str
    start: str
    end: str
    series: list[AnalyticsSeries]


# --- Inbox --------------------------------------------------------------------
class Conversation(BaseModel):
    id: str
    account_id: str | None
    platform: str | None
    participant_name: str | None
    participant_picture: str | None
    last_message: str | None
    last_message_at: datetime | None
    unread_count: int
    status: str | None


class ConversationList(BaseModel):
    items: list[Conversation]
    next_cursor: str | None
    sync_state: str | None


class InboxMessage(BaseModel):
    id: str
    text: str | None
    direction: str | None  # inbound | outbound
    sender_name: str | None
    status: str | None
    created_at: datetime | None
    attachment_type: str | None
    attachment_url: str | None


class MessageList(BaseModel):
    items: list[InboxMessage]
    next_cursor: str | None


class SendMessage(BaseModel):
    account_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=2000)


class CommentedPost(BaseModel):
    id: str
    platform_id: str
    account_id: str | None
    platform: str | None
    content: str | None
    permalink: str | None
    thumbnail: str | None
    comment_count: int
    published_at: datetime | None


class CommentedPostList(BaseModel):
    items: list[CommentedPost]
    next_cursor: str | None


class Comment(BaseModel):
    id: str
    text: str | None
    author_name: str | None
    author_username: str | None
    author_picture: str | None
    created_at: datetime | None
    like_count: int
    reply_count: int
    parent_id: str | None
    is_hidden: bool
    is_owner: bool
    can_reply: bool
    can_delete: bool
    can_hide: bool


class CommentList(BaseModel):
    items: list[Comment]
    next_cursor: str | None


class CommentReply(BaseModel):
    account_id: str = Field(min_length=1, max_length=200)
    comment_id: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=2200)


class CommentAction(BaseModel):
    account_id: str = Field(min_length=1, max_length=200)
    action: Literal["hide", "unhide", "delete"]


class Review(BaseModel):
    id: str
    author_name: str | None
    author_avatar: str | None
    rating: int | None
    text: str | None
    created_at: datetime | None
    reply_text: str | None
    reply_state: str | None  # PENDING | APPROVED | REJECTED


class ReviewList(BaseModel):
    items: list[Review]
    next_cursor: str | None
    average_rating: float | None
    total_count: int | None


class ReviewReply(BaseModel):
    account_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=4000)


class ActionResult(BaseModel):
    ok: bool
    message: str | None


class DraftTurn(BaseModel):
    role: Literal["customer", "agent"]
    text: str = Field(min_length=1, max_length=4000)


class DraftRequest(BaseModel):
    """The thread as the inbox shows it (a DM thread, a comment and its
    replies, or a review), oldest first; the last customer turn is answered."""
    history: list[DraftTurn] = Field(min_length=1, max_length=40)


class DraftSource(BaseModel):
    kind: str
    title: str


class DraftResult(BaseModel):
    body: str
    confidence: float
    # None | no_grounding | moderation_rejected (as the Customer Service drafts)
    fallback: str | None
    sources: list[DraftSource]
