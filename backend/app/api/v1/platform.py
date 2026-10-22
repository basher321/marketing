"""/platform: PilotSonic's Super admin (SPEC-BE-101). The software's AI keys,
SocialAPI master key, Zernio key and sign-in apps, used by every company.

Only a user in platform_admins reaches these routes (anyone else gets 404);
GET /platform/me tells the UI whether to show the Super admin screen."""
from typing import Any
from uuid import UUID

from typing import Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.db.session import get_db
from app.dependencies import get_current_user, require_super_admin
from app.models.user import User
from app.schemas.ai_model import AIModelList, AIModelOrder, AIModelTestResult, AIModelUpdate, ProviderModels, ProviderName
from app.schemas.platform import (
    AppBranding,
    AppBrandingText,
    IntegrationErrorList,
    IntegrationHealthList,
    CompanyAccess,
    CompanyAccessSave,
    CompanyList,
    PlatformMe,
    SettingGroup,
    SettingGroupRead,
    SettingGroupSave,
    SettingTest,
)
from app.schemas.sms import SmsNumberAssign, SmsNumberAssigned, SmsNumberList
from app.services import ai_model_service, platform_service, sms_service
from app.services.tenant_service import MAX_IMAGE_BYTES

BrandingImage = Literal["logo", "logo_dark", "favicon"]

router = APIRouter(prefix="/platform", tags=["platform"])


@router.get("/me", response_model=PlatformMe, status_code=status.HTTP_200_OK)
def platform_me(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return {"super_admin": platform_service.is_super_admin(db, str(current_user.id))}


# ---- AI providers (the SPEC-BE-053 editor, on PilotSonic's keys) ----
# SPEC-BE-113: the app's name and logo. Public: the login page shows it before sign-in.
@router.get("/branding", response_model=AppBranding, status_code=status.HTTP_200_OK)
def get_app_branding(db: Session = Depends(get_db)) -> dict[str, Any]:
    return platform_service.app_branding(db)


@router.put("/branding", response_model=AppBranding, status_code=status.HTTP_200_OK)
def save_app_branding(payload: AppBrandingText, db: Session = Depends(get_db),
                      admin: User = Depends(require_super_admin)) -> dict[str, Any]:
    return platform_service.set_app_branding(db, payload.model_dump(exclude_unset=True), str(admin.tenant_id),
                                             str(admin.id))


@router.put("/branding/{slot}", response_model=AppBranding, status_code=status.HTTP_200_OK)
async def upload_app_branding(slot: BrandingImage, file: UploadFile = File(...), db: Session = Depends(get_db),
                              admin: User = Depends(require_super_admin)) -> dict[str, Any]:
    data = await file.read(MAX_IMAGE_BYTES + 1)
    return platform_service.set_app_branding_image(db, slot, data, str(admin.tenant_id), str(admin.id))


@router.delete("/branding/{slot}", response_model=AppBranding, status_code=status.HTTP_200_OK)
def delete_app_branding(slot: BrandingImage, db: Session = Depends(get_db),
                        admin: User = Depends(require_super_admin)) -> dict[str, Any]:
    return platform_service.set_app_branding(db, {slot: None}, str(admin.tenant_id), str(admin.id))


# SPEC-BE-113 FR3: integration health and the recent errors log.
@router.get("/integrations/health", response_model=IntegrationHealthList, status_code=status.HTTP_200_OK)
def integration_health(db: Session = Depends(get_db), admin: User = Depends(require_super_admin)) -> dict[str, Any]:
    return {"items": platform_service.integration_health(db)}


@router.get("/integrations/errors", response_model=IntegrationErrorList, status_code=status.HTTP_200_OK)
def integration_errors(
    provider: str | None = Query(default=None, max_length=40),
    cursor: str | None = Query(default=None, pattern=r"^\d{1,6}$"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_super_admin),
) -> dict[str, Any]:
    return platform_service.integration_errors(db, provider, int(cursor or 0))


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
    elif group == "twilio":
        from app.integrations import twilio_sms
        from app.services import sms_service

        sid, token = sms_service.credentials(db)
        if not (sid and token):
            raise AppError("Save the Twilio account SID and auth token first.", 409)
        try:
            info = twilio_sms.account(sid, token)
            count = len([n for n in twilio_sms.numbers(sid, token) if n["sms"]])
            ok, message = True, f"Connected: Twilio account {info.get('name') or ''} ({count} SMS number(s))."
        except twilio_sms.SmsError as exc:
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


# ---- SPEC-BE-108: Twilio numbers, one per company ----
@router.get("/sms/numbers", response_model=SmsNumberList, status_code=status.HTTP_200_OK)
def list_sms_numbers(db: Session = Depends(get_db), admin: User = Depends(require_super_admin)) -> dict[str, Any]:
    return {"items": sms_service.list_numbers(db)}


@router.put("/companies/{tenant_id}/sms-number", response_model=SmsNumberAssigned, status_code=status.HTTP_200_OK)
def assign_sms_number(tenant_id: UUID, payload: SmsNumberAssign, db: Session = Depends(get_db),
                      admin: User = Depends(require_super_admin)) -> dict[str, Any]:
    return sms_service.assign_number(db, str(tenant_id), payload.number, admin)
