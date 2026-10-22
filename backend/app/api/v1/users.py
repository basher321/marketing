"""/users endpoints (SPEC-BE-037).

Any authenticated user may read the tenant's users; creating, updating and deleting users is
owner-only. Another tenant's user is a 404.
"""
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.user import MyProfile, MyProfileUpdate, UserCreate, UserRead, UserUpdate
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


# ---- SPEC-BE-113: my profile (declared before /{user_id}) ----
@router.get("/me", response_model=MyProfile, status_code=200)
def get_my_profile(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return user_service.my_profile(db, current_user)


@router.patch("/me", response_model=MyProfile, status_code=200)
def update_my_profile(
    payload: MyProfileUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return user_service.update_my_profile(db, current_user, payload.model_dump(exclude_unset=True))


@router.put("/me/avatar", response_model=MyProfile, status_code=200)
async def upload_my_avatar(
    file: UploadFile = File(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    from app.services.tenant_service import MAX_IMAGE_BYTES

    return user_service.set_my_avatar(db, current_user, await file.read(MAX_IMAGE_BYTES + 1))


@router.delete("/me/avatar", response_model=MyProfile, status_code=200)
def delete_my_avatar(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return user_service.set_my_avatar(db, current_user, None)


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
