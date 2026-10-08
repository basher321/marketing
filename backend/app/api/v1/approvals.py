"""/approvals endpoints."""
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.approval import (
    ApprovalDecisionResult,
    GroupDecisionResult,
    PendingApprovalCounts,
    PendingApprovalList,
    RejectRequest,
)
from app.services import approval_service

router = APIRouter(prefix="/approvals", tags=["approvals"])


# Dashboard E-Commerce / Marketing engine cards' "Pending approvals" (SPEC-BE-020).
@router.get("/pending-counts", response_model=PendingApprovalCounts, status_code=status.HTTP_200_OK)
def get_pending_counts(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> PendingApprovalCounts:
    return PendingApprovalCounts.model_validate(
        approval_service.get_pending_counts(db, str(current_user.tenant_id))
    )


# Decide approval-queue items (SPEC-BE-024) - manager+ only. Records the
# decision; never executes the underlying action.
@router.post(
    "/{approval_id}/approve", response_model=ApprovalDecisionResult, status_code=status.HTTP_200_OK
)
def approve_one(
    approval_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> ApprovalDecisionResult:
    return ApprovalDecisionResult.model_validate(
        approval_service.decide_one(
            db, str(current_user.tenant_id), str(approval_id), str(current_user.id), "approved"
        )
    )


@router.post(
    "/{approval_id}/reject", response_model=ApprovalDecisionResult, status_code=status.HTTP_200_OK
)
def reject_one(
    approval_id: uuid.UUID,
    payload: RejectRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> ApprovalDecisionResult:
    return ApprovalDecisionResult.model_validate(
        approval_service.decide_one(
            db,
            str(current_user.tenant_id),
            str(approval_id),
            str(current_user.id),
            "rejected",
            payload.reason if payload else None,
        )
    )


@router.post(
    "/groups/{subject_id}/approve",
    response_model=GroupDecisionResult,
    status_code=status.HTTP_200_OK,
)
def approve_group(
    subject_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> GroupDecisionResult:
    return GroupDecisionResult.model_validate(
        approval_service.decide_group(
            db, str(current_user.tenant_id), str(subject_id), str(current_user.id), "approved"
        )
    )


@router.post(
    "/groups/{subject_id}/reject",
    response_model=GroupDecisionResult,
    status_code=status.HTTP_200_OK,
)
def reject_group(
    subject_id: uuid.UUID,
    payload: RejectRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> GroupDecisionResult:
    return GroupDecisionResult.model_validate(
        approval_service.decide_group(
            db,
            str(current_user.tenant_id),
            str(subject_id),
            str(current_user.id),
            "rejected",
            payload.reason if payload else None,
        )
    )


# Command Chat "Pending Approvals (N)" panel (SPEC-BE-025) - read-only.
@router.get("/pending", response_model=PendingApprovalList, status_code=status.HTTP_200_OK)
def list_pending(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> PendingApprovalList:
    return PendingApprovalList.model_validate(
        approval_service.list_pending(db, str(current_user.tenant_id))
    )
