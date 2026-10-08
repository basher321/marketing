"""Meta Ads Manager-style builder endpoints (SPEC-BE-055).

Lookups for the pickers (/meta/*), media upload, and the Campaign -> Ad set ->
Ad tree (/campaigns/builder, /campaigns/{id}/builder, /ad-sets/*, /ads/*).
Writes are manager+; every route is tenant-scoped (another tenant's id -> 404).
"""
from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas import meta as s
from app.services import meta_builder_service as svc

router = APIRouter(tags=["meta-builder"])
Manager = Depends(require_permission("manager"))


def _t(user: User) -> str:
    return str(user.tenant_id)


# --- lookups ---------------------------------------------------------------
@router.get("/meta/objectives", response_model=s.ObjectivesResult, status_code=status.HTTP_200_OK)
def objectives(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    return svc.objectives(db, _t(user))


@router.get("/meta/targeting/search", response_model=list[s.LookupItem], status_code=status.HTTP_200_OK)
def targeting_search(
    type: str = Query(..., pattern="^(adgeolocation|adinterest|adlocale|adTargetingCategory)$"),
    q: str = Query(..., min_length=1, max_length=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    return svc.targeting_search(db, _t(user), type, q)


@router.get("/meta/custom-audiences", response_model=list[s.LookupItem], status_code=status.HTTP_200_OK)
def custom_audiences(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    return svc.custom_audiences(db, _t(user))


@router.get("/meta/apps", response_model=list[s.LookupItem], status_code=status.HTTP_200_OK)
def apps(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    return svc.apps(db, _t(user))


@router.get("/meta/lead-forms", response_model=list[s.LookupItem], status_code=status.HTTP_200_OK)
def lead_forms(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    return svc.lead_forms(db, _t(user))


@router.get("/meta/product-sets", response_model=list[s.ProductSet], status_code=status.HTTP_200_OK)
def product_sets(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    return svc.product_sets(db, _t(user))


@router.get("/meta/posts", response_model=s.PostList, status_code=status.HTTP_200_OK)
def posts(
    platform: str = Query("facebook", pattern="^(facebook|instagram)$"),
    after: str | None = Query(None, max_length=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return svc.posts(db, _t(user), platform, after)


@router.post("/meta/posts", response_model=s.ExistingPost, status_code=status.HTTP_201_CREATED)
def create_post(payload: s.PostCreate, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.create_post(db, _t(user), str(user.id), payload)


@router.get("/meta/pixels",response_model=list[s.LookupItem], status_code=status.HTTP_200_OK)
def pixels(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    return svc.pixels(db, _t(user))


@router.post("/meta/reach-estimate", response_model=s.ReachResult, status_code=status.HTTP_200_OK)
def reach_estimate(payload: s.ReachRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    return svc.reach_estimate(db, _t(user), payload)


@router.post("/meta/media", response_model=s.MediaResult, status_code=status.HTTP_201_CREATED)
async def upload_media(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    content = await file.read(svc.VIDEO_MAX + 1)
    return svc.upload_media(db, _t(user), str(user.id), file.filename or "", content)


@router.get("/meta/media/videos/{video_id}", response_model=s.MediaResult, status_code=status.HTTP_200_OK)
def video_status(video_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    return svc.video_status(db, _t(user), video_id)


# --- campaign tree ---------------------------------------------------------
@router.post("/campaigns/builder", response_model=s.BuilderTree, status_code=status.HTTP_201_CREATED)
def create_campaign(payload: s.CampaignCreate, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.create_campaign(db, _t(user), str(user.id), payload)


@router.get("/campaigns/{campaign_id}/builder", response_model=s.BuilderTree, status_code=status.HTTP_200_OK)
def get_tree(campaign_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    return svc.get_tree(db, _t(user), campaign_id)


@router.patch("/campaigns/{campaign_id}/builder", response_model=s.BuilderTree, status_code=status.HTTP_200_OK)
def update_campaign(campaign_id: str, payload: s.CampaignFields, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.update_campaign(db, _t(user), str(user.id), campaign_id, payload)


@router.post("/campaigns/{campaign_id}/ad-sets", response_model=s.BuilderTree, status_code=status.HTTP_201_CREATED)
def add_ad_set(campaign_id: str, payload: s.AdSetCreate, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.add_ad_set(db, _t(user), str(user.id), campaign_id, payload)


@router.post("/campaigns/{campaign_id}/validate", response_model=s.ValidateResult, status_code=status.HTTP_200_OK)
def validate(campaign_id: str, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.validate(db, _t(user), str(user.id), campaign_id)


@router.post("/campaigns/{campaign_id}/publish", response_model=s.BuilderTree, status_code=status.HTTP_200_OK)
def publish(campaign_id: str, payload: s.PublishRequest, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.publish(db, _t(user), str(user.id), user.role == "owner", campaign_id, payload.mode)


@router.patch("/ad-sets/{ad_set_id}", response_model=s.BuilderTree, status_code=status.HTTP_200_OK)
def update_ad_set(ad_set_id: str, payload: s.AdSetFields, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.update_ad_set(db, _t(user), str(user.id), ad_set_id, payload)


@router.post("/ad-sets/{ad_set_id}/duplicate", response_model=s.BuilderTree, status_code=status.HTTP_201_CREATED)
def duplicate_ad_set(ad_set_id: str, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.duplicate_ad_set(db, _t(user), str(user.id), ad_set_id)


@router.delete("/ad-sets/{ad_set_id}", response_model=s.BuilderTree, status_code=status.HTTP_200_OK)
def delete_ad_set(ad_set_id: str, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.delete_ad_set(db, _t(user), str(user.id), ad_set_id)


@router.post("/ad-sets/{ad_set_id}/ads", response_model=s.BuilderTree, status_code=status.HTTP_201_CREATED)
def add_ad(ad_set_id: str, payload: s.AdCreate, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.add_ad(db, _t(user), str(user.id), ad_set_id, payload)


@router.post("/ad-sets/{ad_set_id}/pause", response_model=s.StatusResult, status_code=status.HTTP_200_OK)
def pause_ad_set(ad_set_id: str, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.set_status(db, _t(user), str(user.id), "ad_set", ad_set_id, False)


@router.post("/ad-sets/{ad_set_id}/resume", response_model=s.StatusResult, status_code=status.HTTP_200_OK)
def resume_ad_set(ad_set_id: str, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.set_status(db, _t(user), str(user.id), "ad_set", ad_set_id, True)


@router.patch("/ads/{ad_id}", response_model=s.BuilderTree, status_code=status.HTTP_200_OK)
def update_ad(ad_id: str, payload: s.AdFields, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.update_ad(db, _t(user), str(user.id), ad_id, payload)


@router.post("/ads/{ad_id}/duplicate", response_model=s.BuilderTree, status_code=status.HTTP_201_CREATED)
def duplicate_ad(ad_id: str, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.duplicate_ad(db, _t(user), str(user.id), ad_id)


@router.delete("/ads/{ad_id}", response_model=s.BuilderTree, status_code=status.HTTP_200_OK)
def delete_ad(ad_id: str, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.delete_ad(db, _t(user), str(user.id), ad_id)


@router.post("/ads/{ad_id}/preview", response_model=s.PreviewResult, status_code=status.HTTP_200_OK)
def preview(
    ad_id: str,
    format: str = Query("MOBILE_FEED_STANDARD"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return svc.preview(db, _t(user), ad_id, format)


@router.post("/ads/{ad_id}/pause", response_model=s.StatusResult, status_code=status.HTTP_200_OK)
def pause_ad(ad_id: str, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.set_status(db, _t(user), str(user.id), "ad", ad_id, False)


@router.post("/ads/{ad_id}/resume", response_model=s.StatusResult, status_code=status.HTTP_200_OK)
def resume_ad(ad_id: str, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.set_status(db, _t(user), str(user.id), "ad", ad_id, True)
