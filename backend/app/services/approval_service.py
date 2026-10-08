"""Per-engine pending approval counts (SPEC-BE-020)."""
from datetime import datetime, timezone
from typing import Any, Literal

import structlog
from sqlalchemy import column, func, select, table
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.approval import ApprovalQueue

logger = structlog.get_logger(__name__)

# approval_queue.payload isn't mapped on ApprovalQueue; read it via Core.
_queue = table(
    "approval_queue", column("id"), column("tenant_id"), column("payload", JSONB), column("decision"), column("subject_type")
)

# Command Chat plan steps (SPEC-BE-059) are 'action' items whose payload names
# the module; they count toward an engine by that module.
MODULE_ENGINE = {"ecommerce": "ecommerce", "shipping": "ecommerce", "marketing": "marketing", "meta": "marketing"}


def _payloads(db: Session, tenant_id: str, ids: list[str]) -> dict[str, dict[str, Any]]:
    if not ids:
        return {}
    rows = db.execute(
        select(_queue.c.id, _queue.c.payload).where(_queue.c.tenant_id == tenant_id, _queue.c.id.in_(ids))
    ).all()
    return {str(i): (p if isinstance(p, dict) else {}) for i, p in rows}


def _plan_step(payload: dict[str, Any]) -> bool:
    return bool(payload.get("plan_id")) and payload.get("risk") in ("change", "spend")


def _step_block_reason(db: Session, tenant_id: str, user_id: str, payload: dict[str, Any], decision: str) -> str | None:
    from app.services import orchestrator_service
    from app.services.auth_service import resolve_app_role

    role = resolve_app_role(db, user_id, tenant_id)
    if decision == "rejected":
        return None if role in ("owner", "admin", "manager") else "Only a manager or the owner can reject this step."
    return orchestrator_service.check_can_decide(db, tenant_id, user_id, role, payload)


def _notify_plans(db: Session, tenant_id: str, user_id: str, payloads: list[dict[str, Any]], decision: str) -> None:
    from app.services import orchestrator_service

    for payload in payloads:
        if _plan_step(payload):
            orchestrator_service.on_approval_decided(db, tenant_id, user_id, payload, decision)

# subject_type -> engine mapping (SPEC-BE-020), over the live
# approval_subject_type enum (plan, action, content, campaign, reply,
# pricing_change):
#   E-Commerce: pricing_change - catalog price changes.
#   Marketing:  campaign - ad campaigns; content - content_assets (channel
#               posts / ad creatives, linked to campaigns via campaign_id).
#   Excluded from both counts:
#     reply        - Customer Service replies; that engine card shows no
#                    "Pending approvals" row.
#     plan, action - generic orchestrator plans/actions whose engine cannot be
#                    told from subject_type alone; excluded rather than
#                    guessed into one engine (e.g. a restock request queued as
#                    an 'action' is not counted as E-Commerce).
ECOMMERCE_SUBJECT_TYPES = ("pricing_change",)
MARKETING_SUBJECT_TYPES = ("campaign", "content")


def get_pending_counts(db: Session, tenant_id: str) -> dict[str, int]:
    # Pending = decision 'pending' (no decision yet). expires_at is not
    # checked: an item past expires_at still counts until its decision is set
    # to 'expired'. An engine with no pending items gets 0.
    rows = (
        db.query(ApprovalQueue.subject_type, func.count(ApprovalQueue.id))
        .filter(
            ApprovalQueue.tenant_id == tenant_id,
            ApprovalQueue.decision == "pending",
            ApprovalQueue.subject_type.in_(ECOMMERCE_SUBJECT_TYPES + MARKETING_SUBJECT_TYPES),
        )
        .group_by(ApprovalQueue.subject_type)
        .all()
    )
    by_type = {subject_type: int(count) for subject_type, count in rows}
    counts = {
        "ecommerce": sum(by_type.get(t, 0) for t in ECOMMERCE_SUBJECT_TYPES),
        "marketing": sum(by_type.get(t, 0) for t in MARKETING_SUBJECT_TYPES),
    }
    module = _queue.c.payload["module"].astext
    # One table, no self-join: joining the mapped approval_queue to this Core
    # table of the same name made Postgres reject the query (DuplicateAlias).
    step_rows = db.execute(
        select(module, func.count())
        .where(_queue.c.tenant_id == tenant_id, _queue.c.decision == "pending", _queue.c.subject_type == "action")
        .group_by(module)
    ).all()
    for mod, count in step_rows:
        engine = MODULE_ENGINE.get(mod or "")
        if engine:
            counts[engine] += int(count)
    logger.info("pending_approval_counts_computed", tenant_id=tenant_id, **counts)
    return counts


# Approve / reject decisions (SPEC-BE-024). Only the decision is recorded -
# no approved action is executed here. An item is decidable only while its
# decision is 'pending'; an item past expires_at is still decidable (it still
# counts as pending in get_pending_counts). Every decided item gets exactly
# one audit_log row via core/audit.write_audit_log(), which commits the
# session itself.
Decision = Literal["approved", "rejected"]


def _decision_result(item: ApprovalQueue) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "subject_type": item.subject_type,
        "subject_id": str(item.subject_id),
        "title": item.title,
        "decision": item.decision,
        "decided_by": str(item.decided_by) if item.decided_by else None,
        "decided_at": item.decided_at.astimezone(timezone.utc) if item.decided_at else None,
        "reason": item.reason,
    }


def _audit_decision(
    db: Session, tenant_id: str, user_id: str, item_id: str, meta: dict[str, Any]
) -> None:
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=user_id,
        action="approval.approve" if meta["decision"] == "approved" else "approval.reject",
        resource_type="approval_queue",
        resource_id=item_id,
        metadata=meta,
    )


# Campaign launch approvals (SPEC-BE-047). A `campaign` item is created when a
# non-owner launches over the tenant's daily ad cap; approving it is the
# owner's sign-off, so only an owner may APPROVE one (anyone manager+ may
# reject). Approving launches the campaign (ad set + ad, status live);
# rejecting returns it to an editable draft. Other subject types still only
# record the decision.
def _require_owner_for_campaign_approval(
    db: Session, tenant_id: str, user_id: str, items: list[ApprovalQueue], decision: str
) -> None:
    if decision != "approved" or not any(i.subject_type == "campaign" for i in items):
        return
    from app.services.auth_service import resolve_app_role

    if resolve_app_role(db, user_id, tenant_id) != "owner":
        raise ForbiddenError("Only the owner can approve a campaign launch.")


def _apply_campaign_decisions(
    db: Session,
    tenant_id: str,
    user_id: str,
    items: list[ApprovalQueue],
    decision: str,
    now: datetime,
) -> None:
    # Imported here: campaign_service is a heavier module (planner, retrieval).
    from app.services import campaign_service

    for item in items:
        if item.subject_type == "campaign":
            campaign_service.apply_approval_decision(
                db, tenant_id, str(item.id), str(item.subject_id), user_id, decision, now
            )


def decide_one(
    db: Session,
    tenant_id: str,
    approval_id: str,
    user_id: str,
    decision: Decision,
    reason: str | None = None,
) -> dict[str, Any]:
    # The row is looked up by id AND tenant_id and locked (SELECT ... FOR
    # UPDATE) so two concurrent decisions cannot both apply. Another tenant's
    # item is indistinguishable from a missing one: 404, never 403. An
    # already-decided item raises 409 and nothing changes. reason is stored
    # on reject only.
    item = (
        db.query(ApprovalQueue)
        .filter(ApprovalQueue.id == approval_id, ApprovalQueue.tenant_id == tenant_id)
        .with_for_update()
        .one_or_none()
    )
    if item is None:
        raise NotFoundError("Approval item not found.")
    if item.decision != "pending":
        raise ConflictError(f"Approval item already decided: {item.decision}.")
    _require_owner_for_campaign_approval(db, tenant_id, user_id, [item], decision)
    payload = _payloads(db, tenant_id, [str(item.id)]).get(str(item.id), {})
    if _plan_step(payload):
        blocked = _step_block_reason(db, tenant_id, user_id, payload, decision)
        if blocked:
            raise ForbiddenError(blocked)

    item.decision = decision
    item.decided_by = user_id
    item.decided_at = datetime.now(timezone.utc)
    item.reason = (reason or None) if decision == "rejected" else None
    _apply_campaign_decisions(db, tenant_id, user_id, [item], decision, item.decided_at)
    meta = {
        "decision": decision,
        "subject_type": item.subject_type,
        "subject_id": str(item.subject_id),
        "reason": item.reason,
    }
    # write_audit_log commits: the decision and its audit row land together.
    _audit_decision(db, tenant_id, user_id, str(item.id), meta)
    logger.info("approval_decided", tenant_id=tenant_id, approval_id=approval_id, decision=decision)
    result = _decision_result(item)
    # After the commit: a Command Chat step moves on (SPEC-BE-059).
    _notify_plans(db, tenant_id, user_id, [payload], decision)
    return result


def decide_group(
    db: Session,
    tenant_id: str,
    subject_id: str,
    user_id: str,
    decision: Decision,
    reason: str | None = None,
) -> dict[str, Any]:
    # Approve-all / reject-all: applies the decision to every still-pending
    # item of this tenant sharing subject_id (locked FOR UPDATE). Items already
    # decided are never selected, so they are left untouched. Zero pending
    # items -> decided_count 0, not an error. One audit_log row per item.
    #
    # Atomicity limit: write_audit_log (core/audit.py) commits on every call,
    # so the first call commits all decisions plus the first audit row and
    # each further audit row is its own commit.
    items = (
        db.query(ApprovalQueue)
        .filter(
            ApprovalQueue.tenant_id == tenant_id,
            ApprovalQueue.subject_id == subject_id,
            ApprovalQueue.decision == "pending",
        )
        .order_by(ApprovalQueue.created_at, ApprovalQueue.id)
        .with_for_update()
        .all()
    )
    now = datetime.now(timezone.utc)
    stored_reason = (reason or None) if decision == "rejected" else None
    # "Approve all I can" (SPEC-BE-059): plan steps this user may not decide
    # are left pending instead of failing the whole group.
    payloads = _payloads(db, tenant_id, [str(i.id) for i in items])
    items = [
        i for i in items
        if not _plan_step(payloads.get(str(i.id), {}))
        or _step_block_reason(db, tenant_id, user_id, payloads[str(i.id)], decision) is None
    ]
    _require_owner_for_campaign_approval(db, tenant_id, user_id, items, decision)
    audits = []
    for item in items:
        item.decision = decision
        item.decided_by = user_id
        item.decided_at = now
        item.reason = stored_reason
        audits.append(
            (
                str(item.id),
                {
                    "decision": decision,
                    "subject_type": item.subject_type,
                    "subject_id": subject_id,
                    "reason": stored_reason,
                    "group_decision": True,
                },
            )
        )
    _apply_campaign_decisions(db, tenant_id, user_id, items, decision, now)
    for item_id, meta in audits:
        _audit_decision(db, tenant_id, user_id, item_id, meta)
    decided_ids = [item_id for item_id, _ in audits]
    _notify_plans(db, tenant_id, user_id, [payloads.get(i, {}) for i in decided_ids], decision)
    logger.info(
        "approval_group_decided",
        tenant_id=tenant_id,
        subject_id=subject_id,
        decision=decision,
        decided_count=len(decided_ids),
    )
    return {
        "subject_id": subject_id,
        "decision": decision,
        "decided_count": len(decided_ids),
        "decided_ids": decided_ids,
    }


# Pending Approvals list (SPEC-BE-025).
#
# Title rule: fixed text keyed by subject_type, with only the item's own
# stored approval_queue.title interpolated - nothing from payload/summary and
# no lookups elsewhere, so no product name, amount, or person's name can
# appear unless it is already in that item's stored title.
TITLE_TEMPLATES = {
    "pricing_change": "Price change: {title}",
    "campaign": "Campaign: {title}",
    "content": "Content approval: {title}",
    "reply": "Reply draft: {title}",
    "plan": "Plan: {title}",
    "action": "Action: {title}",
}
# A subject_type with no template is SHOWN with this generic title, not
# excluded, so the count always equals every pending item. All six current
# approval_subject_type values have templates; this only applies if the enum
# gains a value.
GENERIC_TITLE_TEMPLATE = "Approval request: {title}"


def _engine_for(subject_type: str) -> str | None:
    # Engine label = SPEC-BE-020's mapping, via its constants directly (not a
    # second mapping). Types it maps to no engine (reply, plan, action) get
    # None; there is no Customer Service engine in that mapping.
    if subject_type in ECOMMERCE_SUBJECT_TYPES:
        return "E-Commerce"
    if subject_type in MARKETING_SUBJECT_TYPES:
        return "Marketing"
    return None


def list_pending(db: Session, tenant_id: str, now: datetime | None = None) -> dict[str, Any]:
    # Pending = decision 'pending', the same rule as get_pending_counts (an
    # item past expires_at still counts). Most recently requested first
    # (requested_at DESC, id DESC); no limit, so count == len(items).
    # elapsed_seconds = now - requested_at in whole seconds (never negative).
    now = now or datetime.now(timezone.utc)
    rows = (
        db.query(ApprovalQueue)
        .filter(ApprovalQueue.tenant_id == tenant_id, ApprovalQueue.decision == "pending")
        .order_by(ApprovalQueue.requested_at.desc(), ApprovalQueue.id.desc())
        .all()
    )
    step_payloads = _payloads(db, tenant_id, [str(r.id) for r in rows if r.subject_type == "action"])
    items = [
        {
            "id": str(row.id),
            "subject_type": row.subject_type,
            "title": TITLE_TEMPLATES.get(row.subject_type, GENERIC_TITLE_TEMPLATE).format(
                title=row.title
            ),
            "engine": _engine_for(row.subject_type)
            or {"ecommerce": "E-Commerce", "marketing": "Marketing"}.get(
                MODULE_ENGINE.get(step_payloads.get(str(row.id), {}).get("module", ""), "")
            ),
            "requested_at": row.requested_at.astimezone(timezone.utc),
            "elapsed_seconds": max(0, int((now - row.requested_at).total_seconds())),
        }
        for row in rows
    ]
    logger.info("pending_approvals_listed", tenant_id=tenant_id, count=len(items))
    return {"count": len(items), "items": items}
