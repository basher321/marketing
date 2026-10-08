"""Organic Marketing routes (SPEC-BE-076).

Roles: viewer+ reads; agent+ creates and edits drafts; manager+ approves,
schedules, publishes, cancels, reschedules and retries.
"""
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas import organic as s
from app.services import organic_service as svc

router = APIRouter(prefix="/organic", tags=["organic"])
Agent = Depends(require_permission("agent"))
Manager = Depends(require_permission("manager"))
Viewer = Depends(get_current_user)


def _t(user: User) -> str:
    return str(user.tenant_id)


@router.get("/summary", response_model=s.Summary, status_code=status.HTTP_200_OK)
def summary(db: Session = Depends(get_db), user: User = Viewer) -> dict[str, Any]:
    return svc.summary(db, _t(user))


@router.get("/insights", response_model=s.Insights, status_code=status.HTTP_200_OK)
def insights(days: Literal[30, 60, 90] = 60, db: Session = Depends(get_db), user: User = Viewer) -> dict[str, Any]:
    return svc.insights(db, _t(user), days)


@router.get("/contents", response_model=s.ContentList, status_code=status.HTTP_200_OK)
def list_contents(
    status_: str | None = Query(default=None, alias="status", pattern="^(draft|needs_approval|approved|archived)$"),
    platform: str | None = Query(default=None, pattern="^(facebook|instagram|tiktok|linkedin)$"),
    q: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Viewer,
) -> dict[str, Any]:
    return svc.list_contents(db, _t(user), status_, platform, q, page)


@router.post("/contents", response_model=s.ContentOut, status_code=status.HTTP_201_CREATED)
def create_manual(payload: s.ManualCreate, db: Session = Depends(get_db), user: User = Agent) -> dict[str, Any]:
    return svc.create_manual(db, _t(user), str(user.id), payload)


@router.post("/contents/ai", response_model=s.ContentOut, status_code=status.HTTP_201_CREATED)
def create_ai(payload: s.AICreate, db: Session = Depends(get_db), user: User = Agent) -> dict[str, Any]:
    return svc.create_ai(db, _t(user), str(user.id), payload)


@router.get("/contents/{content_id}", response_model=s.ContentOut, status_code=status.HTTP_200_OK)
def get_content(content_id: str, db: Session = Depends(get_db), user: User = Viewer) -> dict[str, Any]:
    return svc.get_content(db, _t(user), content_id)


@router.patch("/contents/{content_id}", response_model=s.ContentOut, status_code=status.HTTP_200_OK)
def update_content(content_id: str, payload: s.ContentPatch, db: Session = Depends(get_db), user: User = Agent) -> dict[str, Any]:
    return svc.update_content(db, _t(user), str(user.id), content_id, payload)


@router.delete("/contents/{content_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def archive(content_id: str, db: Session = Depends(get_db), user: User = Manager) -> Response:
    svc.archive(db, _t(user), str(user.id), content_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/contents/{content_id}/targets", response_model=s.ContentOut, status_code=status.HTTP_200_OK)
def set_targets(content_id: str, payload: s.TargetsPatch, db: Session = Depends(get_db), user: User = Agent) -> dict[str, Any]:
    return svc.set_targets(db, _t(user), str(user.id), content_id, payload)


@router.post("/contents/{content_id}/approve", response_model=s.ContentOut, status_code=status.HTTP_200_OK)
def approve(content_id: str, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.approve(db, _t(user), str(user.id), content_id)


@router.post("/contents/{content_id}/schedule", response_model=s.ContentOut, status_code=status.HTTP_201_CREATED)
def schedule_bulk(content_id: str, payload: s.BulkSchedule, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.schedule_bulk(db, _t(user), str(user.id), content_id, payload.items)


@router.patch("/versions/{version_id}", response_model=s.ContentOut, status_code=status.HTTP_200_OK)
def update_version(version_id: str, payload: s.VersionPatch, db: Session = Depends(get_db), user: User = Agent) -> dict[str, Any]:
    return svc.update_version(db, _t(user), str(user.id), version_id, payload)


@router.post("/versions/{version_id}/regenerate", response_model=s.ContentOut, status_code=status.HTTP_200_OK)
def regenerate(version_id: str, payload: s.RegenerateIn, db: Session = Depends(get_db), user: User = Agent) -> dict[str, Any]:
    return svc.regenerate(db, _t(user), str(user.id), version_id, list(payload.parts), payload.instruction)


@router.post("/versions/{version_id}/revert", response_model=s.ContentOut, status_code=status.HTTP_200_OK)
def revert(version_id: str, payload: s.RevertIn, db: Session = Depends(get_db), user: User = Agent) -> dict[str, Any]:
    return svc.revert(db, _t(user), str(user.id), version_id, payload.variant_index)


@router.get("/versions/{version_id}/preview", response_model=s.Preview, status_code=status.HTTP_200_OK)
def preview(version_id: str, db: Session = Depends(get_db), user: User = Viewer) -> dict[str, Any]:
    return svc.preview(db, _t(user), version_id)


@router.post("/versions/{version_id}/schedule", response_model=s.PostOut, status_code=status.HTTP_201_CREATED)
def schedule(version_id: str, payload: s.ScheduleIn, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.schedule_version(db, _t(user), str(user.id), version_id, payload.scheduled_at_local, payload.timezone)


@router.post("/versions/{version_id}/publish-now", response_model=s.PostOut, status_code=status.HTTP_202_ACCEPTED)
def publish_now(version_id: str, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.publish_now(db, _t(user), str(user.id), version_id)


@router.post("/posts/{post_id}/cancel", response_model=s.PostOut, status_code=status.HTTP_200_OK)
def cancel(post_id: str, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.cancel(db, _t(user), str(user.id), post_id)


@router.post("/posts/{post_id}/reschedule", response_model=s.PostOut, status_code=status.HTTP_200_OK)
def reschedule(post_id: str, payload: s.ScheduleIn, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.reschedule(db, _t(user), str(user.id), post_id, payload.scheduled_at_local, payload.timezone)


@router.post("/posts/{post_id}/retry", response_model=s.PostOut, status_code=status.HTTP_202_ACCEPTED)
def retry(post_id: str, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.retry(db, _t(user), str(user.id), post_id)


@router.get("/calendar", response_model=s.Calendar, status_code=status.HTTP_200_OK)
def calendar(start: date = Query(alias="from"), end: date = Query(alias="to"), db: Session = Depends(get_db), user: User = Viewer) -> dict[str, Any]:
    return svc.calendar(db, _t(user), start, end)


@router.get("/history", response_model=s.History, status_code=status.HTTP_200_OK)
def history(
    status_: str | None = Query(default=None, alias="status", pattern="^(published|failed|cancelled)$"),
    platform: str | None = Query(default=None, pattern="^(facebook|instagram|tiktok|linkedin)$"),
    page: int = Query(default=1, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Viewer,
) -> dict[str, Any]:
    return svc.history(db, _t(user), status_, platform, page)
