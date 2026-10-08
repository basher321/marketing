"""Zernio paid-ads routes (SPEC-BE-084): every company's paid campaigns through
one server-wide Zernio key, next to the existing builders (unchanged).

Roles: viewer+ reads; manager+ connects accounts and creates / boosts / pauses /
resumes / edits / deletes campaigns (D3 = B: no owner-only step).
Without ZERNIO_API_KEY every route but /status and /platforms answers 503.
"""
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas import zernio as s
from app.services import zernio_service as svc

router = APIRouter(prefix="/zernio", tags=["zernio"])
Viewer = Depends(get_current_user)
Manager = Depends(require_permission("manager"))
# Zernio / platform ids (hex, numeric, act_…, urn:li:…): no slashes or spaces.
IdStr = Annotated[str, Path(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:=\-]+$")]
# A fresh Query per parameter: FastAPI binds a Query object's alias to the first
# parameter that uses it, so one shared instance would leak names across routes.
IdQ = Annotated[str, Query(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:=\-]+$")]
RangeQ = Annotated[Literal["7d", "30d", "90d"], Query(alias="range")]
PlatformQ = Literal["facebook", "instagram", "tiktok", "linkedin", "pinterest", "twitter", "googleads"]


def _t(user: User) -> str:
    return str(user.tenant_id)


# --- Status, platforms, connect ----------------------------------------------
@router.get("/status", response_model=s.Status, status_code=status.HTTP_200_OK)
def get_status(db: Session = Depends(get_db), user: User = Viewer) -> dict[str, Any]:
    return svc.status(db, _t(user))


@router.get("/platforms", response_model=s.PlatformList, status_code=status.HTTP_200_OK)
def platforms(db: Session = Depends(get_db), user: User = Viewer) -> dict[str, Any]:
    return svc.platforms(db, _t(user))


@router.post("/connect", response_model=s.ConnectResult, status_code=status.HTTP_200_OK)
def connect(payload: s.ConnectRequest, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.connect(db, _t(user), str(user.id), payload.platform)


@router.post("/callback", response_model=s.CallbackResult, status_code=status.HTTP_200_OK)
def callback(payload: s.CallbackRequest, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.callback(db, _t(user), str(user.id), payload)


@router.delete("/accounts/{account_id}", status_code=status.HTTP_200_OK, response_model=s.StatusResult)
def disconnect(account_id: IdStr, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    svc.disconnect(db, _t(user), str(user.id), account_id)
    return {"status": "disconnected", "message": "Disconnected."}


# --- Ad accounts, identities, posts, targeting -------------------------------
@router.get("/accounts/{account_id}/ad-accounts", response_model=s.AdAccountList, status_code=status.HTTP_200_OK)
def ad_accounts(account_id: IdStr, db: Session = Depends(get_db), user: User = Viewer) -> dict[str, Any]:
    return svc.ad_accounts(db, _t(user), account_id)


@router.get("/accounts/{account_id}/identities", response_model=s.Identities, status_code=status.HTTP_200_OK)
def identities(account_id: IdStr, ad_account_id: IdQ, db: Session = Depends(get_db),
               user: User = Viewer) -> dict[str, Any]:
    return svc.identities(db, _t(user), account_id, ad_account_id)


@router.get("/accounts/{account_id}/posts", response_model=s.PostList, status_code=status.HTTP_200_OK)
def account_posts(account_id: IdStr, db: Session = Depends(get_db), user: User = Viewer) -> dict[str, Any]:
    return svc.account_posts(db, _t(user), account_id)


@router.get("/targeting/search", response_model=s.SearchResult, status_code=status.HTTP_200_OK)
def targeting_search(
    account_id: IdQ,
    q: str = Query(min_length=1, max_length=100),
    dimension: Literal["geo", "interest", "behavior", "language"] = Query(default="geo"),
    geo_type: Literal["all", "country", "region", "city", "zip", "metro_area"] | None = Query(default=None),
    country: str | None = Query(default=None, min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$"),
    ad_account_id: str | None = Query(default=None, max_length=200, pattern=r"^[A-Za-z0-9_.:=\-]+$"),
    db: Session = Depends(get_db),
    user: User = Viewer,
) -> dict[str, Any]:
    return svc.targeting_search(db, _t(user), account_id, q, dimension, geo_type, country.upper() if country else None,
                                ad_account_id)


@router.post("/targeting/reach", response_model=s.Reach, status_code=status.HTTP_200_OK)
def reach(payload: s.ReachRequest, db: Session = Depends(get_db), user: User = Viewer) -> dict[str, Any]:
    return svc.reach(db, _t(user), payload)


# --- Create, validate, preview, boost ----------------------------------------
@router.post("/campaigns", response_model=s.CreateResult, status_code=status.HTTP_201_CREATED)
def create_campaign(payload: s.CampaignCreate, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.create_campaign(db, _t(user), str(user.id), payload)


@router.post("/campaigns/validate", response_model=s.ValidateResult, status_code=status.HTTP_200_OK)
def validate_campaign(payload: s.CampaignCreate, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.validate_campaign(db, _t(user), payload)


@router.post("/campaigns/preview", response_model=s.PreviewResult, status_code=status.HTTP_200_OK)
def preview(payload: s.CampaignCreate, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.preview(db, _t(user), payload)


@router.post("/boost", response_model=s.CreateResult, status_code=status.HTTP_201_CREATED)
def boost(payload: s.BoostCreate, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.boost(db, _t(user), str(user.id), payload)


# --- List and manage -----------------------------------------------------------
@router.get("/campaigns", response_model=s.CampaignList, status_code=status.HTTP_200_OK)
def list_campaigns(
    platform: PlatformQ | None = Query(default=None),
    status_: Literal["active", "paused", "pending_review", "rejected", "completed", "cancelled", "error"] | None = Query(
        default=None, alias="status"),
    q: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1, le=1000),
    range_: RangeQ = "30d",
    db: Session = Depends(get_db),
    user: User = Viewer,
) -> dict[str, Any]:
    return svc.list_campaigns(db, _t(user), platform, status_, q, page, range_)


@router.post("/campaigns/{campaign_id}/{action}", response_model=s.StatusResult, status_code=status.HTTP_200_OK)
def campaign_status(campaign_id: IdStr, action: Literal["pause", "resume"], db: Session = Depends(get_db),
                    user: User = Manager) -> dict[str, Any]:
    return svc.set_status(db, _t(user), str(user.id), "campaign", campaign_id, action)


@router.post("/ad-sets/{ad_set_id}/{action}", response_model=s.StatusResult, status_code=status.HTTP_200_OK)
def ad_set_status(ad_set_id: IdStr, action: Literal["pause", "resume"], db: Session = Depends(get_db),
                  user: User = Manager) -> dict[str, Any]:
    return svc.set_status(db, _t(user), str(user.id), "ad_set", ad_set_id, action)


@router.post("/ads/{ad_id}/{action}", response_model=s.StatusResult, status_code=status.HTTP_200_OK)
def ad_status(ad_id: IdStr, action: Literal["pause", "resume"], db: Session = Depends(get_db),
              user: User = Manager) -> dict[str, Any]:
    return svc.set_status(db, _t(user), str(user.id), "ad", ad_id, action)


@router.patch("/campaigns/{campaign_id}", response_model=s.CampaignNode, status_code=status.HTTP_200_OK)
def update_campaign(campaign_id: IdStr, payload: s.CampaignUpdate, db: Session = Depends(get_db),
                    user: User = Manager) -> dict[str, Any]:
    return svc.update_campaign(db, _t(user), str(user.id), campaign_id, payload)


@router.delete("/campaigns/{campaign_id}", response_model=s.DeleteResult, status_code=status.HTTP_200_OK)
def delete_campaign(campaign_id: IdStr, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.delete_campaign(db, _t(user), str(user.id), campaign_id)


@router.get("/campaigns/{campaign_id}/analytics", response_model=s.CampaignAnalytics, status_code=status.HTTP_200_OK)
def campaign_analytics(
    campaign_id: IdStr,
    range_: RangeQ = "30d",
    breakdowns: str | None = Query(default=None, max_length=60, pattern=r"^(age|gender|country)(,(age|gender|country))*$"),
    db: Session = Depends(get_db),
    user: User = Viewer,
) -> dict[str, Any]:
    return svc.campaign_analytics(db, _t(user), campaign_id, range_, breakdowns)
