"""/orchestrator endpoints (Command Chat messages and plans)."""
from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.orchestrator import (
    ChatMessage,
    ChatMessageCreate,
    PlanActionEdit,
    PlanRead,
    SendMessageResult,
)
from app.services import orchestrator_service

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


@router.get("/messages", response_model=list[ChatMessage], status_code=status.HTTP_200_OK)
def list_messages(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[dict[str, Any]]:
    return orchestrator_service.list_messages(db, str(current_user.tenant_id))


# Sending stores the user message, then plans it (SPEC-BE-059): a clarifying
# question, or a plan whose read/draft steps start right away in the background
# and whose change/spend steps wait for approval per the policy.
@router.post("/messages", response_model=SendMessageResult, status_code=status.HTTP_201_CREATED)
def send_message(
    payload: ChatMessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return orchestrator_service.send_message_and_plan(
        db, str(current_user.tenant_id), str(current_user.id), payload.body, current_user.role
    )


@router.get("/plans/{plan_id}", response_model=PlanRead, status_code=status.HTTP_200_OK)
def get_plan(
    plan_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return orchestrator_service.get_plan(db, str(current_user.tenant_id), plan_id)


@router.patch("/plans/{plan_id}/actions/{index}", response_model=PlanRead, status_code=status.HTTP_200_OK)
def edit_plan_action(
    plan_id: str,
    index: int,
    payload: PlanActionEdit,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return orchestrator_service.edit_action(
        db, str(current_user.tenant_id), str(current_user.id), current_user.role, plan_id, index, payload.params
    )


@router.post("/plans/{plan_id}/actions/{index}/retry", response_model=PlanRead, status_code=status.HTTP_200_OK)
def retry_plan_action(
    plan_id: str,
    index: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return orchestrator_service.retry_action(db, str(current_user.tenant_id), str(current_user.id), plan_id, index)


@router.post("/draft/discard", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def discard_draft(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> None:
    orchestrator_service.discard_draft(db, str(current_user.tenant_id), str(current_user.id))
