"""Saved workflows list (SPEC-BE-014), detail + dry-run test run (SPEC-BE-034),
create / versioned edit / enable / versions / restore (SPEC-BE-049)."""
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import column, func, insert, table, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models.user import User
from app.models.workflow import Workflow, WorkflowRun
from app.schemas.workflow import WorkflowSave

logger = structlog.get_logger(__name__)


def _status_label(enabled: bool) -> str:
    # Status mapping (SPEC-BE-014): display label for the existing boolean
    # workflows.enabled column (model attribute `is_active`) - True ->
    # "Enabled", False -> "Paused". No stored status value is added.
    return "Enabled" if enabled else "Paused"


def _actions_count(actions: Any) -> int:
    # Actions count = length of the workflow's own stored workflows.actions
    # jsonb array (default '[]'). A non-array value counts as 0 rather than
    # e.g. the number of keys in an object.
    return len(actions) if isinstance(actions, list) else 0


def _chains(workflows: list[Workflow]) -> dict[str, list[str]]:
    """{current workflow id: [its id, previous id, ...]} (SPEC-BE-049).
    A workflow some other row names as previous_version_id is superseded."""
    by_id = {str(w.id): w for w in workflows}
    superseded = {str(w.previous_version_id) for w in workflows if w.previous_version_id}
    chains: dict[str, list[str]] = {}
    for wid in by_id:
        if wid in superseded:
            continue
        chain, cur = [], by_id.get(wid)
        while cur is not None and str(cur.id) not in chain:
            chain.append(str(cur.id))
            cur = by_id.get(str(cur.previous_version_id)) if cur.previous_version_id else None
        chains[wid] = chain
    return chains


def list_workflows(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    all_rows = (
        db.query(Workflow)
        .filter(Workflow.tenant_id == tenant_id)
        .order_by(Workflow.updated_at.desc(), Workflow.id)
        .all()
    )
    # Only the current version of each chain is listed (SPEC-BE-049).
    chains = _chains(all_rows)
    workflows = [w for w in all_rows if str(w.id) in chains]

    # Runs (7d) = workflow_runs rows whose `started_at` (the run's start
    # timestamp, TIMESTAMPTZ) is within [now - 7 days, now] in UTC, summed over
    # every version in the chain. Runs that never started (started_at IS NULL)
    # are not counted. workflows.run_count is an all-time counter, not used.
    now = datetime.now(timezone.utc)
    runs_7d: dict[str, int] = {
        str(workflow_id): count
        for workflow_id, count in (
            db.query(WorkflowRun.workflow_id, func.count(WorkflowRun.id))
            .filter(
                WorkflowRun.tenant_id == tenant_id,
                WorkflowRun.started_at >= now - timedelta(days=7),
                WorkflowRun.started_at <= now,
            )
            .group_by(WorkflowRun.workflow_id)
            .all()
        )
    }

    logger.info("workflows_listed", tenant_id=tenant_id, count=len(workflows))
    return [
        {
            "id": str(w.id),
            "name": w.name,
            "trigger_type": w.trigger_type,
            "actions_count": _actions_count(w.actions),
            "runs_7d": sum(runs_7d.get(v, 0) for v in chains[str(w.id)]),
            "status": _status_label(w.is_active),
        }
        for w in workflows
    ]


def _is_current(db: Session, tenant_id: str, workflow_id: str) -> bool:
    return (
        db.query(Workflow.id)
        .filter(Workflow.tenant_id == tenant_id, Workflow.previous_version_id == workflow_id)
        .first()
        is None
    )


def get_workflow(db: Session, tenant_id: str, workflow_id: str) -> dict[str, Any]:
    """One workflow's raw structure (Workflow Builder canvas). Another tenant's -> 404."""
    workflow = _get_workflow_row(db, tenant_id, workflow_id)
    return _detail(db, tenant_id, workflow)


def _detail(db: Session, tenant_id: str, workflow: Workflow) -> dict[str, Any]:
    return {
        "id": str(workflow.id),
        "name": workflow.name,
        "trigger_type": workflow.trigger_type,
        "trigger_config": workflow.trigger_config if isinstance(workflow.trigger_config, dict) else {},
        "condition_dsl": workflow.condition_dsl or None,
        "actions": workflow.actions if isinstance(workflow.actions, list) else [],
        "status": _status_label(workflow.is_active),
        "description": workflow.description,
        "version": workflow.version,
        "is_current": _is_current(db, tenant_id, str(workflow.id)),
    }


# ---------------------------------------------------------------------------
# Create / edit (versioned) / enable / versions / restore (SPEC-BE-049)
# ---------------------------------------------------------------------------
# Saving an edit inserts a NEW row (version + 1, previous_version_id = old id)
# and disables the old one, so workflow_runs keep pointing at the exact version
# that ran. The editor's forms come from WORKFLOW_CATALOG below.
#
# Action types: the dry-run Test Run's eight simulated types (the live
# workflow_action_type values it supports). The legacy workflow_engine
# ACTION_REGISTRY only holds "log"/"notify" and is not what runs here.
#
# Condition grammar (condition_dsl has none defined anywhere, so one is set
# here and validated on save; the dry-run still treats conditions as passed):
#   clause ("AND" clause)*   ;   clause = <field> <op> <value>
#   field: letters/digits/_ and dots, e.g. order.total
#   op:    == != > >= < <= contains
#   value: a number, true/false, or text (optionally "quoted")
_TRIGGER_FIELDS: dict[str, list[dict[str, Any]]] = {
    "product_created": [],
    "product_updated": [],
    "inventory_low": [{"key": "threshold", "label": "Stock at or below", "kind": "number", "required": True}],
    "order_placed": [{"key": "min_total", "label": "Only orders of at least (major units)", "kind": "number", "required": False}],
    "order_fulfilled": [],
    "order_refunded": [],
    "order_abandoned_cart": [{"key": "after_minutes", "label": "Minutes after abandonment", "kind": "number", "required": True}],
    "message_received": [{"key": "channel", "label": "Channel", "kind": "select", "required": False, "options": ["any", "whatsapp", "messenger", "instagram", "facebook", "email", "sms", "web", "tiktok"]}],
    "schedule_cron": [{"key": "cron", "label": "Schedule (cron)", "kind": "text", "required": True, "help": "e.g. 0 9 * * 1 = every Monday 09:00"}],
    "ad_threshold_crossed": [
        {"key": "metric", "label": "Metric", "kind": "select", "required": True, "options": ["roas", "ctr", "cpc", "daily_spend"]},
        {"key": "operator", "label": "When", "kind": "select", "required": True, "options": ["below", "above"]},
        {"key": "value", "label": "Value", "kind": "number", "required": True},
    ],
    "content_published": [],
    "manual_owner_command": [],
}
_TRIGGER_LABELS = {
    "product_created": "Product created", "product_updated": "Product updated", "inventory_low": "Inventory low",
    "order_placed": "Order placed", "order_fulfilled": "Order fulfilled", "order_refunded": "Order refunded",
    "order_abandoned_cart": "Cart abandoned", "message_received": "Message received", "schedule_cron": "On a schedule",
    "ad_threshold_crossed": "Ad metric crosses a threshold", "content_published": "Content published",
    "manual_owner_command": "Run manually",
}
_CHANNEL_OPTS = ["whatsapp", "messenger", "instagram", "facebook", "email", "sms", "web", "tiktok"]
_ACTION_FIELDS: dict[str, tuple[str, list[dict[str, Any]]]] = {
    "generate_content": ("Generate content (AI)", [
        {"key": "channel", "label": "Channel", "kind": "select", "required": True, "options": _CHANNEL_OPTS},
        {"key": "brief", "label": "Brief", "kind": "text", "required": True},
    ]),
    "schedule_post": ("Schedule a post", [
        {"key": "channel", "label": "Channel", "kind": "select", "required": True, "options": _CHANNEL_OPTS},
        {"key": "delay_minutes", "label": "Delay (minutes)", "kind": "number", "required": False},
    ]),
    "launch_ad": ("Launch an ad", [
        {"key": "daily_budget", "label": "Daily budget (major units)", "kind": "number", "required": True},
        {"key": "duration_days", "label": "Duration (days)", "kind": "number", "required": True},
    ]),
    "adjust_budget": ("Adjust ad budget", [
        {"key": "change_pct", "label": "Change (%)", "kind": "number", "required": True, "help": "e.g. -50 to halve, 0 pauses spend growth"},
    ]),
    "send_message": ("Send a message", [
        {"key": "channel", "label": "Channel", "kind": "select", "required": True, "options": _CHANNEL_OPTS},
        {"key": "text", "label": "Message", "kind": "text", "required": True},
    ]),
    "create_task": ("Create a task", [
        {"key": "title", "label": "Task title", "kind": "text", "required": True},
        {"key": "assignee_role", "label": "Assign to", "kind": "select", "required": False, "options": ["owner", "manager", "operator"]},
    ]),
    "notify_owner": ("Notify the owner", [
        {"key": "message", "label": "Message", "kind": "text", "required": True},
    ]),
    "call_webhook": ("Call a webhook", [
        {"key": "url", "label": "URL (https)", "kind": "url", "required": True},
    ]),
}
CONDITION_HELP = (
    "Optional. One or more clauses joined by AND: <field> <operator> <value>. "
    "Operators: == != > >= < <= contains. Values: numbers, true/false, or text."
)
CONDITION_EXAMPLES = ["order.total >= 5000", "customer.tags contains vip AND order.channel == whatsapp"]
_CLAUSE = re.compile(r'^\s*([A-Za-z_][\w.]*)\s*(==|!=|>=|<=|>|<|contains)\s*(.+?)\s*$')


def catalog() -> dict[str, Any]:
    from app.workflow_engine import triggers

    def fields(defs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{"options": [], "help": "", **d} for d in defs]

    return {
        # Triggers without a live source (SPEC-BE-060) are labeled "manual test only".
        "triggers": [
            {
                "type": t,
                "label": _TRIGGER_LABELS[t] + ("" if triggers.is_live(t) else " (manual test only)"),
                "fields": fields(f),
            }
            for t, f in _TRIGGER_FIELDS.items()
        ],
        "actions": [{"type": t, "label": label, "fields": fields(f)} for t, (label, f) in _ACTION_FIELDS.items()],
        "condition_help": CONDITION_HELP,
        "condition_examples": CONDITION_EXAMPLES,
    }


def parse_condition(dsl: str | None) -> list[tuple[str, str, str]]:
    """Validate the condition text; returns the clauses. Raises AppError(422)."""
    if not dsl or not dsl.strip():
        return []
    clauses = []
    for raw in re.split(r"\s+AND\s+", dsl.strip(), flags=re.IGNORECASE):
        m = _CLAUSE.match(raw)
        if not m:
            raise AppError(f"Can't read condition “{raw.strip()}”. Use: <field> <operator> <value>, e.g. order.total >= 5000.", 422)
        clauses.append((m.group(1), m.group(2), m.group(3).strip('"')))
    return clauses


def _validate_fields(defs: list[dict[str, Any]], values: dict[str, Any], what: str) -> dict[str, Any]:
    known = {d["key"]: d for d in defs}
    unknown = sorted(set(values) - set(known))
    if unknown:
        raise AppError(f"Unknown {what} field(s): {', '.join(unknown)}.", 422)
    clean: dict[str, Any] = {}
    for key, d in known.items():
        value = values.get(key)
        if value in (None, ""):
            if d["required"]:
                raise AppError(f"{what.capitalize()}: “{d['label']}” is required.", 422)
            continue
        if d["kind"] == "number":
            try:
                value = float(str(value))
            except (TypeError, ValueError):
                raise AppError(f"{what.capitalize()}: “{d['label']}” must be a number.", 422) from None
            value = int(value) if value.is_integer() else value
        elif d["kind"] == "select" and value not in d.get("options", []):
            raise AppError(f"{what.capitalize()}: “{d['label']}” must be one of {', '.join(d['options'])}.", 422)
        elif d["kind"] == "url" and not str(value).startswith("https://"):
            raise AppError(f"{what.capitalize()}: “{d['label']}” must start with https://.", 422)
        elif d["kind"] in ("text", "url"):
            value = str(value).strip()[:2000]
        clean[key] = value
    return clean


def _validated(payload: WorkflowSave) -> dict[str, Any]:
    if payload.trigger_type not in _TRIGGER_FIELDS:
        raise AppError(f"Unknown trigger type {payload.trigger_type!r}.", 422)
    trigger_config = _validate_fields(_TRIGGER_FIELDS[payload.trigger_type], payload.trigger_config, "trigger")
    actions = []
    for index, action in enumerate(payload.actions, start=1):
        if action.type not in _ACTION_FIELDS:
            raise AppError(f"Step {index}: unknown action type {action.type!r}.", 422)
        params = _validate_fields(_ACTION_FIELDS[action.type][1], action.params, f"step {index}")
        if action.type == "call_webhook" and params.get("url"):
            # SPEC-BE-071 F12: the same public-https guard the run uses, at save.
            from app.integrations import verify

            try:
                verify._public_https_base(str(params["url"]))
            except verify.VerifyError as exc:
                raise AppError(f"Step {index}: {exc}", 422) from None
        # Stored flat, as the seeded workflows and the dry-run expect.
        actions.append({"type": action.type, **params})
    parse_condition(payload.condition_dsl)
    return {
        "name": payload.name,
        "description": (payload.description or "").strip() or None,
        "trigger_type": payload.trigger_type,
        "trigger_config": trigger_config,
        "condition_dsl": (payload.condition_dsl or "").strip() or None,
        "actions": actions,
    }


def _audit(db: Session, tenant_id: str, actor: str, action: str, w: Workflow, extra: dict[str, Any] | None = None) -> None:
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor,
        action=action,
        resource_type="workflow",
        resource_id=str(w.id),
        metadata={"name": w.name, "version": w.version, **(extra or {})},
    )


def create_workflow(db: Session, tenant_id: str, actor: str, payload: WorkflowSave) -> dict[str, Any]:
    data = _validated(payload)
    workflow = Workflow(tenant_id=tenant_id, version=1, is_active=payload.enabled, created_by=actor, **data)
    db.add(workflow)
    db.flush()
    _audit(db, tenant_id, actor, "workflow.create", workflow)
    db.refresh(workflow)
    return _detail(db, tenant_id, workflow)


def _require_current(db: Session, tenant_id: str, workflow_id: str) -> Workflow:
    workflow = _get_workflow_row(db, tenant_id, workflow_id)
    if not _is_current(db, tenant_id, str(workflow.id)):
        raise ConflictError("This is an older version; edit the current version instead.")
    return workflow


def _new_version(db: Session, tenant_id: str, actor: str, current: Workflow, data: dict[str, Any]) -> Workflow:
    new = Workflow(
        tenant_id=tenant_id,
        version=current.version + 1,
        previous_version_id=str(current.id),
        is_active=current.is_active,
        created_by=actor,
        **data,
    )
    current.is_active = False
    db.add(new)
    db.flush()
    return new


def update_workflow(db: Session, tenant_id: str, actor: str, workflow_id: str, payload: WorkflowSave) -> dict[str, Any]:
    current = _require_current(db, tenant_id, workflow_id)
    data = _validated(payload)
    enabled = payload.enabled if "enabled" in payload.model_fields_set else current.is_active
    new = _new_version(db, tenant_id, actor, current, data)
    new.is_active = enabled
    _audit(db, tenant_id, actor, "workflow.update", new, {"previous_version_id": str(current.id)})
    db.refresh(new)
    return _detail(db, tenant_id, new)


def set_enabled(db: Session, tenant_id: str, actor: str, workflow_id: str, enabled: bool) -> dict[str, Any]:
    workflow = _require_current(db, tenant_id, workflow_id)
    workflow.is_active = enabled
    _audit(db, tenant_id, actor, "workflow.enable" if enabled else "workflow.disable", workflow)
    db.refresh(workflow)
    return _detail(db, tenant_id, workflow)


def _chain_for(db: Session, tenant_id: str, workflow_id: str) -> tuple[list[Workflow], str]:
    rows = db.query(Workflow).filter(Workflow.tenant_id == tenant_id).all()
    target = _get_workflow_row(db, tenant_id, workflow_id)
    for head, chain in _chains(rows).items():
        if str(target.id) in chain:
            by_id = {str(w.id): w for w in rows}
            return [by_id[i] for i in chain], head
    return [target], str(target.id)


def list_versions(db: Session, tenant_id: str, workflow_id: str) -> list[dict[str, Any]]:
    chain, head = _chain_for(db, tenant_id, workflow_id)
    authors = dict(
        db.query(User.id, func.concat_ws(" ", User.first_name, User.last_name))
        .filter(User.id.in_([w.created_by for w in chain if w.created_by]))
        .all()
    ) if any(w.created_by for w in chain) else {}
    return [
        {
            "id": str(w.id),
            "version": w.version,
            "created_at": w.created_at.astimezone(timezone.utc),
            "created_by_name": (authors.get(w.created_by) or "").strip() or None if w.created_by else None,
            "name": w.name,
            "trigger_type": w.trigger_type,
            "action_count": _actions_count(w.actions),
            "enabled": w.is_active,
            "is_current": str(w.id) == head,
        }
        for w in chain
    ]


def restore_version(db: Session, tenant_id: str, actor: str, workflow_id: str, version_id: str) -> dict[str, Any]:
    chain, head = _chain_for(db, tenant_id, workflow_id)
    old = next((w for w in chain if str(w.id) == version_id), None)
    if old is None:
        raise NotFoundError("Version not found in this workflow's history.")
    current = next(w for w in chain if str(w.id) == head)
    data = {
        "name": old.name,
        "description": old.description,
        "trigger_type": old.trigger_type,
        "trigger_config": dict(old.trigger_config or {}),
        "condition_dsl": old.condition_dsl,
        "actions": list(old.actions or []),
    }
    new = _new_version(db, tenant_id, actor, current, data)
    _audit(db, tenant_id, actor, "workflow.restore", new, {"restored_version": old.version})
    db.refresh(new)
    return _detail(db, tenant_id, new)


def _get_workflow_row(db: Session, tenant_id: str, workflow_id: str) -> Workflow:
    # Same convention as the rest of the codebase: another tenant's workflow (or a malformed
    # id) is indistinguishable from a missing one -> 404, never 403.
    try:
        uuid.UUID(workflow_id)
    except ValueError as exc:
        raise NotFoundError("Workflow not found.") from exc
    workflow = (
        db.query(Workflow)
        .filter(Workflow.id == workflow_id, Workflow.tenant_id == tenant_id)
        .first()
    )
    if workflow is None:
        raise NotFoundError("Workflow not found.")
    return workflow


# ---------------------------------------------------------------------------
# Test Run - dry-run execution (SPEC-BE-034). Reads the workflow, writes one workflow_runs
# row and one action_executions row per processed action, and nothing else: no external
# call, no other domain's table, no audit_log row (the run rows are the record).
#
# Live-schema deviations from the spec's literal values (the spec's strings are not valid
# enum values in the live database):
#   - workflow_runs.triggered_by is the actor_type enum (human/ai/system/webhook), so a test
#     run is 'human' with triggered_by_id = the caller; the spec's "manual_test" marker is
#     recorded in the run's output as {"mode": "manual_test", "dry_run": true}.
#   - run_status has no 'completed' or 'simulated': a finished run is 'succeeded'/'failed';
#     each simulated action is 'succeeded' with output {"simulated": true, ...}.
#   - workflow_version (the workflow's `version`) and correlation_id (one new uuid shared by
#     the run and its action rows) are NOT NULL in the live tables.
# Written through table() constructs, as orchestrator_service does for approval_queue: the
# WorkflowRun / ActionExecution models don't map these live columns, and the (unused)
# workflow_engine still depends on the old ActionExecution attributes.
# ---------------------------------------------------------------------------
# The jsonb columns need their type so psycopg2 can bind Python dicts.
_workflow_runs = table(
    "workflow_runs",
    column("id"), column("tenant_id"), column("workflow_id"), column("workflow_version"),
    column("triggered_by"), column("triggered_by_id"), column("input", JSONB),
    column("output", JSONB), column("status"), column("started_at"), column("finished_at"),
    column("error_message"), column("correlation_id"),
)
_action_executions = table(
    "action_executions",
    column("tenant_id"), column("workflow_run_id"), column("action_index"), column("action_type"),
    column("input", JSONB), column("output", JSONB), column("status"), column("attempts"),
    column("started_at"), column("finished_at"), column("correlation_id"),
)
# The eight action types the spec documents. The live workflow_action_type enum also has
# update_product and adjust_pricing; per the spec they are treated as unrecognized (the run
# fails at that action) until a spec defines their dry-run behavior.
DRY_RUN_ACTION_TYPES = (
    "generate_content", "schedule_post", "launch_ad", "adjust_budget",
    "send_message", "create_task", "notify_owner", "call_webhook",
)
SIMULATED_OUTPUT = {"simulated": True, "message": "Dry run - no external call made"}


def test_run_workflow(
    db: Session, tenant_id: str, user_id: str, workflow_id: str, run_input: dict[str, Any] | None
) -> dict[str, Any]:
    workflow = _get_workflow_row(db, tenant_id, workflow_id)
    run_input = run_input or {}
    correlation_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    run_id = db.execute(
        insert(_workflow_runs)
        .values(
            tenant_id=tenant_id,
            workflow_id=str(workflow.id),
            workflow_version=workflow.version,
            triggered_by="human",
            triggered_by_id=user_id,
            input=run_input,
            output={"mode": "manual_test", "dry_run": True},
            status="running",
            started_at=started,
            correlation_id=correlation_id,
        )
        .returning(_workflow_runs.c.id)
    ).scalar_one()

    # Condition placeholder: condition_dsl has no defined grammar anywhere, so it is not parsed
    # or evaluated - every test run treats the condition as passed, pending a rule-engine spec.

    executions: list[dict[str, Any]] = []
    error: str | None = None
    actions = workflow.actions if isinstance(workflow.actions, list) else []
    for index, action in enumerate(actions):
        action_type = action.get("type") if isinstance(action, dict) else None
        if action_type not in DRY_RUN_ACTION_TYPES:
            # Stop at the first missing/unrecognized type: no row for it or anything after.
            error = f"Unrecognized action type {action_type!r} at action_index {index}."
            break
        # Input = shallow merge of the action's stored config with the run input; run input
        # keys win on conflict ({**config, **run_input}).
        config = {k: v for k, v in action.items() if k != "type"}
        now = datetime.now(timezone.utc)
        db.execute(
            insert(_action_executions).values(
                tenant_id=tenant_id,
                workflow_run_id=run_id,
                action_index=index,
                action_type=action_type,
                input={**config, **run_input},
                output=SIMULATED_OUTPUT,
                status="succeeded",
                attempts=1,
                started_at=now,
                finished_at=now,
                correlation_id=correlation_id,
            )
        )
        executions.append(
            {"action_index": index, "type": action_type, "status": "succeeded", "output": SIMULATED_OUTPUT}
        )

    finished = datetime.now(timezone.utc)
    status = "failed" if error else "succeeded"
    db.execute(
        update(_workflow_runs)
        .where(_workflow_runs.c.id == run_id, _workflow_runs.c.tenant_id == tenant_id)
        .values(status=status, finished_at=finished, error_message=error)
    )
    db.commit()
    logger.info(
        "workflow_test_run", tenant_id=tenant_id, workflow_id=workflow_id, status=status,
        actions=len(executions),
    )
    return {
        "workflow_run": {
            "id": str(run_id), "status": status, "started_at": started,
            "finished_at": finished, "error": error,
        },
        "action_executions": executions,
    }


# ---------------------------------------------------------------------------
# Command Chat + live runs (SPEC-BE-060)
# ---------------------------------------------------------------------------
def _action_phrase(action: dict[str, Any]) -> str:
    kind = action.get("type")
    if kind == "notify_owner":
        return f"notify the owner (“{action.get('message', '')}”)"
    if kind == "create_task":
        return f"create a task “{action.get('title', '')}” for {action.get('assignee_role') or 'manager'}"
    label = _ACTION_FIELDS.get(str(kind), (str(kind),))[0]
    return label[0].lower() + label[1:] if label else str(kind)


def describe_workflow(db: Session, tenant_id: str, workflow_id: str) -> dict[str, Any]:
    """A readable one-line summary plus 7-day run stats, for chat inspect."""
    from app.workflow_engine import triggers

    workflow = _get_workflow_row(db, tenant_id, workflow_id)
    detail = _detail(db, tenant_id, workflow)
    when = triggers.describe(workflow.trigger_type, detail["trigger_config"])
    condition = f" and **{workflow.condition_dsl}**" if workflow.condition_dsl else ""
    steps = ", ".join(_action_phrase(a) for a in detail["actions"] if isinstance(a, dict))
    since = datetime.now(timezone.utc) - timedelta(days=7)
    runs = db.execute(
        _workflow_runs.select()
        .with_only_columns(_workflow_runs.c.status, _workflow_runs.c.started_at)
        .where(
            _workflow_runs.c.tenant_id == tenant_id,
            _workflow_runs.c.workflow_id == str(workflow.id),
            _workflow_runs.c.started_at >= since,
        )
        .order_by(_workflow_runs.c.started_at.desc())
    ).all()
    live = "" if triggers.is_live(workflow.trigger_type) else " (this trigger runs in manual tests only)"
    summary = (
        f"“{workflow.name}” ({detail['status']}, v{workflow.version}): when **{when}**{condition} → {steps}.{live} "
        f"{len(runs)} run(s) in the last 7 days" + (f", last {runs[0].status}." if runs else ".")
    )
    return {**detail, "summary": summary, "runs_7d": len(runs), "last_run_status": runs[0].status if runs else None}


def run_manual(db: Session, tenant_id: str, actor: str, workflow_id: str, run_input: dict[str, Any]) -> dict[str, Any]:
    """POST /workflows/{id}/run and chat run_workflow: one live run now (the
    condition is evaluated against {"input": ...})."""
    from app.workflow_engine.engine import run_workflow

    workflow = _require_current(db, tenant_id, workflow_id)
    run = run_workflow(db, workflow, {"input": run_input or {}}, triggered_by="human", triggered_by_id=actor)
    if run is None:
        raise ConflictError("A workflow can't start another workflow run.")
    return run


# Condition fields a chat-made workflow may use must be ones its trigger
# provides (workflow_engine.triggers). Returns [(path, question)] - fixed
# question text only; never the LLM's words.
_CLAUSE_FIELD = re.compile(r"^\s*([A-Za-z_][\w.]*)")
BEST_SELLER_FIELDS = {"product.units_sold_30d", "product.revenue_30d_cents"}


def chat_validation_issues(payload: WorkflowSave) -> list[tuple[str, str]]:
    from app.workflow_engine import triggers

    issues: list[tuple[str, str]] = []
    try:
        _validated(payload)
    except AppError as exc:
        detail = str(exc.detail or "")
        if "Stock at or below" in detail:
            issues.append(("trigger_config.threshold", "What stock level counts as low (the workflow fires at or below it)?"))
        elif "Can't read condition" in detail:
            issues.append(("condition_dsl", "I couldn't express that condition. Which field and value should it check (for example: units sold in 30 days at least 20)?"))
        elif "unknown action type" in detail.lower():
            issues.append(("actions", "Which of these should the workflow do: notify the owner, create a task, call a webhook, generate content, or queue an ad/price change for approval?"))
        elif "Unknown trigger" in detail:
            issues.append(("trigger_type", "What should start the workflow (e.g. low stock, a new order, a schedule)?"))
        else:
            issues.append(("workflow", "Some workflow details are missing or invalid: " + detail))
        return issues
    if payload.condition_dsl:
        for field_path, _op, _value in parse_condition(payload.condition_dsl):
            if not triggers.field_allowed(payload.trigger_type, field_path):
                issues.append((
                    "condition_dsl",
                    f"The condition uses “{field_path}”, which this trigger doesn't provide. Which of these should it check: "
                    + ", ".join(triggers.TRIGGER_CONTEXT_FIELDS.get(payload.trigger_type, ())) + "?",
                ))
    return issues
