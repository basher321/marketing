"""Job lists (SPEC-BE-097): every minute, submitted job lists with a job due
(its run_at passed, or nothing running) get their executor started. Rules
live in orchestrator_service.execute_ready_actions."""
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger(__name__)

MAX_LISTS_PER_RUN = 50


def run_due_jobs() -> int:
    from app.db.session import SessionLocal
    from app.models.orchestrator import OrchestratorPlan
    from app.services import job_board_service
    from app.services.orchestrator_service import schedule_execution

    db = SessionLocal()
    started = 0
    try:
        now = datetime.now(timezone.utc)
        plans = (
            db.query(OrchestratorPlan)
            .filter(OrchestratorPlan.template.isnot(None),
                    OrchestratorPlan.status.in_(("submitted", "approved", "partially_approved", "proposed")))
            .order_by(OrchestratorPlan.created_at.asc())
            .limit(500)
            .all()
        )
        for plan in plans:
            actions = plan.actions or []
            if any(a.get("status") == "approved" and job_board_service.due(a, now) for a in actions):
                schedule_execution(db, str(plan.tenant_id), str(plan.id))
                started += 1
                if started >= MAX_LISTS_PER_RUN:
                    break
        return started
    except Exception:
        db.rollback()
        logger.exception("plan_jobs_failed")
        return started
    finally:
        db.close()
