"""/campaigns endpoints."""
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.campaign import (
    AdSpend24h,
    CampaignDetail,
    CampaignDraftCreate,
    CampaignDraftUpdate,
    CampaignListItem,
    CampaignMetrics,
    CampaignResults,
    MetaSyncResult,
)
from app.services import campaign_service

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


# Single source for the Marketing page "Active Campaigns"/"Avg. ROAS" cards and the Dashboard
# Marketing engine card (SPEC-BE-009). The pre-spec list/create/status routes were removed: the
# campaign list is a separate, later spec.
@router.get("/metrics", response_model=CampaignMetrics, status_code=status.HTTP_200_OK)
def get_campaign_metrics(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> CampaignMetrics:
    return CampaignMetrics.model_validate(
        campaign_service.get_campaign_metrics(db, current_user.tenant_id)
    )


# Marketing page "Active Campaigns" table (SPEC-BE-038).
@router.get("", response_model=list[CampaignListItem], status_code=status.HTTP_200_OK)
def list_campaigns(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[dict[str, Any]]:
    return campaign_service.list_campaigns(db, str(current_user.tenant_id))


# Dashboard "Ad Spend" card (SPEC-BE-019).
@router.get("/ad-spend-24h", response_model=AdSpend24h, status_code=status.HTTP_200_OK)
def get_ad_spend_24h(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> AdSpend24h:
    return AdSpend24h.model_validate(
        campaign_service.get_ad_spend_24h(db, str(current_user.tenant_id))
    )


# Campaign Wizard drafts (SPEC-BE-044). /drafts is declared before /{campaign_id}.
@router.get("/drafts", response_model=list[CampaignDetail], status_code=status.HTTP_200_OK)
def list_drafts(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[dict[str, Any]]:
    return campaign_service.list_drafts(db, str(current_user.tenant_id))


@router.post("", response_model=CampaignDetail, status_code=status.HTTP_201_CREATED)
def create_draft(
    payload: CampaignDraftCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return campaign_service.create_draft(
        db, str(current_user.tenant_id), str(current_user.id), payload
    )


@router.get("/{campaign_id}", response_model=CampaignDetail, status_code=status.HTTP_200_OK)
def get_campaign(
    campaign_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return campaign_service.get_campaign(db, str(current_user.tenant_id), str(campaign_id))


@router.patch("/{campaign_id}", response_model=CampaignDetail, status_code=status.HTTP_200_OK)
def update_draft(
    campaign_id: UUID,
    payload: CampaignDraftUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return campaign_service.update_draft(
        db, str(current_user.tenant_id), str(current_user.id), str(campaign_id), payload
    )


# Launch / pause / resume (SPEC-BE-047). Launch goes live, or is queued for the
# owner's approval when over the tenant's daily ad cap and the actor isn't the owner.
@router.post(
    "/{campaign_id}/launch", response_model=CampaignDetail, status_code=status.HTTP_200_OK
)
def launch_campaign(
    campaign_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return campaign_service.launch(
        db,
        str(current_user.tenant_id),
        str(current_user.id),
        current_user.role == "owner",
        str(campaign_id),
    )


@router.post("/{campaign_id}/pause", response_model=CampaignDetail, status_code=status.HTTP_200_OK)
def pause_campaign(
    campaign_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return campaign_service.pause(
        db, str(current_user.tenant_id), str(current_user.id), str(campaign_id)
    )


@router.post(
    "/{campaign_id}/resume", response_model=CampaignDetail, status_code=status.HTTP_200_OK
)
def resume_campaign(
    campaign_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return campaign_service.resume(
        db, str(current_user.tenant_id), str(current_user.id), str(campaign_id)
    )


# Meta results (SPEC-BE-056): on-demand import for one campaign, and its results.
@router.post("/{campaign_id}/sync", response_model=MetaSyncResult, status_code=status.HTTP_200_OK)
def sync_campaign_results(
    campaign_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return campaign_service.sync_meta_results(
        db, str(current_user.tenant_id), str(current_user.id), str(campaign_id)
    )


@router.get("/{campaign_id}/results", response_model=CampaignResults, status_code=status.HTTP_200_OK)
def get_campaign_results(
    campaign_id: UUID,
    range: Literal["7d", "30d", "90d", "lifetime"] = "7d",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return campaign_service.get_campaign_results(db, str(current_user.tenant_id), str(campaign_id), range)
