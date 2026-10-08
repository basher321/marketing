"""Paid Marketing lists across campaigns (SPEC-BE-079): ad sets and ads from
every builder, and pause/resume dispatched to the builder that made the row.
Reads are viewer+; pause/resume manager+; another tenant's id -> 404."""
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas import paid as s
from app.services import paid_service as svc

router = APIRouter(prefix="/paid", tags=["paid"])
Manager = Depends(require_permission("manager"))
# The live campaign_status enum (also used by ad_groups / ads).
Status = Literal["draft", "scheduled", "running", "paused", "completed", "failed"]
Range = Literal["7d", "30d", "90d"]


@router.get("/ad-sets", response_model=s.AdSetList, status_code=status.HTTP_200_OK)
def list_ad_sets(
    platform: s.PaidPlatform | None = None,
    status_: Status | None = Query(default=None, alias="status"),
    campaign_id: UUID | None = None,
    q: str | None = Query(default=None, max_length=100),
    range_key: Range = Query(default="30d", alias="range"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return svc.list_ad_sets(db, str(user.tenant_id), platform=platform, status=status_, campaign_id=str(campaign_id) if campaign_id else None,
                            q=q or None, range_key=range_key, page=page, page_size=page_size)


@router.get("/ads", response_model=s.AdList, status_code=status.HTTP_200_OK)
def list_ads(
    platform: s.PaidPlatform | None = None,
    status_: Status | None = Query(default=None, alias="status"),
    campaign_id: UUID | None = None,
    ad_set_id: UUID | None = None,
    q: str | None = Query(default=None, max_length=100),
    range_key: Range = Query(default="30d", alias="range"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return svc.list_ads(db, str(user.tenant_id), platform=platform, status=status_, campaign_id=str(campaign_id) if campaign_id else None,
                        ad_set_id=str(ad_set_id) if ad_set_id else None, q=q or None, range_key=range_key, page=page, page_size=page_size)


@router.post("/ad-sets/{ad_set_id}/pause", response_model=s.StatusResult, status_code=status.HTTP_200_OK)
def pause_ad_set(ad_set_id: UUID, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.set_ad_set_status(db, str(user.tenant_id), str(user.id), str(ad_set_id), resume=False)


@router.post("/ad-sets/{ad_set_id}/resume", response_model=s.StatusResult, status_code=status.HTTP_200_OK)
def resume_ad_set(ad_set_id: UUID, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.set_ad_set_status(db, str(user.tenant_id), str(user.id), str(ad_set_id), resume=True)


@router.post("/ads/{ad_id}/pause", response_model=s.StatusResult, status_code=status.HTTP_200_OK)
def pause_ad(ad_id: UUID, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.set_ad_status(db, str(user.tenant_id), str(user.id), str(ad_id), resume=False)


@router.post("/ads/{ad_id}/resume", response_model=s.StatusResult, status_code=status.HTTP_200_OK)
def resume_ad(ad_id: UUID, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.set_ad_status(db, str(user.tenant_id), str(user.id), str(ad_id), resume=True)
