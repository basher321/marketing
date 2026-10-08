"""/orders endpoints."""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.order import OrderList, OrderMetrics, OrderRevenue24h
from app.services import order_service

router = APIRouter(prefix="/orders", tags=["orders"])

# The live order_status enum; any other ?status= value is a 422.
OrderStatus = Literal[
    "pending", "confirmed", "processing", "shipped", "delivered", "cancelled", "refunded"
]


@router.get("", response_model=OrderList, status_code=status.HTTP_200_OK)
def list_orders(
    order_status: Annotated[OrderStatus | None, Query(alias="status")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OrderList:
    # Blank/whitespace-only search means "no search".
    search = q.strip() if q and q.strip() else None
    return OrderList.model_validate(
        order_service.list_orders(db, current_user.tenant_id, order_status, search, limit, offset)
    )


@router.get("/metrics", response_model=OrderMetrics, status_code=status.HTTP_200_OK)
def get_order_metrics(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> OrderMetrics:
    return OrderMetrics.model_validate(order_service.get_order_metrics(db, current_user.tenant_id))


@router.get("/revenue-24h", response_model=OrderRevenue24h, status_code=status.HTTP_200_OK)
def get_revenue_24h(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> OrderRevenue24h:
    return OrderRevenue24h.model_validate(
        order_service.get_revenue_24h(db, current_user.tenant_id)
    )
