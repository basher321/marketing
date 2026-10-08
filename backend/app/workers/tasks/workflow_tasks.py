"""Workflow execution jobs (SPEC-BE-060).

dispatch_cron_workflows runs every minute: each enabled `schedule_cron`
workflow whose cron expression (5 fields, evaluated in the tenant timezone)
had a fire time inside the last minute runs once. Other live triggers are
fired by the code that changes the data (workflow_engine.dispatcher.fire).
"""
from datetime import datetime, timedelta, timezone

import structlog
from apscheduler.triggers.cron import CronTrigger

logger = structlog.get_logger(__name__)


def dispatch_cron_workflows() -> int:
    from app.db.session import SessionLocal
    from app.models.tenant import Tenant
    from app.models.workflow import Workflow
    from app.workflow_engine.engine import run_workflow

    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    ran = 0
    db = SessionLocal()
    try:
        rows = (
            db.query(Workflow, Tenant.timezone)
            .join(Tenant, Tenant.id == Workflow.tenant_id)
            .filter(Workflow.trigger_type == "schedule_cron", Workflow.is_active.is_(True))
            .all()
        )
        for workflow, tz in rows:
            cron = str((workflow.trigger_config or {}).get("cron") or "")
            try:
                trigger = CronTrigger.from_crontab(cron, timezone=tz or "UTC")
            except ValueError:
                logger.warning("workflow_cron_invalid", workflow_id=str(workflow.id))
                continue
            due = trigger.get_next_fire_time(None, now - timedelta(minutes=1))
            if due is not None and now - timedelta(minutes=1) < due <= now:
                run_workflow(db, workflow, {"now": now.isoformat()})
                ran += 1
    finally:
        db.close()
    if ran:
        logger.info("workflow_cron_dispatched", runs=ran)
    return ran
