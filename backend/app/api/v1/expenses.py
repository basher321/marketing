"""/expenses: other business costs for profit & loss (SPEC-BE-110 FR1)."""
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.expense import ExpenseCategory, ExpenseCreate, ExpenseList, ExpensePatch, ExpenseRead
from app.services import expense_service

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.get("", response_model=ExpenseList, status_code=status.HTTP_200_OK)
def list_expenses(
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
    category: ExpenseCategory | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return expense_service.list_expenses(db, current_user.tenant_id, start, end, category, limit, offset)


@router.post("", response_model=ExpenseRead, status_code=status.HTTP_201_CREATED)
def create_expense(
    payload: ExpenseCreate, db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return expense_service.create_expense(db, current_user.tenant_id, current_user, payload)


@router.patch("/{expense_id}", response_model=ExpenseRead, status_code=status.HTTP_200_OK)
def update_expense(
    expense_id: str, payload: ExpensePatch, db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return expense_service.update_expense(db, current_user.tenant_id, current_user, expense_id, payload)


@router.delete("/{expense_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(
    expense_id: str, db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> Response:
    expense_service.delete_expense(db, current_user.tenant_id, current_user, expense_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
