"""/scheduled-posts endpoints."""
from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.scheduled_post import ContentCalendar, ScheduledPostCount
from app.services import scheduler_service

router = APIRouter(prefix="/scheduled-posts", tags=["scheduled-posts"])


# Single source for both the Marketing page "Scheduled Posts" card and the
# Dashboard Marketing engine card's "Scheduled posts" metric (SPEC-BE-010).
@router.get("/count", response_model=ScheduledPostCount, status_code=status.HTTP_200_OK)
def count_pending_posts(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> ScheduledPostCount:
    return ScheduledPostCount(
        pending=scheduler_service.count_pending_posts(db, current_user.tenant_id)
    )


# Marketing page "Content Calendar" (SPEC-BE-038).
@router.get("/calendar", response_model=ContentCalendar, status_code=status.HTTP_200_OK)
def get_content_calendar(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return scheduler_service.get_content_calendar(db, str(current_user.tenant_id))
