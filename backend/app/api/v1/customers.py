"""/customers endpoints (SPEC-BE-007)."""
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.customer import CustomerCreate, CustomerRead
from app.services import customer_service

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=list[CustomerRead], status_code=200)
def list_customers(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[dict[str, Any]]:
    return customer_service.list_customers(db, str(current_user.tenant_id))


@router.post("", response_model=CustomerRead, status_code=201)
def create_customer(
    payload: CustomerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agent")),  # SPEC-BE-071 F5: not viewers
) -> dict[str, Any]:
    return customer_service.create_customer(db, str(current_user.tenant_id), payload)
