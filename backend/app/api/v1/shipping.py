"""/shipping endpoints: zones and their rates (SPEC-BE-043).

The prefix was /shipping-policies; nothing called it (the old routes failed
against the live tables).
"""
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.shipping import (
    DetectResult,
    ShippingRateCreate,
    ShippingRateRead,
    ShippingRateUpdate,
    ShippingSetup,
    ShippingStatus,
    ShippingZoneCreate,
    ShippingZoneList,
    ShippingZoneRead,
    SyncResult,
    ValidationResult,
)
from app.services import shipping_service

router = APIRouter(prefix="/shipping", tags=["shipping"])


@router.get("/zones", response_model=ShippingZoneList, status_code=status.HTTP_200_OK)
def list_zones(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return shipping_service.list_zones(db, current_user.tenant_id)


@router.post("/zones", response_model=ShippingZoneRead, status_code=status.HTTP_201_CREATED)
def create_zone(
    payload: ShippingZoneCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return shipping_service.create_zone(db, current_user.tenant_id, current_user.id, payload)


@router.post(
    "/zones/{zone_id}/rates", response_model=ShippingRateRead, status_code=status.HTTP_201_CREATED
)
def create_rate(
    zone_id: UUID,
    payload: ShippingRateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return shipping_service.create_rate(
        db, current_user.tenant_id, current_user.id, str(zone_id), payload
    )


@router.patch("/rates/{rate_id}", response_model=ShippingRateRead, status_code=status.HTTP_200_OK)
def update_rate(
    rate_id: UUID,
    payload: ShippingRateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    # SPEC-BE-058: any subset of fields (the old {active} toggle body still works).
    # A store-sourced rate is changed in the store first.
    return shipping_service.update_rate(
        db, current_user.tenant_id, current_user.id, str(rate_id), payload
    )


@router.get("/status", response_model=ShippingStatus, status_code=status.HTTP_200_OK)
def get_status(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return shipping_service.get_status(db, str(current_user.tenant_id))


@router.post("/detect", response_model=DetectResult, status_code=status.HTTP_200_OK)
def detect(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return shipping_service.detect(db, str(current_user.tenant_id), str(current_user.id))


@router.post("/sync", response_model=SyncResult, status_code=status.HTTP_200_OK)
def sync(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return shipping_service.sync(db, str(current_user.tenant_id), str(current_user.id))


@router.post("/validate", response_model=ValidationResult, status_code=status.HTTP_200_OK)
def validate(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return shipping_service.validate(db, str(current_user.tenant_id))


@router.post("/setup", response_model=SyncResult, status_code=status.HTTP_201_CREATED)
def setup(
    payload: ShippingSetup,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    result = shipping_service.setup(db, str(current_user.tenant_id), str(current_user.id), payload)
    return {**result, "last_sync_at": result.get("last_sync_at") or ""}


@router.post("/setup/validate", response_model=ValidationResult, status_code=status.HTTP_200_OK)
def validate_setup(
    payload: ShippingSetup,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    # Guided setup Review step (SPEC-BE-058): the draft is validated, nothing is written.
    return shipping_service.validate_setup(db, str(current_user.tenant_id), payload)
