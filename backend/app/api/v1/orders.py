"""/orders endpoints."""
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.order import (
    OrderCreate,
    OrderDetail,
    OrderList,
    OrderMetrics,
    OrderPatch,
    OrderRevenue24h,
    OrderStatusChange,
    OrderStatusValue,
)
from app.schemas.ecommerce import PaymentList, PaymentStatus, PaymentUpdate
from app.schemas.sms import SmsSendResult
from app.services import ecommerce_service, order_service, sms_service

router = APIRouter(prefix="/orders", tags=["orders"])

# The live order_status enum (SPEC-BE-107 added awaiting_confirmation, returned);
# any other ?status= value is a 422.
OrderStatus = OrderStatusValue


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


# ---- SPEC-BE-111 FR7: the Payments tab (before /{order_id}) ----------------
@router.get("/payments", response_model=PaymentList, status_code=status.HTTP_200_OK)
def list_payments(
    payment_status: Annotated[PaymentStatus | None, Query(alias="status")] = None,
    range_key: Annotated[Literal["7d", "30d", "90d"] | None, Query(alias="range")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    days = {"7d": 7, "30d": 30, "90d": 90}.get(range_key or "")
    return ecommerce_service.list_payments(db, current_user.tenant_id, payment_status, days, limit, offset)


@router.post("/{order_id}/payment", response_model=OrderDetail, status_code=status.HTTP_200_OK)
def set_payment(
    order_id: str, payload: PaymentUpdate, db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agent")),
) -> dict[str, Any]:
    ecommerce_service.set_payment(db, current_user.tenant_id, current_user, order_id, payload.payment_status,
                                  payload.method, payload.reference)
    return order_service.get_order_detail(db, current_user.tenant_id, order_id, current_user.role)


# ---- SPEC-BE-107 / 108: lifecycle -------------------------------------------
@router.post("", response_model=OrderDetail, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreate,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=200)] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agent")),
) -> dict[str, Any]:
    tenant_id = current_user.tenant_id
    order_id, created = order_service.create_order(db, tenant_id, current_user, payload, idempotency_key)
    if created:
        # SPEC-BE-108 FR4: the confirmation SMS when the company has auto-confirm on.
        sms_service.auto_confirm(db, tenant_id, order_id, current_user)
    else:
        response.status_code = status.HTTP_200_OK
    return order_service.get_order_detail(db, tenant_id, order_id, current_user.role)


@router.get("/{order_id}", response_model=OrderDetail, status_code=status.HTTP_200_OK)
def get_order(
    order_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return order_service.get_order_detail(db, current_user.tenant_id, order_id, current_user.role)


@router.post("/{order_id}/status", response_model=OrderDetail, status_code=status.HTTP_200_OK)
def change_order_status(
    order_id: str,
    payload: OrderStatusChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agent")),
) -> dict[str, Any]:
    order_service.change_status(
        db, current_user.tenant_id, order_id, payload.to, actor=current_user, reason=payload.reason,
        tracking_number=payload.tracking_number, tracking_url=payload.tracking_url,
    )
    return order_service.get_order_detail(db, current_user.tenant_id, order_id, current_user.role)


@router.patch("/{order_id}", response_model=OrderDetail, status_code=status.HTTP_200_OK)
def update_order(
    order_id: str,
    payload: OrderPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agent")),
) -> dict[str, Any]:
    order_service.update_order(db, current_user.tenant_id, current_user, order_id, payload)
    return order_service.get_order_detail(db, current_user.tenant_id, order_id, current_user.role)


@router.post("/{order_id}/confirmation-sms", response_model=SmsSendResult, status_code=status.HTTP_200_OK)
def send_confirmation_sms(
    order_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_permission("agent"))
) -> dict[str, Any]:
    return sms_service.send_confirmation(db, current_user.tenant_id, order_id, current_user)
