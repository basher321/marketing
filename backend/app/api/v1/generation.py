"""Photo / video generation routes (SPEC-BE-077).

Generate, regenerate, edit and cancel are agent+; approve is manager+.
Starting returns 202: the job runs in the background; poll
GET /organic/generations/{id}.
"""
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas import generation as s
from app.services import generation_service as svc

router = APIRouter(prefix="/organic", tags=["generation"])
Agent = Depends(require_permission("agent"))
Manager = Depends(require_permission("manager"))


def _t(user: User) -> str:
    return str(user.tenant_id)


@router.get("/generation/providers", response_model=s.Readiness, status_code=status.HTTP_200_OK)
def providers(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    return svc.readiness(db, _t(user))


@router.post("/generate/photo", response_model=s.StartResult, status_code=status.HTTP_202_ACCEPTED)
def generate_photo(payload: s.PhotoRequest, db: Session = Depends(get_db), user: User = Agent) -> dict[str, Any]:
    return {"jobs": svc.start_photo(db, _t(user), str(user.id), payload)}


@router.post("/generate/video", response_model=s.StartResult, status_code=status.HTTP_202_ACCEPTED)
def generate_video(payload: s.VideoRequest, db: Session = Depends(get_db), user: User = Agent) -> dict[str, Any]:
    return {"jobs": svc.start_video(db, _t(user), str(user.id), payload)}


@router.get("/generations", response_model=s.JobList, status_code=status.HTTP_200_OK)
def list_jobs(
    kind: str | None = Query(default=None, pattern="^(image|video)$"),
    status_: str | None = Query(default=None, alias="status", pattern="^(queued|running|succeeded|failed|cancelled)$"),
    page: int = Query(default=1, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return svc.list_jobs(db, _t(user), kind, status_, page)


@router.get("/generations/{job_id}", response_model=s.JobOut, status_code=status.HTTP_200_OK)
def get_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    return svc.get_job(db, _t(user), job_id)


@router.post("/generations/{job_id}/regenerate", response_model=s.JobOut, status_code=status.HTTP_202_ACCEPTED)
def regenerate(job_id: str, payload: s.RegenerateRequest, db: Session = Depends(get_db), user: User = Agent) -> dict[str, Any]:
    out = svc.regenerate(db, _t(user), str(user.id), job_id, payload.model_dump(exclude_unset=True))
    return svc.get_job(db, _t(user), out["id"])


@router.post("/generations/{job_id}/edit", response_model=s.JobOut, status_code=status.HTTP_202_ACCEPTED)
def edit(job_id: str, payload: s.EditRequest, db: Session = Depends(get_db), user: User = Agent) -> dict[str, Any]:
    out = svc.edit(db, _t(user), str(user.id), job_id, payload.instruction)
    return svc.get_job(db, _t(user), out["id"])


@router.post("/generations/{job_id}/cancel", response_model=s.JobOut, status_code=status.HTTP_200_OK)
def cancel(job_id: str, db: Session = Depends(get_db), user: User = Agent) -> dict[str, Any]:
    return svc.cancel(db, _t(user), str(user.id), job_id)


@router.post("/generations/{job_id}/approve", response_model=s.JobOut, status_code=status.HTTP_200_OK)
def approve(job_id: str, payload: s.ApproveRequest, db: Session = Depends(get_db), user: User = Manager) -> dict[str, Any]:
    return svc.approve(db, _t(user), str(user.id), job_id, payload.create_content)
