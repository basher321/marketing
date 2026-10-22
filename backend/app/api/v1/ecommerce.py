"""/ecommerce/config: the company's business type and what E-Commerce shows (SPEC-BE-111)."""
from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.ecommerce import EcommerceConfig, EcommerceConfigSave
from app.services import ecommerce_service

router = APIRouter(prefix="/ecommerce", tags=["ecommerce"])


@router.get("/config", response_model=EcommerceConfig, status_code=status.HTTP_200_OK)
def get_config(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return ecommerce_service.get_config(db, current_user.tenant_id)


@router.put("/config", response_model=EcommerceConfig, status_code=status.HTTP_200_OK)
def save_config(
    payload: EcommerceConfigSave, db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return ecommerce_service.save_config(db, current_user.tenant_id, current_user, payload.business_type)
