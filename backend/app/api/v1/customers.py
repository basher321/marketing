"""/customers endpoints (SPEC-BE-007, SPEC-BE-109)."""
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.customer import CustomerCreate, CustomerPatch, CustomerRead, CustomerRecord
from app.services import customer_service

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=list[CustomerRead], status_code=200)
def list_customers(
    response: Response,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    search = q.strip() if q and q.strip() else None
    items, total = customer_service.list_customers(db, str(current_user.tenant_id), search, limit, offset)
    response.headers["X-Total-Count"] = str(total)
    return items


@router.post("", response_model=CustomerRead, status_code=201)
def create_customer(
    payload: CustomerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agent")),  # SPEC-BE-071 F5: not viewers
) -> dict[str, Any]:
    return customer_service.create_customer(db, str(current_user.tenant_id), payload)


@router.get("/{customer_id}", response_model=CustomerRecord, status_code=200)
def get_customer_record(
    customer_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return customer_service.customer_record(db, str(current_user.tenant_id), customer_id)


@router.patch("/{customer_id}", response_model=CustomerRecord, status_code=200)
def update_customer(
    customer_id: str,
    payload: CustomerPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agent")),
) -> dict[str, Any]:
    return customer_service.update_customer(db, str(current_user.tenant_id), current_user, customer_id, payload)
