"""Event dispatcher: fans a live event out to matching enabled workflows (SPEC-BE-060).

Only the current version of a workflow chain can be enabled (SPEC-BE-049
disables the superseded row), so filtering on `enabled` selects current rows.
Trigger-config matching per type:
- inventory_low: fires when `previous available > threshold >= available`
  (crossing only; staying low doesn't fire again).
- order_placed: min_total (major units) when set.
- ad_threshold_crossed: metric below/above value.
- schedule_cron / manual_owner_command: always (the scheduler / caller chose it).
"""
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.models.workflow import Workflow
from app.workflow_engine.engine import run_workflow

logger = structlog.get_logger(__name__)


def matches(workflow: Workflow, event_type: str, payload: dict[str, Any]) -> bool:
    config = workflow.trigger_config or {}
    try:
        if event_type == "inventory_low":
            threshold = float(config["threshold"])
            before = payload.get("_previous_available")
            after = (payload.get("inventory") or {}).get("available")
            return before is not None and after is not None and before > threshold >= after
        if event_type == "order_placed":
            minimum = config.get("min_total")
            total = float((payload.get("order") or {}).get("total") or 0)
            return minimum in (None, "") or total >= float(str(minimum))
        if event_type == "ad_threshold_crossed":
            value = (payload.get("campaign") or {}).get(str(config.get("metric")))
            if value is None:
                return False
            limit = float(config["value"])
            return value < limit if config.get("operator") == "below" else value > limit
    except (KeyError, TypeError, ValueError):
        return False
    return True


def dispatch_event(
    db: Session, tenant_id: str, event_type: str, payload: dict[str, Any]
) -> list[dict[str, Any]]:
    workflows = (
        db.query(Workflow)
        .filter(
            Workflow.tenant_id == tenant_id,
            Workflow.trigger_type == event_type,
            Workflow.is_active.is_(True),
        )
        .order_by(Workflow.created_at, Workflow.id)
        .all()
    )
    context = {k: v for k, v in payload.items() if not k.startswith("_previous")}
    runs = []
    for workflow in workflows:
        if not matches(workflow, event_type, payload):
            continue
        run = run_workflow(db, workflow, context)
        if run:
            runs.append(run)
    logger.info("workflow_event_dispatched", tenant_id=tenant_id, trigger=event_type, runs=len(runs))
    return runs


def fire(db: Session, tenant_id: str, event_type: str, payload: dict[str, Any]) -> None:
    """Dispatch after the caller's commit, on the scheduler (or inline when the
    scheduler isn't running)."""
    from app.services.scheduler_service import run_soon

    run_soon(dispatch_event, str(tenant_id), event_type, payload, db=db, name=f"workflow:{event_type}")
