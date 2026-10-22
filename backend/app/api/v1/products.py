"""/products endpoints."""
from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.ecommerce import ProductCreate, ProductDetail, ProductPatch
from app.schemas.product import ProductListItem
from app.services import ecommerce_service, product_service

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductListItem], status_code=status.HTTP_200_OK)
def list_products(
    category_id: str | None = Query(default=None, max_length=36),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    return product_service.list_products(db, current_user.tenant_id, category_id)



# ---- SPEC-BE-111: products by hand, validated by the business type ----
@router.post("", response_model=ProductDetail, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate, db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return ecommerce_service.create_product(db, current_user.tenant_id, current_user, payload)


@router.get("/{product_id}", response_model=ProductDetail, status_code=status.HTTP_200_OK)
def get_product(
    product_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return ecommerce_service.get_product(db, current_user.tenant_id, product_id)


@router.patch("/{product_id}", response_model=ProductDetail, status_code=status.HTTP_200_OK)
def update_product(
    product_id: str, payload: ProductPatch, db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return ecommerce_service.update_product(db, current_user.tenant_id, current_user, product_id, payload)


@router.delete("/{product_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
def archive_product(
    product_id: str, db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> Response:
    """Archives (products are never hard-deleted: orders point at them)."""
    ecommerce_service.archive_product(db, current_user.tenant_id, current_user, product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
