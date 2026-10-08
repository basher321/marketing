"""/inventory endpoints."""
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.inventory import InventoryAdjust, InventoryRead
from app.services import inventory_service

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("", response_model=list[InventoryRead], status_code=status.HTTP_200_OK)
def list_inventory(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[dict[str, Any]]:
    return inventory_service.list_inventory(db, current_user.tenant_id)


@router.get("/low-stock", response_model=list[InventoryRead], status_code=status.HTTP_200_OK)
def list_low_stock(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[dict[str, Any]]:
    return inventory_service.low_stock_items(db, current_user.tenant_id)


@router.post(
    "/{inventory_id}/adjust", response_model=InventoryRead, status_code=status.HTTP_200_OK
)
def adjust_inventory(
    inventory_id: UUID,
    payload: InventoryAdjust,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return inventory_service.adjust_on_hand(
        db,
        current_user.tenant_id,
        current_user.id,
        str(inventory_id),
        payload.on_hand,
        payload.reason,
    )
