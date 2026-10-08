"""Workflow action registry and executors (SPEC-BE-060), plus the notification
and webhook helpers Command Chat's notify_owner / create_task / call_webhook
actions share (SPEC-BE-059).

Stored workflow actions are flat dicts: {"type": ..., **params} (SPEC-BE-049).
Text params may contain {{dotted.path}} placeholders filled from the trigger
context; a missing value becomes "" and is never an error.

What each type does when a live run executes it:
- notify_owner -> one `notifications` row per active owner.
- create_task  -> one `notifications` row (type 'task') per active user of the
                  assignee role (default manager); there is no task table.
- call_webhook -> SSRF-guarded https POST of the context (verify.py's guard).
- generate_content -> an AI creative draft (SPEC-BE-046); nothing is published.
- adjust_pricing, update_product, launch_ad, adjust_budget, send_message,
  schedule_post -> a PENDING approval_queue item (subject_type 'action'); the
  run output says "queued for approval". A workflow never acts on these alone.
- log -> structured log line only.
"""
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import structlog
from sqlalchemy import column, insert, select, table
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

logger = structlog.get_logger(__name__)

ActionFn = Callable[[Session, str, dict[str, Any], dict[str, Any]], dict[str, Any]]
ACTION_REGISTRY: dict[str, ActionFn] = {}

_notifications = table(
    "notifications",
    column("id"),
    column("tenant_id"),
    column("user_id"),
    column("type"),
    column("title"),
    column("body"),
    column("link_url"),
    column("severity"),
    column("metadata", JSONB),
)
_approval_queue = table(
    "approval_queue",
    column("id"),
    column("tenant_id"),
    column("subject_type"),
    column("subject_id"),
    column("title"),
    column("summary"),
    column("payload", JSONB),
    column("requested_by_type"),
    column("decision"),
    column("correlation_id"),
)

# Our assignee roles -> live role_type values that receive the notification.
ROLE_TYPES = {"owner": ("owner",), "manager": ("manager",), "operator": ("operator",)}
_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][\w.]*)\s*\}\}")
QUEUED_TYPES = ("adjust_pricing", "update_product", "launch_ad", "adjust_budget", "send_message", "schedule_post")


def register_action(name: str) -> Callable[[ActionFn], ActionFn]:
    def decorator(func: ActionFn) -> ActionFn:
        ACTION_REGISTRY[name] = func
        return func

    return decorator


def lookup(context: dict[str, Any], dotted: str) -> Any:
    value: Any = context
    for part in dotted.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def render(text: Any, context: dict[str, Any]) -> str:
    def sub(match: "re.Match[str]") -> str:
        value = lookup(context, match.group(1))
        return "" if value is None else str(value)

    return _PLACEHOLDER.sub(sub, str(text or ""))


def notify_role(
    db: Session,
    tenant_id: str,
    role: str,
    kind: str,
    title: str,
    body: str,
    link_url: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    """One notifications row per active user holding `role` in the tenant.
    Flushes only; the caller's transaction commits."""
    from app.models.user import Role, User, UserRole

    user_ids = db.scalars(
        select(User.id)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            User.tenant_id == tenant_id,
            UserRole.tenant_id == tenant_id,
            User.status == "active",
            Role.type.in_(ROLE_TYPES.get(role, (role,))),
        )
        .distinct()
    ).all()
    for user_id in user_ids:
        db.execute(
            insert(_notifications).values(
                tenant_id=tenant_id,
                user_id=user_id,
                type=kind[:50],
                title=title[:255],
                body=body,
                link_url=link_url,
                severity="info",
                metadata={"role": role, **(metadata or {})},
            )
        )
    db.flush()
    return len(user_ids)


def post_webhook(url: str, payload: dict[str, Any]) -> int:
    from app.integrations import verify

    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Webhook URL must start with https://.")
    try:
        verify._require_public_host(parsed.hostname)
    except verify.VerifyError as exc:
        raise ValueError(str(exc)) from None
    with verify.client_factory() as client:
        resp = client.post(url, json=payload)
    return resp.status_code


@register_action("log")
def log_action(db: Session, tenant_id: str, config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    logger.info("workflow_action_log", tenant_id=tenant_id, message=render(config.get("message"), context))
    return {"logged": True}


@register_action("notify_owner")
def notify_owner_action(db: Session, tenant_id: str, config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    message = render(config.get("message"), context)
    count = notify_role(db, tenant_id, "owner", "workflow", "Workflow notice", message, metadata=_meta(context))
    return {"notified": count, "message": message}


@register_action("create_task")
def create_task_action(db: Session, tenant_id: str, config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    role = config.get("assignee_role") or "manager"
    title = render(config.get("title"), context)
    count = notify_role(db, tenant_id, role, "task", title, render(config.get("details"), context), metadata={"assignee_role": role, **_meta(context)})
    return {"task": title, "assignee_role": role, "recipients": count}


@register_action("call_webhook")
def call_webhook_action(db: Session, tenant_id: str, config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    status = post_webhook(str(config.get("url")), {"event": "workflow", "context": _plain(context)})
    if status >= 400:
        raise ValueError(f"Webhook answered HTTP {status}.")
    return {"http_status": status}


@register_action("generate_content")
def generate_content_action(db: Session, tenant_id: str, config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    from app.services import content_service

    sku = lookup(context, "product.sku")
    actor = str(context.get("_actor_user_id") or "")
    asset = content_service.generate_creative_asset(
        db, tenant_id, actor, "awareness", [sku] if sku else [], render(config.get("brief"), context), str(config.get("channel") or "facebook")
    )
    return {"content_asset_id": str(asset["id"]), "status": "draft"}


def _queue(action_type: str) -> ActionFn:
    def run(db: Session, tenant_id: str, config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        workflow_id = context.get("_workflow_id")
        approval_id = db.execute(
            insert(_approval_queue)
            .values(
                tenant_id=tenant_id,
                subject_type="action",
                subject_id=workflow_id,
                title=f"Workflow step: {action_type}"[:255],
                summary=f"Requested by workflow {context.get('_workflow_name', '')}",
                payload={
                    "source": "workflow",
                    "workflow_id": str(workflow_id),
                    "run_id": str(context.get("_run_id")),
                    "action_type": action_type,
                    "module": "marketing" if action_type in ("launch_ad", "adjust_budget", "send_message", "schedule_post") else "ecommerce",
                    "risk": "spend" if action_type in ("launch_ad", "adjust_budget") else "change",
                    "params": {k: render(v, context) if isinstance(v, str) else v for k, v in config.items() if k != "type"},
                },
                requested_by_type="system",
                decision="pending",
                correlation_id=context.get("_correlation_id"),
            )
            .returning(_approval_queue.c.id)
        ).scalar_one()
        return {"queued_for_approval": str(approval_id)}

    return run


for _t in QUEUED_TYPES:
    ACTION_REGISTRY[_t] = _queue(_t)


def _meta(context: dict[str, Any]) -> dict[str, Any]:
    return {"workflow_id": str(context.get("_workflow_id")), "run_id": str(context.get("_run_id"))}


def _plain(context: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in context.items() if not k.startswith("_")}


def execute_action(db: Session, tenant_id: str, action_type: str, config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    handler = ACTION_REGISTRY.get(action_type)
    if handler is None:
        return {"error": f"Unknown action type '{action_type}'"}
    return handler(db, tenant_id, config, context)
