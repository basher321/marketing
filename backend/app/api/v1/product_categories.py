"""/product-categories over the live product_categories table (SPEC-BE-111 FR6)."""
from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.ecommerce import CategoryCreate, CategoryPatch, CategoryRead
from app.services import ecommerce_service

router = APIRouter(prefix="/product-categories", tags=["products"])


@router.get("", response_model=list[CategoryRead], status_code=status.HTTP_200_OK)
def list_categories(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    return ecommerce_service.list_categories(db, current_user.tenant_id)


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreate, db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return ecommerce_service.create_category(db, current_user.tenant_id, current_user, payload)


@router.patch("/{category_id}", response_model=CategoryRead, status_code=status.HTTP_200_OK)
def update_category(
    category_id: str, payload: CategoryPatch, db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return ecommerce_service.update_category(db, current_user.tenant_id, current_user, category_id, payload)
