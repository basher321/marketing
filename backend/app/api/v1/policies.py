"""/policies endpoints (SPEC-BE-048): any role reads; writes are manager+
because enabled policies ground the AI's customer replies."""
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.policy import PolicyCreate, PolicyList, PolicyRead, PolicyUpdate
from app.services import policy_service

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get("", response_model=PolicyList, status_code=status.HTTP_200_OK)
def list_policies(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return policy_service.list_policies(db, str(current_user.tenant_id))


@router.post("", response_model=PolicyRead, status_code=status.HTTP_201_CREATED)
def create_policy(
    payload: PolicyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return policy_service.create_policy(db, str(current_user.tenant_id), str(current_user.id), payload)


@router.patch("/{policy_id}", response_model=PolicyRead, status_code=status.HTTP_200_OK)
def update_policy(
    policy_id: UUID,
    payload: PolicyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return policy_service.update_policy(
        db, str(current_user.tenant_id), str(current_user.id), str(policy_id), payload
    )


@router.delete("/{policy_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
def delete_policy(
    policy_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> None:
    policy_service.delete_policy(db, str(current_user.tenant_id), str(current_user.id), str(policy_id))
