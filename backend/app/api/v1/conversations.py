"""/conversations endpoints."""
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.conversation import (
    CsMetrics,
    DraftEdit,
    DraftResponse,
    DraftSendResult,
    HandoffResult,
    InboxList,
    MessageCreate,
    MessageRead,
)
from app.services import conversation_service

router = APIRouter(prefix="/conversations", tags=["conversations"])


# Customer Service inbox: the Open Conversations table (SPEC-BE-007).
@router.get("", response_model=InboxList, status_code=200)
def list_conversations(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return conversation_service.list_inbox(db, str(current_user.tenant_id))


@router.post("/{conversation_id}/messages", response_model=MessageRead, status_code=201)
def add_message(
    conversation_id: str,
    payload: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agent")),  # SPEC-BE-071 F5: not viewers
):
    return conversation_service.add_message(
        db, current_user.tenant_id, conversation_id, payload.sender_type, payload.body
    )


# Dashboard Customer Service engine card (SPEC-BE-021).
@router.get("/cs-metrics", response_model=CsMetrics, status_code=200)
def get_cs_metrics(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> CsMetrics:
    return CsMetrics.model_validate(
        conversation_service.get_cs_metrics(db, current_user.tenant_id)
    )


# AI Reply Draft panel actions (SPEC-BE-026) - agent+ only. No draft
# generation, LLM, or moderation endpoint.
@router.get("/{conversation_id}/draft", response_model=DraftResponse, status_code=200)
def get_draft(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agent")),
) -> DraftResponse:
    return DraftResponse.model_validate(
        conversation_service.get_pending_draft(db, current_user.tenant_id, str(conversation_id))
    )


@router.patch("/{conversation_id}/draft", response_model=DraftResponse, status_code=200)
def edit_draft(
    conversation_id: uuid.UUID,
    payload: DraftEdit,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agent")),
) -> DraftResponse:
    return DraftResponse.model_validate(
        conversation_service.edit_draft(
            db, current_user.tenant_id, str(conversation_id), payload.body
        )
    )


@router.post("/{conversation_id}/draft/send", response_model=DraftSendResult, status_code=200)
def send_draft(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agent")),
) -> DraftSendResult:
    return DraftSendResult.model_validate(
        conversation_service.send_draft(
            db, current_user.tenant_id, str(conversation_id), current_user.id
        )
    )


@router.post("/{conversation_id}/handoff", response_model=HandoffResult, status_code=200)
def handoff(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agent")),
) -> HandoffResult:
    return HandoffResult.model_validate(
        conversation_service.handoff(
            db, current_user.tenant_id, str(conversation_id), current_user.id
        )
    )


# AI reply-draft generation (SPEC-BE-028) - agent+ only. Generates via
# SPEC-BE-027 and replaces any pending draft (see conversation_service).
@router.post("/{conversation_id}/draft/generate", response_model=DraftResponse, status_code=201)
def generate_draft(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agent")),
) -> DraftResponse:
    return DraftResponse.model_validate(
        conversation_service.generate_draft(
            db, current_user.tenant_id, str(conversation_id), current_user.id
        )
    )
