"""AI Ad Autopilot endpoints (SPEC-BE-069).

Starting, answering, retrying, regenerating, discarding and publishing are
manager+; reading is any role. A run never publishes by itself: POST
/{id}/publish is the only path to going live, and it applies the normal
approval rules. Every route is tenant-scoped (another tenant's id -> 404).
"""
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas import ai_campaign as s
from app.services import ai_campaign_service as svc

router = APIRouter(prefix="/ai-campaigns", tags=["ai-campaigns"])
Manager = Depends(require_permission("manager"))


def _t(user: User) -> str:
    return str(user.tenant_id)


@router.post("", response_model=s.AICampaignRunRead, status_code=status.HTTP_202_ACCEPTED)
def create(payload: s.AICampaignCreate, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.create_run(db, _t(user), str(user.id), payload)


@router.get("", response_model=s.AICampaignRunList, status_code=status.HTTP_200_OK)
def list_runs(status_filter: str | None = Query(default=None, alias="status", max_length=30), db: Session = Depends(get_db),
              user: User = Depends(get_current_user)) -> dict[str, Any]:
    return svc.list_runs(db, _t(user), status_filter)


@router.get("/readiness", response_model=s.Readiness, status_code=status.HTTP_200_OK)
def readiness(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    """What the "Create with AI" form may offer, from real data (SPEC-FE-046 amendment)."""
    return svc.readiness(db, _t(user))


@router.get("/{run_id}", response_model=s.AICampaignRunRead, status_code=status.HTTP_200_OK)
def read(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    return svc.read_run(db, _t(user), run_id)


@router.post("/{run_id}/answer", response_model=s.AICampaignRunRead, status_code=status.HTTP_202_ACCEPTED)
def answer(run_id: str, payload: s.AnswerRequest, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.answer(db, _t(user), str(user.id), run_id, payload)


@router.post("/{run_id}/retry", response_model=s.AICampaignRunRead, status_code=status.HTTP_202_ACCEPTED)
def retry(run_id: str, payload: s.RetryRequest, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.retry(db, _t(user), str(user.id), run_id, payload)


@router.post("/{run_id}/cancel", response_model=s.AICampaignRunRead, status_code=status.HTTP_200_OK)
def cancel(run_id: str, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.cancel(db, _t(user), str(user.id), run_id)


@router.post("/{run_id}/regenerate", response_model=s.AICampaignRunRead, status_code=status.HTTP_200_OK)
def regenerate(run_id: str, payload: s.RegenerateRequest, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.regenerate(db, _t(user), str(user.id), run_id, payload)


@router.post("/{run_id}/publish", response_model=s.AICampaignRunRead, status_code=status.HTTP_200_OK)
def publish(run_id: str, payload: s.PublishRequest, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.publish(db, _t(user), str(user.id), user.role == "owner", run_id, payload)
