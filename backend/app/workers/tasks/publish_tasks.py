"""Organic post publishing (SPEC-BE-076): runs every minute.

Due `scheduled` posts are claimed (FOR UPDATE SKIP LOCKED, marked
`publishing` and committed) and sent through the platform adapter; async
platforms are polled on later runs. All rules live in
organic_service.run_due; this module only opens a session.
"""
import structlog

logger = structlog.get_logger(__name__)


def publish_scheduled_post() -> dict[str, int]:
    from app.db.session import SessionLocal
    from app.services.organic_service import run_due

    db = SessionLocal()
    try:
        return run_due(db)
    except Exception:
        db.rollback()
        logger.exception("organic_publish_pass_failed")
        return {}
    finally:
        db.close()
