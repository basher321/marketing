"""/users endpoints (SPEC-BE-037).

Any authenticated user may read the tenant's users; creating, updating and deleting users is
owner-only. Another tenant's user is a 404.
"""
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead], status_code=200)
def list_users(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[dict[str, Any]]:
    return user_service.list_users(db, str(current_user.tenant_id))


@router.post("", response_model=UserRead, status_code=201)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("owner")),
) -> dict[str, Any]:
    return user_service.create_user(
        db, str(current_user.tenant_id), str(current_user.id), payload
    )


@router.get("/{user_id}", response_model=UserRead, status_code=200)
def get_user(
    user_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return user_service.get_user(db, str(current_user.tenant_id), user_id)


@router.patch("/{user_id}", response_model=UserRead, status_code=200)
def update_user(
    user_id: str,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("owner")),
) -> dict[str, Any]:
    return user_service.update_user(
        db, str(current_user.tenant_id), str(current_user.id), user_id, payload
    )


@router.delete("/{user_id}", response_model=None, status_code=204)
def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("owner")),
) -> None:
    user_service.delete_user(db, str(current_user.tenant_id), str(current_user.id), user_id)
