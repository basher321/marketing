"""/brand endpoints (SPEC-BE-012).

Any authenticated user may read the brand settings; saving is manager+ because they shape
every AI-generated reply and post.
"""
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.brand import BrandSettingsRead, BrandSettingsUpdate
from app.services import brand_service

router = APIRouter(prefix="/brand", tags=["brand"])


@router.get("", response_model=BrandSettingsRead, status_code=200)
def get_brand_settings(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return brand_service.get_brand_settings(db, str(current_user.tenant_id))


@router.put("", response_model=BrandSettingsRead, status_code=200)
def save_brand_settings(
    payload: BrandSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return brand_service.save_brand_settings(
        db, str(current_user.tenant_id), str(current_user.id), payload
    )
