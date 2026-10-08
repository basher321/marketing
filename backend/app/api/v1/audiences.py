"""/audiences endpoints (SPEC-BE-045)."""
from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.audience import AudienceCreate, AudienceList, AudienceRead
from app.services import audience_service

router = APIRouter(prefix="/audiences", tags=["audiences"])


@router.get("", response_model=AudienceList, status_code=status.HTTP_200_OK)
def list_audiences(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return audience_service.list_audiences(db, current_user.tenant_id)


@router.post("", response_model=AudienceRead, status_code=status.HTTP_201_CREATED)
def create_audience(
    payload: AudienceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return audience_service.create_audience(db, current_user.tenant_id, current_user.id, payload)
