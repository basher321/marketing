"""/analytics endpoints."""
from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.analytics import (
    ActivityFeed,
    AdsReport,
    EngagementReport,
    OrganicImportResult,
    OrganicReport,
    RangeKey,
    SalesSummary,
    ServiceReport,
    TopProduct,
)
from app.schemas.campaign import MetaSyncResult
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/sales", response_model=SalesSummary, status_code=status.HTTP_200_OK)
def get_sales_summary(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> SalesSummary:
    return SalesSummary.model_validate(analytics_service.get_sales_summary(db, current_user.tenant_id))


@router.get("/top-products", response_model=list[TopProduct], status_code=status.HTTP_200_OK)
def get_top_products(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[dict[str, Any]]:
    return analytics_service.get_top_products(db, current_user.tenant_id)


# Dashboard "Recent Activity" timeline (SPEC-BE-022): read-only feed of real events.
@router.get("/activity", response_model=ActivityFeed, status_code=status.HTTP_200_OK)
def get_recent_activity(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return analytics_service.get_recent_activity(db, str(current_user.tenant_id))


# Analytics page Ads / Engagement / Customer Service tabs (SPEC-BE-050); read-only,
# any authenticated role. ?range=7d|30d|90d (default 30d); other values -> 422.
@router.get("/ads", response_model=AdsReport, status_code=status.HTTP_200_OK)
def get_ads_report(
    range: RangeKey = "30d",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return analytics_service.get_ads_report(db, str(current_user.tenant_id), range)


@router.get("/engagement", response_model=EngagementReport, status_code=status.HTTP_200_OK)
def get_engagement_report(
    range: RangeKey = "30d",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return analytics_service.get_engagement_report(db, str(current_user.tenant_id), range)


@router.get("/customer-service", response_model=ServiceReport, status_code=status.HTTP_200_OK)
def get_service_report(
    range: RangeKey = "30d",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return analytics_service.get_service_report(db, str(current_user.tenant_id), range)

# Organic Marketing results (SPEC-BE-078): imported post metrics; null = no data.
@router.get("/organic", response_model=OrganicReport, status_code=status.HTTP_200_OK)
def get_organic_report(
    range: RangeKey = "30d",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return analytics_service.get_organic_report(db, str(current_user.tenant_id), range)


@router.post("/organic/import", response_model=OrganicImportResult, status_code=status.HTTP_200_OK)
def import_organic(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return analytics_service.import_organic_metrics(db, str(current_user.tenant_id), str(current_user.id))


# On-demand Meta results import for all published campaigns (SPEC-BE-056).
@router.post("/meta/sync", response_model=MetaSyncResult, status_code=status.HTTP_200_OK)
def sync_meta_results(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    from app.services import campaign_service

    return campaign_service.sync_meta_results(db, str(current_user.tenant_id), str(current_user.id))
