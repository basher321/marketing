"""Generation jobs left behind by a restart (SPEC-BE-077): every minute,
running video jobs not polled for 2 minutes are polled, and queued jobs
older than 2 minutes are started. Rules live in generation_service."""
import structlog

logger = structlog.get_logger(__name__)


def resume_generation_jobs() -> int:
    from app.db.session import SessionLocal
    from app.services.generation_service import resume_stale

    db = SessionLocal()
    try:
        return resume_stale(db)
    except Exception:
        db.rollback()
        logger.exception("generation_resume_failed")
        return 0
    finally:
        db.close()
