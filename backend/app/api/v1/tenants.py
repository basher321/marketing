"""/tenants endpoints: the caller's organization (SPEC-BE-037, SPEC-BE-051)."""
from typing import Any

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError
from app.db.session import get_db
from app.dependencies import get_current_tenant, get_current_user, require_permission
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.tenant import (
    Branding,
    BrandingTextUpdate,
    LocaleOptions,
    TenantRead,
    TenantResetRequest,
    TenantResetResult,
    TenantUpdate,
)
from app.services import tenant_service
from app.services.tenant_service import MAX_IMAGE_BYTES, BrandingSlot
from app.utils import locale_data

router = APIRouter(prefix="/tenants", tags=["tenants"])


# Worldwide country / currency / language / timezone lists for the company settings
# (SPEC-BE-072). Static data, so browsers may cache it for a day.
@router.get("/locale-options", response_model=LocaleOptions, status_code=status.HTTP_200_OK)
def get_locale_options(response: Response, current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    response.headers["Cache-Control"] = "private, max-age=86400"
    return locale_data.locale_options()


@router.get("/me", response_model=TenantRead, status_code=status.HTTP_200_OK)
def get_my_tenant(tenant: Tenant = Depends(get_current_tenant)) -> dict[str, Any]:
    return tenant_service.tenant_payload(tenant)


# Profile and branding: owner or manager (require_permission("manager")).
@router.patch("/me", response_model=TenantRead, status_code=status.HTTP_200_OK)
def update_my_tenant(
    payload: TenantUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return tenant_service.update_profile(db, str(current_user.tenant_id), str(current_user.id), payload)


@router.patch("/me/branding", response_model=Branding, status_code=status.HTTP_200_OK)
def update_branding_text(
    payload: BrandingTextUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return tenant_service.set_branding_text(db, str(current_user.tenant_id), str(current_user.id), payload)


@router.put("/me/branding/{slot}", response_model=Branding, status_code=status.HTTP_200_OK)
async def upload_branding_image(
    slot: BrandingSlot,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    # Read at most 1 MB + 1 byte so an oversized upload is rejected without
    # holding the whole file in memory.
    data = await file.read(MAX_IMAGE_BYTES + 1)
    return tenant_service.set_branding_image(
        db, str(current_user.tenant_id), str(current_user.id), slot, data
    )


@router.delete("/me/branding/{slot}", response_model=Branding, status_code=status.HTTP_200_OK)
def delete_branding_image(
    slot: BrandingSlot,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return tenant_service.clear_branding_image(db, str(current_user.tenant_id), str(current_user.id), slot)


# Reset company data: owner only, confirmed by the workspace slug and password.
@router.post("/me/reset", response_model=TenantResetResult, status_code=status.HTTP_200_OK)
def reset_company_data(
    payload: TenantResetRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if current_user.role != "owner":
        raise ForbiddenError("Only the owner can reset company data.")
    return tenant_service.reset_company_data(
        db, str(current_user.tenant_id), current_user, payload.confirm_slug, payload.password
    )
