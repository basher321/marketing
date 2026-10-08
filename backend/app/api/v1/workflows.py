"""/workflows endpoints (SPEC-BE-014, SPEC-BE-034, SPEC-BE-049)."""
from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.workflow import (
    WorkflowLiveRun,
    WorkflowCatalog,
    WorkflowDetail,
    WorkflowEnabled,
    WorkflowListItem,
    WorkflowSave,
    WorkflowTestRequest,
    WorkflowTestResult,
    WorkflowVersion,
)
from app.services import workflow_service

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("", response_model=list[WorkflowListItem], status_code=status.HTTP_200_OK)
def list_workflows(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[dict[str, Any]]:
    return workflow_service.list_workflows(db, current_user.tenant_id)


# Editor form definitions (SPEC-BE-049); declared before /{workflow_id}.
@router.get("/catalog", response_model=WorkflowCatalog, status_code=status.HTTP_200_OK)
def get_catalog(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return workflow_service.catalog()


@router.post("", response_model=WorkflowDetail, status_code=status.HTTP_201_CREATED)
def create_workflow(
    payload: WorkflowSave,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return workflow_service.create_workflow(db, str(current_user.tenant_id), str(current_user.id), payload)


# Workflow Builder canvas (SPEC-FE-018): one workflow's raw structure. Same access as the list.
@router.get("/{workflow_id}", response_model=WorkflowDetail, status_code=status.HTTP_200_OK)
def get_workflow(
    workflow_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return workflow_service.get_workflow(db, str(current_user.tenant_id), workflow_id)


# Saving an edit creates a new version (SPEC-BE-049).
@router.put("/{workflow_id}", response_model=WorkflowDetail, status_code=status.HTTP_200_OK)
def update_workflow(
    workflow_id: str,
    payload: WorkflowSave,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return workflow_service.update_workflow(
        db, str(current_user.tenant_id), str(current_user.id), workflow_id, payload
    )


@router.patch("/{workflow_id}/enabled", response_model=WorkflowDetail, status_code=status.HTTP_200_OK)
def set_workflow_enabled(
    workflow_id: str,
    payload: WorkflowEnabled,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return workflow_service.set_enabled(
        db, str(current_user.tenant_id), str(current_user.id), workflow_id, payload.enabled
    )


@router.get("/{workflow_id}/versions", response_model=list[WorkflowVersion], status_code=status.HTTP_200_OK)
def list_versions(
    workflow_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[dict[str, Any]]:
    return workflow_service.list_versions(db, str(current_user.tenant_id), workflow_id)


@router.post(
    "/{workflow_id}/versions/{version_id}/restore",
    response_model=WorkflowDetail,
    status_code=status.HTTP_201_CREATED,
)
def restore_version(
    workflow_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return workflow_service.restore_version(
        db, str(current_user.tenant_id), str(current_user.id), workflow_id, version_id
    )


# Test Run (SPEC-BE-034): dry run, nothing external is called. SPEC-BE-034 rule 9 says to
# reuse the GET endpoints' capability; they declare none beyond authentication, so this
# endpoint requires the same (any authenticated user of the tenant).
@router.post("/{workflow_id}/test", response_model=WorkflowTestResult, status_code=status.HTTP_200_OK)
def test_run_workflow(
    workflow_id: str,
    payload: WorkflowTestRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return workflow_service.test_run_workflow(
        db,
        str(current_user.tenant_id),
        str(current_user.id),
        workflow_id,
        payload.input if payload else None,
    )


# Live manual run (SPEC-BE-060): real actions, unlike the dry-run Test Run above.
@router.post("/{workflow_id}/run", response_model=WorkflowLiveRun, status_code=status.HTTP_200_OK)
def run_workflow_now(
    workflow_id: str,
    payload: WorkflowTestRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return workflow_service.run_manual(
        db, str(current_user.tenant_id), str(current_user.id), workflow_id, (payload.input if payload else None) or {}
    )
