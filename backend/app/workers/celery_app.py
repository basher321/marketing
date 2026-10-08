"""Shared APScheduler instance for the in-process job scheduler.

Named celery_app.py for continuity with SPEC-BE-004's target file list, but
this holds no Celery code — SPEC-BE-001 explicitly scopes message brokers
(Celery/Redis/Kafka) out of this backend in favor of an in-process scheduler.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        settings = get_settings()
        _scheduler = AsyncIOScheduler(timezone=settings.SCHEDULER_TIMEZONE)
    return _scheduler
