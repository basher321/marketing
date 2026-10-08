"""/ads endpoints."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.campaign import AdCtr7d
from app.services import ad_service

router = APIRouter(prefix="/ads", tags=["ads"])


# Backs the Marketing page "CTR (7d)" card (SPEC-BE-011).
@router.get("/ctr-7d", response_model=AdCtr7d, status_code=status.HTTP_200_OK)
def get_ctr_7d(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> AdCtr7d:
    return AdCtr7d(ctr_7d_pct=ad_service.get_ctr_7d(db, current_user.tenant_id))
