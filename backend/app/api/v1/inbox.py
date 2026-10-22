"""/inbox: the unified inbox across SocialAPI, WhatsApp, SMS and stored channels (SPEC-BE-112)."""
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.inbox import (
    InboxChannelList,
    InboxConversation,
    InboxConversationList,
    InboxCustomerPanel,
    InboxLink,
    InboxPatch,
    InboxSend,
    InboxSent,
    InboxThread,
)
from app.services import inbox_service

router = APIRouter(prefix="/inbox", tags=["inbox"])
Key = Annotated[str, Query(max_length=400)]


@router.get("/channels", response_model=InboxChannelList, status_code=status.HTTP_200_OK)
def channels(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    return inbox_service.list_channels(db, user.tenant_id)


@router.get("/conversations", response_model=InboxConversationList, status_code=status.HTTP_200_OK)
def conversations(
    channel: Annotated[str | None, Query(max_length=300)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    conv_status: Annotated[Literal["open", "pending", "resolved", "archived"] | None, Query(alias="status")] = None,
    unread: bool = False,
    assignee: Literal["me"] | None = None,
    cursor: Annotated[str | None, Query(max_length=4000)] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    search = q.strip() if q and q.strip() else None
    return inbox_service.list_conversations(db, user.tenant_id, user, channel, search, conv_status, unread,
                                            assignee == "me", cursor)


@router.get("/conversations/{key}/messages", response_model=InboxThread, status_code=status.HTTP_200_OK)
def thread(
    key: str, cursor: Annotated[str | None, Query(max_length=4000)] = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return inbox_service.get_thread(db, user.tenant_id, user, key, cursor)


@router.post("/conversations/{key}/messages", response_model=InboxSent, status_code=status.HTTP_201_CREATED)
def send(key: str, payload: InboxSend, db: Session = Depends(get_db),
         user: User = Depends(require_permission("agent"))) -> dict[str, Any]:
    return inbox_service.send(db, user.tenant_id, user, key, payload)


@router.patch("/conversations/{key}", response_model=InboxConversation, status_code=status.HTTP_200_OK)
def update(key: str, payload: InboxPatch, db: Session = Depends(get_db),
           user: User = Depends(require_permission("agent"))) -> dict[str, Any]:
    return inbox_service.update(db, user.tenant_id, user, key, payload)


@router.post("/conversations/{key}/link", response_model=InboxCustomerPanel, status_code=status.HTTP_200_OK)
def link(key: str, payload: InboxLink, db: Session = Depends(get_db),
         user: User = Depends(require_permission("agent"))) -> dict[str, Any]:
    return inbox_service.link(db, user.tenant_id, user, key, payload.customer_id)
