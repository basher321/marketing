"""/platform: PilotSonic's Super admin (SPEC-BE-101). The software's AI keys,
SocialAPI master key, Zernio key and sign-in apps, used by every company.

Only a user in platform_admins reaches these routes (anyone else gets 404);
GET /platform/me tells the UI whether to show the Super admin screen."""
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.db.session import get_db
from app.dependencies import get_current_user, require_super_admin
from app.models.user import User
from app.schemas.ai_model import AIModelList, AIModelOrder, AIModelTestResult, AIModelUpdate, ProviderModels, ProviderName
from app.schemas.platform import (
    CompanyAccess,
    CompanyAccessSave,
    CompanyList,
    PlatformMe,
    SettingGroup,
    SettingGroupRead,
    SettingGroupSave,
    SettingTest,
)
from app.services import ai_model_service, platform_service

router = APIRouter(prefix="/platform", tags=["platform"])


@router.get("/me", response_model=PlatformMe, status_code=status.HTTP_200_OK)
def platform_me(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return {"super_admin": platform_service.is_super_admin(db, str(current_user.id))}


# ---- AI providers (the SPEC-BE-053 editor, on PilotSonic's keys) ----
@router.get("/ai-models", response_model=AIModelList, status_code=status.HTTP_200_OK)
def list_ai_models(db: Session = Depends(get_db), admin: User = Depends(require_super_admin)) -> dict[str, Any]:
    return ai_model_service.list_providers(db, str(admin.tenant_id), admin=True)


@router.put("/ai-models/order", response_model=AIModelList, status_code=status.HTTP_200_OK)
def set_ai_model_order(payload: AIModelOrder, db: Session = Depends(get_db),
                       admin: User = Depends(require_super_admin)) -> dict[str, Any]:
    return ai_model_service.set_order(db, str(admin.tenant_id), str(admin.id), list(payload.order))


@router.put("/ai-models/{provider}", response_model=AIModelList, status_code=status.HTTP_200_OK)
def update_ai_model(provider: ProviderName, payload: AIModelUpdate, db: Session = Depends(get_db),
                    admin: User = Depends(require_super_admin)) -> dict[str, Any]:
    return ai_model_service.update_provider(db, str(admin.tenant_id), str(admin.id), provider, payload)


@router.get("/ai-models/{provider}/models", response_model=ProviderModels, status_code=status.HTTP_200_OK)
def list_provider_models(provider: ProviderName, db: Session = Depends(get_db),
                         admin: User = Depends(require_super_admin)) -> dict[str, Any]:
    return ai_model_service.list_models(db, str(admin.tenant_id), provider)


@router.post("/ai-models/{provider}/test", response_model=AIModelTestResult, status_code=status.HTTP_200_OK)
def test_ai_model(provider: ProviderName, db: Session = Depends(get_db),
                  admin: User = Depends(require_super_admin)) -> dict[str, Any]:
    return ai_model_service.test_provider(db, str(admin.tenant_id), str(admin.id), provider)


@router.delete("/ai-models/{provider}", response_model=AIModelList, status_code=status.HTTP_200_OK)
def delete_ai_model_key(provider: ProviderName, db: Session = Depends(get_db),
                        admin: User = Depends(require_super_admin)) -> dict[str, Any]:
    return ai_model_service.delete_key(db, str(admin.tenant_id), str(admin.id), provider)


# ---- SocialAPI master key, Zernio key, sign-in apps ----
@router.get("/settings", response_model=list[SettingGroupRead], status_code=status.HTTP_200_OK)
def list_settings(db: Session = Depends(get_db), admin: User = Depends(require_super_admin)) -> list[dict[str, Any]]:
    return [platform_service.group_status(db, g) for g in platform_service.FIELDS]


@router.put("/settings/{group}", response_model=SettingGroupRead, status_code=status.HTTP_200_OK)
def save_settings(group: SettingGroup, payload: SettingGroupSave, db: Session = Depends(get_db),
                  admin: User = Depends(require_super_admin)) -> dict[str, Any]:
    return platform_service.save_group(db, group, payload.values, payload.clear, str(admin.tenant_id), str(admin.id))


@router.post("/settings/{group}/test", response_model=SettingTest, status_code=status.HTTP_200_OK)
def test_settings(group: SettingGroup, db: Session = Depends(get_db),
                  admin: User = Depends(require_super_admin)) -> dict[str, Any]:
    """A real call with the saved key: SocialAPI lists brands, Zernio lists profiles.
    The sign-in apps can only be checked by a company connecting."""
    if group == "socialapi":
        from app.integrations import socialapi

        key = platform_service.value("socialapi", "api_key", db)
        if not key:
            raise AppError("Save the SocialAPI master key first.", 409)
        try:
            count = len(socialapi.list_brands(key))
            ok, message = True, f"Connected: SocialAPI answered ({count} brand(s))."
        except socialapi.SocialAPIError as exc:
            ok, message = False, exc.message
    elif group == "zernio":
        from app.integrations import zernio

        if not platform_service.value("zernio", "api_key", db):
            raise AppError("Save the Zernio API key first.", 409)
        try:
            zernio.call("GET", "/profiles")
            ok, message = True, "Connected: Zernio answered."
        except zernio.ZernioError as exc:
            ok, message = False, exc.message
    else:
        raise AppError("This app is checked when a company connects with it.", 422)
    platform_service.record(db, group, None if ok else message)
    platform_service.audit(db, str(admin.tenant_id), str(admin.id), "settings_tested", group=group, ok=ok)
    return {"ok": ok, "message": message}


# ---- Which companies may use the software's keys (SPEC-BE-103) ----
@router.get("/companies", response_model=CompanyList, status_code=status.HTTP_200_OK)
def list_companies(
    q: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(require_super_admin),
) -> dict[str, Any]:
    return platform_service.list_companies(db, q, page, page_size)


@router.put("/companies/{tenant_id}/access", response_model=CompanyAccess, status_code=status.HTTP_200_OK)
def save_company_access(tenant_id: UUID, payload: CompanyAccessSave, db: Session = Depends(get_db),
                        admin: User = Depends(require_super_admin)) -> dict[str, bool]:
    return platform_service.set_access(db, str(tenant_id), {str(k): v for k, v in payload.access.items()}, str(admin.tenant_id), str(admin.id))
