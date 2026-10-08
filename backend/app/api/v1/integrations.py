"""/integrations endpoints (SPEC-BE-017, SPEC-BE-052)."""
from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.integration import (
    CatalogProvider,
    IntegrationSave,
    IntegrationStatus,
    IntegrationTestResult,
    MetaCallback,
    MetaChoices,
    MetaConnectUrl,
    MetaSelect,
)
from app.services import integration_service

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("", response_model=list[IntegrationStatus], status_code=status.HTTP_200_OK)
def list_integration_statuses(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[dict[str, Any]]:
    return integration_service.list_integration_statuses(db, current_user.tenant_id)


# Declared before /{provider} routes.
@router.get("/catalog", response_model=list[CatalogProvider], status_code=status.HTTP_200_OK)
def get_catalog(current_user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    return integration_service.catalog()


# "Connect with Facebook" (SPEC-BE-054), manager+. Declared before /{provider}.
@router.get("/meta/connect", response_model=MetaConnectUrl, status_code=status.HTTP_200_OK)
def meta_connect(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return integration_service.meta_connect_url(db, str(current_user.tenant_id), str(current_user.id))


@router.post("/meta/callback", response_model=MetaChoices, status_code=status.HTTP_200_OK)
def meta_callback(
    payload: MetaCallback,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return integration_service.meta_callback(
        db, str(current_user.tenant_id), str(current_user.id), payload.code, payload.state
    )


@router.post("/meta/select", response_model=IntegrationStatus, status_code=status.HTTP_200_OK)
def meta_select(
    payload: MetaSelect,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return integration_service.meta_select(
        db,
        str(current_user.tenant_id),
        str(current_user.id),
        payload.ad_account_id,
        payload.page_id,
        payload.instagram_id,
        payload.pixel_id,
    )


@router.put("/{provider}", response_model=IntegrationTestResult, status_code=status.HTTP_200_OK)
def save_integration(
    provider: str,
    payload: IntegrationSave,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return integration_service.save_credentials(
        db, str(current_user.tenant_id), str(current_user.id), provider, payload
    )


@router.post("/{provider}/test", response_model=IntegrationTestResult, status_code=status.HTTP_200_OK)
def test_integration(
    provider: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return integration_service.test_connection(db, str(current_user.tenant_id), str(current_user.id), provider)


@router.delete("/{provider}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
def disconnect_integration(
    provider: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> None:
    integration_service.disconnect(db, str(current_user.tenant_id), str(current_user.id), provider)
