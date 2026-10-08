"""Post scheduling logic, plus the APScheduler job-scheduler lifecycle.

Two unrelated responsibilities share this file: count_pending_posts is the
ScheduledPost domain service (used by api/v1/scheduled_posts.py, SPEC-BE-010 -
which names a nonexistent scheduled_post_service.py; this file is where the
domain service already lived); start_scheduler/shutdown_scheduler/
get_scheduler_status control the process-wide APScheduler instance from
app.workers.celery_app. They collide on this filename only because
SPEC-BE-004 named app/services/scheduler_service.py as its target file — see
that spec for context.
"""
import logging
from datetime import date, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.content import ContentAsset
from app.models.scheduled_post import ScheduledPost
from app.models.tenant import Tenant
from app.workers.celery_app import get_scheduler
from app.workers.schedules import JOBS

logger = logging.getLogger(__name__)
post_logger = structlog.get_logger(__name__)

# "Pending" = queued and not yet published (SPEC-BE-010). Of the live
# post_status enum (pending, scheduled, publishing, published, failed,
# cancelled), only `pending` and `scheduled` count. `publishing` (in flight),
# `published`, `failed`, and `cancelled` are excluded. scheduled_at is not
# checked - an overdue pending post still counts.
PENDING_POST_STATUSES = ("pending", "scheduled")


def count_pending_posts(db: Session, tenant_id: str) -> int:
    # Tenancy: scheduled_posts has its own tenant_id column (FK to tenants), so
    # the filter is direct - no join through content_assets or campaigns. The
    # table has no RLS policy, so this filter is the only tenant isolation.
    count = (
        db.query(func.count(ScheduledPost.id))
        .filter(
            ScheduledPost.tenant_id == tenant_id,
            ScheduledPost.status.in_(PENDING_POST_STATUSES),
        )
        .scalar()
    )
    post_logger.info("scheduled_posts_pending_counted", tenant_id=tenant_id, count=count)
    return int(count or 0)


# Marketing "Content Calendar" (SPEC-BE-038). Shown: pending, scheduled, publishing and
# published posts; failed/cancelled are excluded. The week is Monday-Sunday containing "now"
# in the tenant's own timezone (tenants.timezone), computed in Postgres so no local tz
# database is needed; each post lands on its tenant-local scheduled date.
CALENDAR_POST_STATUSES = ("pending", "scheduled", "publishing", "published")


def get_content_calendar(db: Session, tenant_id: str) -> dict[str, Any]:
    tz = db.execute(select(Tenant.timezone).where(Tenant.id == tenant_id)).scalar() or "UTC"
    week_start: date = db.execute(
        select(cast(func.date_trunc("week", func.timezone(tz, func.now())), Date))
    ).scalar_one()
    week_end = week_start + timedelta(days=7)
    local_day = cast(func.timezone(tz, ScheduledPost.scheduled_at), Date)
    rows = db.execute(
        select(
            ScheduledPost.id,
            ScheduledPost.channel,
            ScheduledPost.status,
            ScheduledPost.scheduled_at,
            ContentAsset.format,
            local_day.label("local_day"),
        )
        .join(
            ContentAsset,
            (ContentAsset.id == ScheduledPost.content_asset_id)
            & (ContentAsset.tenant_id == tenant_id),
        )
        .where(
            ScheduledPost.tenant_id == tenant_id,
            ScheduledPost.status.in_(CALENDAR_POST_STATUSES),
            local_day >= week_start,
            local_day < week_end,
        )
        .order_by(ScheduledPost.scheduled_at, ScheduledPost.id)
    ).all()
    days: list[dict[str, Any]] = [
        {"date": week_start + timedelta(days=i), "posts": []} for i in range(7)
    ]
    for r in rows:
        days[(r.local_day - week_start).days]["posts"].append(
            {
                "id": str(r.id),
                "channel": r.channel,
                "format": r.format,
                "status": r.status,
                "scheduled_at": r.scheduled_at.astimezone(timezone.utc),
            }
        )
    post_logger.info("content_calendar_built", tenant_id=tenant_id, posts=len(rows))
    return {"week_start": week_start, "timezone": tz, "days": days}


def start_scheduler() -> None:
    settings = get_settings()
    if not settings.SCHEDULER_ENABLED:
        logger.info("Scheduler disabled (SCHEDULER_ENABLED=false); not starting.")
        return

    scheduler = get_scheduler()
    if scheduler.running:
        logger.info("Scheduler already running; not starting again.")
        return

    for job in JOBS:
        scheduler.add_job(**job, replace_existing=True)
    scheduler.start()
    job_ids = [job.id for job in scheduler.get_jobs()]
    logger.info("Scheduler started with %d job(s): %s", len(job_ids), ", ".join(job_ids))


def shutdown_scheduler() -> None:
    settings = get_settings()
    if not settings.SCHEDULER_ENABLED:
        return

    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down.")


def get_scheduler_status() -> dict[str, Any]:
    settings = get_settings()
    if not settings.SCHEDULER_ENABLED:
        return {"enabled": False, "running": False, "jobs": []}

    scheduler = get_scheduler()
    return {
        "enabled": True,
        "running": scheduler.running,
        "jobs": [job.id for job in scheduler.get_jobs()],
    }


# One-off background jobs (SPEC-BE-059/060): Command Chat plan execution and
# live workflow dispatch run "soon" on the in-process scheduler with their own
# DB session, after the caller's transaction committed. When the scheduler
# isn't running (SCHEDULER_ENABLED=false, scripts) or INLINE_JOBS is set (the
# rolled-back verification transaction), the job runs inline on the caller's
# session instead. A job error is logged and rolled back, never raised to the
# caller (the caller's own work is already committed).
INLINE_JOBS = False


def _run_with_session(job: Any, args: tuple[Any, ...], name: str) -> None:
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        job(db, *args)
    except Exception:
        db.rollback()
        logger.exception("background_job_failed: %s", name)
    finally:
        db.close()


def run_soon(job: Any, *args: Any, db: Session, name: str = "job") -> None:
    scheduler = get_scheduler()
    if INLINE_JOBS or not scheduler.running:
        try:
            job(db, *args)
        except Exception:
            db.rollback()
            logger.exception("inline_job_failed: %s", name)
        return
    scheduler.add_job(_run_with_session, args=[job, args, name], name=name, misfire_grace_time=300)
