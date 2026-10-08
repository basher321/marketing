"""Multi-platform Ad Manager endpoints (SPEC-BE-062).

GET /ads/platforms drives the Ad Manager page (Meta included, as a link to its
own builder). The rest is the builder for TikTok, Google Ads, LinkedIn, X,
Snapchat and Pinterest. Writes are manager+; every route is tenant-scoped
(another tenant's id -> 404).
"""
from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas import ads_builder as s
from app.services import ads_builder_service as svc

router = APIRouter(prefix="/ads", tags=["ad-manager"])
Manager = Depends(require_permission("manager"))
MEDIA_MAX = 500 * 1024 * 1024  # the largest platform limit (TikTok video)


def _t(user: User) -> str:
    return str(user.tenant_id)


@router.get("/platforms", response_model=s.PlatformList, status_code=status.HTTP_200_OK)
def platforms(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    return svc.platforms(db, _t(user))


@router.post("/results/sync", response_model=s.ResultsSync, status_code=status.HTTP_200_OK)
def sync_results(campaign_id: str | None = Query(default=None, max_length=36), db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    """Import results now for every published platform campaign (or one);
    throttled to once per 5 minutes per platform connection."""
    return svc.sync_results(db, _t(user), str(user.id), campaign_id)


@router.get("/{platform}/lookup/{kind}", response_model=list[s.LookupItem], status_code=status.HTTP_200_OK)
def lookup(
    platform: s.BuilderPlatform, kind: str, q: str = Query(default="", max_length=100),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    return svc.lookup(db, _t(user), platform, kind, q)


@router.post("/{platform}/media", response_model=s.MediaResult, status_code=status.HTTP_201_CREATED)
async def upload_media(platform: s.BuilderPlatform, file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    content = await file.read(MEDIA_MAX + 1)
    if len(content) > MEDIA_MAX:
        raise AppError("The file is larger than 500 MB.", 413)
    return svc.upload_media(db, _t(user), str(user.id), platform, file.filename or "upload", content)


@router.post("/{platform}/campaigns", response_model=s.PlatformTree, status_code=status.HTTP_201_CREATED)
def create_campaign(platform: s.BuilderPlatform, payload: s.CampaignCreate, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.create_campaign(db, _t(user), str(user.id), platform, payload)


@router.get("/campaigns/{campaign_id}", response_model=s.PlatformTree, status_code=status.HTTP_200_OK)
def get_tree(campaign_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    return svc.get_tree(db, _t(user), campaign_id)


@router.patch("/campaigns/{campaign_id}", response_model=s.PlatformTree, status_code=status.HTTP_200_OK)
def update_campaign(campaign_id: str, payload: s.CampaignFields, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.update_campaign(db, _t(user), str(user.id), campaign_id, payload)


@router.post("/campaigns/{campaign_id}/groups", response_model=s.PlatformTree, status_code=status.HTTP_201_CREATED)
def add_group(campaign_id: str, payload: s.GroupFields, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.add_group(db, _t(user), str(user.id), campaign_id, payload)


@router.post("/campaigns/{campaign_id}/validate", response_model=s.ValidateResult, status_code=status.HTTP_200_OK)
def validate(campaign_id: str, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.validate(db, _t(user), campaign_id)


@router.post("/campaigns/{campaign_id}/publish", response_model=s.PlatformTree, status_code=status.HTTP_200_OK)
def publish(campaign_id: str, payload: s.PublishRequest, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.publish(db, _t(user), str(user.id), user.role == "owner", campaign_id, payload.mode)


@router.post("/campaigns/{campaign_id}/pause", response_model=s.StatusResult, status_code=status.HTTP_200_OK)
def pause_campaign(campaign_id: str, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.set_status(db, _t(user), str(user.id), "campaign", campaign_id, resume=False)


@router.post("/campaigns/{campaign_id}/resume", response_model=s.StatusResult, status_code=status.HTTP_200_OK)
def resume_campaign(campaign_id: str, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.set_status(db, _t(user), str(user.id), "campaign", campaign_id, resume=True)


@router.patch("/groups/{group_id}", response_model=s.PlatformTree, status_code=status.HTTP_200_OK)
def update_group(group_id: str, payload: s.GroupFields, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.update_group(db, _t(user), str(user.id), group_id, payload)


@router.delete("/groups/{group_id}", response_model=s.PlatformTree, status_code=status.HTTP_200_OK)
def delete_group(group_id: str, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.delete_group(db, _t(user), str(user.id), group_id)


@router.post("/groups/{group_id}/duplicate", response_model=s.PlatformTree, status_code=status.HTTP_201_CREATED)
def duplicate_group(group_id: str, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.duplicate_group(db, _t(user), str(user.id), group_id)


@router.post("/groups/{group_id}/ads", response_model=s.PlatformTree, status_code=status.HTTP_201_CREATED)
def add_ad(group_id: str, payload: s.AdFields, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.add_ad(db, _t(user), str(user.id), group_id, payload)


@router.post("/groups/{group_id}/pause", response_model=s.StatusResult, status_code=status.HTTP_200_OK)
def pause_group(group_id: str, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.set_status(db, _t(user), str(user.id), "group", group_id, resume=False)


@router.post("/groups/{group_id}/resume", response_model=s.StatusResult, status_code=status.HTTP_200_OK)
def resume_group(group_id: str, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.set_status(db, _t(user), str(user.id), "group", group_id, resume=True)


@router.patch("/ads/{ad_id}", response_model=s.PlatformTree, status_code=status.HTTP_200_OK)
def update_ad(ad_id: str, payload: s.AdFields, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.update_ad(db, _t(user), str(user.id), ad_id, payload)


@router.delete("/ads/{ad_id}", response_model=s.PlatformTree, status_code=status.HTTP_200_OK)
def delete_ad(ad_id: str, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.delete_ad(db, _t(user), str(user.id), ad_id)


@router.post("/ads/{ad_id}/duplicate", response_model=s.PlatformTree, status_code=status.HTTP_201_CREATED)
def duplicate_ad(ad_id: str, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.duplicate_ad(db, _t(user), str(user.id), ad_id)


@router.post("/ads/{ad_id}/pause", response_model=s.StatusResult, status_code=status.HTTP_200_OK)
def pause_ad(ad_id: str, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.set_status(db, _t(user), str(user.id), "ad", ad_id, resume=False)


@router.post("/ads/{ad_id}/resume", response_model=s.StatusResult, status_code=status.HTTP_200_OK)
def resume_ad(ad_id: str, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.set_status(db, _t(user), str(user.id), "ad", ad_id, resume=True)
