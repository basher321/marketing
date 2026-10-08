"""/products endpoints."""
from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.product import ProductListItem
from app.services import product_service

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductListItem], status_code=status.HTTP_200_OK)
def list_products(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[dict[str, Any]]:
    return product_service.list_products(db, current_user.tenant_id)
