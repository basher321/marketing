"""Live workflow executor: trigger context -> condition -> actions (SPEC-BE-060).

Writes the live workflow_runs / action_executions columns (the same Core tables
the SPEC-BE-034 dry run uses), increments workflows.run_count and sets
last_run_at. An action error marks that step and the run failed; the other
steps still run. The run commits on its own (it is called after the triggering
transaction committed, never inside a user's request transaction).

Guards:
- at most MAX_RUNS_PER_HOUR live runs per workflow (excess -> a 'cancelled' run
  with the reason, so it is visible);
- no recursion: a run started while another run is executing in this context
  (e.g. an action that would fire a trigger) is skipped.
"""
import contextvars
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import column, func, insert, select, table, update
from sqlalchemy.orm import Session

from app.models.workflow import Workflow
from app.workflow_engine.actions import execute_action
from app.workflow_engine.conditions import evaluate_all

logger = structlog.get_logger(__name__)

MAX_RUNS_PER_HOUR = 50
_running: contextvars.ContextVar[bool] = contextvars.ContextVar("workflow_running", default=False)


def run_workflow(
    db: Session,
    workflow: Workflow,
    context: dict[str, Any],
    triggered_by: str = "system",
    triggered_by_id: str | None = None,
) -> dict[str, Any] | None:
    from app.services.workflow_service import _action_executions, _workflow_runs, parse_condition

    if _running.get():
        logger.info("workflow_run_skipped_recursion", workflow_id=str(workflow.id))
        return None
    tenant_id = str(workflow.tenant_id)
    now = datetime.now(timezone.utc)
    correlation_id = str(uuid.uuid4())
    recent = db.execute(
        select(func.count())
        .select_from(_workflow_runs)
        .where(
            _workflow_runs.c.tenant_id == tenant_id,
            _workflow_runs.c.workflow_id == str(workflow.id),
            _workflow_runs.c.started_at >= now - timedelta(hours=1),
            _workflow_runs.c.output["mode"].astext == "live",
        )
    ).scalar_one()
    base = {
        "tenant_id": tenant_id,
        "workflow_id": str(workflow.id),
        "workflow_version": workflow.version,
        "triggered_by": triggered_by,
        "triggered_by_id": triggered_by_id,
        "input": _plain(context),
        "started_at": now,
        "correlation_id": correlation_id,
    }
    if recent >= MAX_RUNS_PER_HOUR:
        run_id = db.execute(
            insert(_workflow_runs)
            .values(
                **base,
                status="cancelled",
                finished_at=now,
                output={"mode": "live", "result": "rate_limited"},
                error_message=f"More than {MAX_RUNS_PER_HOUR} runs in the last hour.",
            )
            .returning(_workflow_runs.c.id)
        ).scalar_one()
        db.commit()
        return {"id": str(run_id), "status": "cancelled", "output": {"result": "rate_limited"}}

    run_id = db.execute(
        insert(_workflow_runs)
        .values(**base, status="running", output={"mode": "live"})
        .returning(_workflow_runs.c.id)
    ).scalar_one()
    ctx = {
        **context,
        "_workflow_id": str(workflow.id),
        "_workflow_name": workflow.name,
        "_run_id": str(run_id),
        "_correlation_id": correlation_id,
    }

    if not evaluate_all(parse_condition(workflow.condition_dsl), ctx):
        # Condition not met: recorded as a succeeded run with no steps, so the
        # history shows the trigger fired and why nothing happened.
        output: dict[str, Any] = {"mode": "live", "result": "condition_not_met"}
        _finish(db, run_id, tenant_id, "succeeded", output, None, workflow)
        return {"id": str(run_id), "status": "succeeded", "output": output}

    token = _running.set(True)
    failed: list[str] = []

    steps: list[dict[str, Any]] = []
    try:
        for index, action in enumerate(workflow.actions or []):
            action_type = action.get("type") if isinstance(action, dict) else None
            config = {k: v for k, v in (action or {}).items() if k != "type"}
            started = datetime.now(timezone.utc)
            try:
                with db.begin_nested():
                    result = execute_action(db, tenant_id, str(action_type), config, ctx)
                status = "failed" if "error" in result else "succeeded"
            except Exception as exc:  # one failing step never stops the others
                result, status = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}, "failed"
            if status == "failed":
                failed.append(f"step {index + 1}: {result['error']}")
            steps.append({"index": index, "type": action_type, "status": status})
            db.execute(
                insert(_action_executions).values(
                    tenant_id=tenant_id,
                    workflow_run_id=run_id,
                    action_index=index,
                    action_type=action_type,
                    input=config,
                    output=_jsonable(result),
                    status=status,
                    attempts=1,
                    started_at=started,
                    finished_at=datetime.now(timezone.utc),
                    correlation_id=correlation_id,
                )
            )
    finally:
        _running.reset(token)
    status = "failed" if failed else "succeeded"
    output = {"mode": "live", "result": "executed", "steps": steps}
    _finish(db, run_id, tenant_id, status, output, "; ".join(failed) or None, workflow)
    return {"id": str(run_id), "status": status, "output": output}


def _finish(
    db: Session,
    run_id: Any,
    tenant_id: str,
    status: str,
    output: dict[str, Any],
    error: str | None,
    workflow: Workflow,
) -> None:
    from app.core.audit import write_audit_log
    from app.services.workflow_service import _workflow_runs as runs

    now = datetime.now(timezone.utc)
    db.execute(
        update(runs)
        .where(runs.c.id == run_id, runs.c.tenant_id == tenant_id)
        .values(status=status, output=output, finished_at=now, error_message=error)
    )
    # run_count / last_run_at aren't mapped on Workflow; a Core table of the live columns.
    wf = table("workflows", column("id"), column("tenant_id"), column("run_count"), column("last_run_at"))
    db.execute(
        update(wf)
        .where(wf.c.id == str(workflow.id), wf.c.tenant_id == tenant_id)
        .values(run_count=func.coalesce(wf.c.run_count, 0) + 1, last_run_at=now)
    )
    # write_audit_log commits the run, its steps and the audit row together.
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=None,
        action="workflow.run_succeeded" if status == "succeeded" else "workflow.run_failed",
        resource_type="workflow_run",
        resource_id=str(run_id),
        metadata={
            "workflow_id": str(workflow.id),
            "version": workflow.version,
            "result": output.get("result"),
            "error": error,
        },
    )
    logger.info("workflow_run_finished", tenant_id=tenant_id, workflow_id=str(workflow.id), status=status)


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _plain(context: dict[str, Any]) -> dict[str, Any]:
    return _jsonable({k: v for k, v in context.items() if not k.startswith("_")})
