"""Message threading, assignment, handoff."""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.ai.prompts.reply_drafter import HistoryMessage, generate_reply_draft
from app.core.audit import write_audit_log
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models.conversation import Conversation, Message
from app.models.customer import Customer

logger = structlog.get_logger(__name__)

# Customer Service inbox (SPEC-BE-007). Only live conversation_status 'open' and 'pending'
# are listed; 'resolved' and 'archived' are out of the inbox.
INBOX_STATUSES = ("open", "pending")


def _customer_name(
    first: str | None, last: str | None, email: str | None, phone: str | None
) -> str | None:
    # "first last" trimmed; if empty, fall back to email, then phone; else null. The
    # mockup's "Sarah A." abbreviation is left to the frontend.
    name = " ".join(p.strip() for p in (first, last) if p and p.strip())
    return name or email or phone or None


def _handed_off_at(metadata: Any) -> datetime | None:
    # The handoff marker written by handoff() below: metadata.handed_off_at (ISO-8601, UTC).
    raw = metadata.get("handed_off_at") if isinstance(metadata, dict) else None
    try:
        parsed = datetime.fromisoformat(raw) if isinstance(raw, str) else None
    except ValueError:
        return None
    if parsed is not None and parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def list_inbox(db: Session, tenant_id: str) -> dict[str, Any]:
    """The Open Conversations table: 4 queries total, never one per conversation.

    inbox_status, first matching rule wins (a "sent reply" = outbound message from 'agent'
    or 'ai' with sent_at set):
      1. escalated    - a handoff marker exists and no reply was sent after it;
      2. draft_ready  - a pending AI draft exists (outbound, 'ai', sent_at NULL);
      3. new          - no reply ever sent, or the customer's latest message is newer than
                        the latest sent reply (customer waiting, nothing drafted);
      4. auto_replied - the latest sent reply is from 'ai' with no human approval
                        (approved_by NULL). Nothing produces this yet (no automatic replies);
      5. replied      - otherwise (a human sent or approved the latest reply).
    waiting_since = the latest inbound 'customer' message's created_at, from messages (the
    conversations.last_customer_message_at column is not maintained by anything yet).
    """
    rows = db.execute(
        select(
            Conversation.id,
            Conversation.channel,
            Conversation.status,
            Conversation.topic,
            Conversation.extra_metadata,
            Conversation.created_at,
            Customer.first_name,
            Customer.last_name,
            Customer.email,
            Customer.phone,
        )
        .outerjoin(
            Customer,
            (Customer.id == Conversation.customer_id)
            & (Customer.tenant_id == tenant_id)
            & Customer.deleted_at.is_(None),
        )
        .where(Conversation.tenant_id == tenant_id, Conversation.status.in_(INBOX_STATUSES))
    ).all()
    ids = [r.id for r in rows]
    if not ids:
        return {"count": 0, "items": []}

    in_tenant = (Message.tenant_id == tenant_id, Message.conversation_id.in_(ids))
    last_customer = {
        str(cid): at
        for cid, at in db.execute(
            select(Message.conversation_id, func.max(Message.created_at))
            .where(*in_tenant, Message.direction == "inbound", Message.sender_type == "customer")
            .group_by(Message.conversation_id)
        ).all()
    }
    last_reply = {
        str(r.conversation_id): r
        for r in db.execute(
            select(
                Message.conversation_id, Message.sent_at, Message.sender_type, Message.approved_by
            )
            .where(
                *in_tenant,
                Message.direction == "outbound",
                Message.sender_type.in_(("agent", "ai")),
                Message.sent_at.is_not(None),
            )
            .order_by(Message.conversation_id, Message.sent_at.desc(), Message.id.desc())
            .distinct(Message.conversation_id)
        ).all()
    }
    with_draft = {
        str(cid)
        for cid in db.scalars(
            select(Message.conversation_id)
            .where(
                *in_tenant,
                Message.direction == "outbound",
                Message.sender_type == "ai",
                Message.sent_at.is_(None),
            )
            .distinct()
        ).all()
    }

    items = []
    for r in rows:
        cid = str(r.id)
        waiting = last_customer.get(cid)
        reply = last_reply.get(cid)
        handed_off = _handed_off_at(r.extra_metadata)
        if handed_off is not None and (reply is None or reply.sent_at <= handed_off):
            inbox_status = "escalated"
        elif cid in with_draft:
            inbox_status = "draft_ready"
        elif reply is None or (waiting is not None and waiting > reply.sent_at):
            inbox_status = "new"
        elif reply.sender_type == "ai" and reply.approved_by is None:
            inbox_status = "auto_replied"
        else:
            inbox_status = "replied"
        items.append(
            {
                "id": cid,
                "customer_name": _customer_name(r.first_name, r.last_name, r.email, r.phone),
                "channel": r.channel,
                "topic": r.topic,
                "waiting_since": waiting.astimezone(timezone.utc) if waiting else None,
                "inbox_status": inbox_status,
                "status": r.status,
                "_created_at": r.created_at,
            }
        )
    # Most recent customer message first; conversations the customer never wrote to last;
    # ties by newest conversation, then id.
    items.sort(
        key=lambda i: (
            i["waiting_since"] is None,
            -i["waiting_since"].timestamp() if i["waiting_since"] else 0.0,
            -i["_created_at"].timestamp(),
            i["id"],
        )
    )
    for item in items:
        del item["_created_at"]
    return {"count": len(items), "items": items}


def get_conversation(db: Session, tenant_id: str, conversation_id: str) -> Conversation:
    conversation = (
        db.query(Conversation)
        .filter(Conversation.tenant_id == tenant_id, Conversation.id == conversation_id)
        .first()
    )
    if conversation is None:
        raise NotFoundError("Conversation not found.")
    return conversation


def add_message(db: Session, tenant_id: str, conversation_id: str, sender_type: str, body: str) -> Message:
    conversation = get_conversation(db, tenant_id, conversation_id)
    message = Message(conversation_id=conversation.id, sender_type=sender_type, body=body)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def assign_conversation(db: Session, tenant_id: str, conversation_id: str, user_id: str) -> Conversation:
    conversation = get_conversation(db, tenant_id, conversation_id)
    conversation.assigned_user_id = user_id
    db.commit()
    db.refresh(conversation)
    return conversation


def get_cs_metrics(
    db: Session, tenant_id: str, now: datetime | None = None
) -> dict[str, float | None]:
    # Customer Service engine card (SPEC-BE-021). Window: the tenant's
    # conversations with created_at in [now-7d, now] (UTC), for all three
    # figures. Every query filters conversations.tenant_id and
    # messages.tenant_id explicitly. null = no data / placeholder.
    #
    # SPEC-BE-007 does not exist, so there is no waiting-time computation or
    # status derivation to reuse; avg. response is computed here per
    # SPEC-BE-021's own rule.
    now = now or datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    in_window = (
        Conversation.tenant_id == tenant_id,
        Conversation.created_at >= week_ago,
        Conversation.created_at <= now,
    )

    # Avg. response = per conversation, the time from its last customer message
    # (messages.direction 'inbound' + sender_type 'customer', at created_at) to
    # the first reply sent after it (direction 'outbound', sender_type 'agent'
    # or 'ai', at sent_at; unsent AI drafts with sent_at NULL and 'system'
    # messages do not count). Conversations with no reply yet are excluded.
    # Averaged in seconds; null when no conversation has a reply.
    last_customer = (
        select(
            Message.conversation_id.label("conversation_id"),
            func.max(Message.created_at).label("last_at"),
        )
        .where(
            Message.tenant_id == tenant_id,
            Message.direction == "inbound",
            Message.sender_type == "customer",
        )
        .group_by(Message.conversation_id)
        .subquery()
    )
    first_reply = (
        select(func.min(Message.sent_at))
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == last_customer.c.conversation_id,
            Message.direction == "outbound",
            Message.sender_type.in_(("agent", "ai")),
            Message.sent_at.is_not(None),
            Message.sent_at >= last_customer.c.last_at,
        )
        .scalar_subquery()
    )
    delays = (
        select(func.extract("epoch", first_reply - last_customer.c.last_at).label("seconds"))
        .select_from(Conversation)
        .join(last_customer, last_customer.c.conversation_id == Conversation.id)
        .where(*in_window)
        .subquery()
    )
    avg_seconds = db.execute(select(func.avg(delays.c.seconds))).scalar()

    # Deflection rate - PLACEHOLDER (null) pending an escalation signal /
    # SPEC-BE-007. SPEC-BE-021's rule is "% of conversations whose status per
    # SPEC-BE-007's derivation is not 'escalated'", but SPEC-BE-007 does not
    # exist and no escalated state exists in the live schema:
    # conversation_status is open/pending/resolved/archived, and no column
    # records escalation or handoff. Counting "not escalated" would report
    # 100% for every tenant, so no figure is returned. Never replace this with
    # a proxy definition.
    deflection_rate_pct = None

    # CSAT (7d) = AVG(conversations.csat_score) over the window's conversations
    # that have a score (NULL scores ignored), rounded to 1 decimal; null when
    # none are scored. The scale is not constrained in the DB (the HTML shows
    # "/5").
    avg_csat = db.execute(
        select(func.avg(Conversation.csat_score)).where(
            *in_window, Conversation.csat_score.is_not(None)
        )
    ).scalar()

    metrics = {
        "avg_response_seconds": round(float(avg_seconds), 1) if avg_seconds is not None else None,
        "deflection_rate_pct": deflection_rate_pct,
        "csat_7d": round(float(avg_csat), 1) if avg_csat is not None else None,
    }
    logger.info("cs_metrics_computed", tenant_id=tenant_id, **metrics)
    return metrics


# AI Reply Draft actions (SPEC-BE-026) - operate on an existing draft only; no
# draft generation, LLM call, or moderation happens here.
#
# A "pending draft" is a messages row with direction 'outbound', sender_type
# 'ai' and sent_at NULL (the same "unsent AI draft" SPEC-BE-021 excludes from
# avg. response). There is no draft table or draft-status column. With several,
# the newest (created_at, then id) is the current draft.
#
# No escalated state exists in the live conversation_status enum
# (open/pending/resolved/archived), so neither send nor handoff changes
# conversations.status; handoff records a metadata marker instead (SPEC-BE-007).


def _require_conversation(db: Session, tenant_id: str, conversation_id: str) -> None:
    # Another tenant's conversation is indistinguishable from a missing one:
    # 404, never 403. Column-level query (the Conversation model still maps
    # columns the live table lacks).
    found = (
        db.query(Conversation.id)
        .filter(Conversation.id == conversation_id, Conversation.tenant_id == tenant_id)
        .first()
    )
    if found is None:
        raise NotFoundError("Conversation not found.")


def _pending_draft(
    db: Session, tenant_id: str, conversation_id: str, lock: bool = False
) -> Message | None:
    query = (
        db.query(Message)
        .filter(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation_id,
            Message.direction == "outbound",
            Message.sender_type == "ai",
            Message.sent_at.is_(None),
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
    )
    if lock:
        query = query.with_for_update()
    return query.first()


def _require_pending_draft(db: Session, tenant_id: str, conversation_id: str) -> Message:
    _require_conversation(db, tenant_id, conversation_id)
    draft = _pending_draft(db, tenant_id, conversation_id, lock=True)
    if draft is None:
        raise ConflictError("No pending draft for this conversation.")
    return draft


def get_pending_draft(db: Session, tenant_id: str, conversation_id: str) -> dict[str, Any]:
    # Returns {"draft": None} when there is no pending draft - the documented
    # empty response, not an error.
    _require_conversation(db, tenant_id, conversation_id)
    draft = _pending_draft(db, tenant_id, conversation_id)
    if draft is None:
        return {"draft": None}
    # confidence / sources (SPEC-BE-028) are read back exactly as persisted
    # from SPEC-BE-027's result: messages.ai_confidence and
    # messages.metadata->'grounding_sources'. null / [] when absent.
    metadata = draft.extra_metadata if isinstance(draft.extra_metadata, dict) else {}
    return {
        "draft": {
            "id": str(draft.id),
            "body": draft.body,
            "created_at": draft.created_at.astimezone(timezone.utc),
            "confidence": float(draft.ai_confidence) if draft.ai_confidence is not None else None,
            "sources": metadata.get("grounding_sources", []),
        }
    }


def edit_draft(
    db: Session, tenant_id: str, conversation_id: str, body: str
) -> dict[str, Any]:
    # Updates only the draft's text; nothing is sent and no audit row is
    # written (the spec audits send and handoff only).
    draft = _require_pending_draft(db, tenant_id, conversation_id)
    draft.body = body
    db.commit()
    logger.info("draft_edited", tenant_id=tenant_id, conversation_id=conversation_id)
    return get_pending_draft(db, tenant_id, conversation_id)


def send_draft(
    db: Session, tenant_id: str, conversation_id: str, user_id: str
) -> dict[str, Any]:
    # Send in place: the pending draft row becomes the outbound message
    # (sent_at = approved_at = now, approved_by = caller), which also consumes
    # the draft - it no longer matches the pending-draft rule. The
    # conversation's last_agent_message_at is updated. A whitespace-only draft
    # is rejected (400) before anything is written. One audit_log row.
    draft = _require_pending_draft(db, tenant_id, conversation_id)
    if not draft.body or not draft.body.strip():
        raise AppError("Draft text is empty; nothing was sent.")
    now = datetime.now(timezone.utc)
    draft.sent_at = now
    draft.approved_at = now
    draft.approved_by = user_id
    db.query(Conversation).filter(
        Conversation.id == conversation_id, Conversation.tenant_id == tenant_id
    ).update({Conversation.last_agent_message_at: now}, synchronize_session=False)
    message_id, body = str(draft.id), draft.body
    # write_audit_log commits: the send and its audit row land together.
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=user_id,
        action="conversation.reply_sent",
        resource_type="message",
        resource_id=message_id,
        metadata={"conversation_id": conversation_id},
    )
    logger.info("draft_sent", tenant_id=tenant_id, conversation_id=conversation_id)
    return {"message_id": message_id, "body": body, "sent_at": now}


def handoff(
    db: Session, tenant_id: str, conversation_id: str, user_id: str
) -> dict[str, Any]:
    # Escalates to a human without sending the draft. Requires a pending draft
    # (per SPEC-BE-026). The draft is left unsent (still pending) and
    # conversations.status is not changed (no escalated value exists in the live
    # conversation_status enum). SPEC-BE-007: the handoff is also recorded as a
    # durable marker in conversations.metadata (handed_off_at ISO-8601 UTC,
    # handed_off_by), which the inbox reads as "escalated" until a reply is sent
    # after it; plus its one audit_log row, as before.
    draft = _require_pending_draft(db, tenant_id, conversation_id)
    now = datetime.now(timezone.utc)
    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.tenant_id == tenant_id)
        .with_for_update()
        .one()
    )
    # A new dict (not in-place mutation) so the JSONB change is detected and saved.
    conversation.extra_metadata = {
        **(conversation.extra_metadata or {}),
        "handed_off_at": now.isoformat(),
        "handed_off_by": str(user_id),
    }
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=user_id,
        action="conversation.handoff",
        resource_type="conversation",
        resource_id=conversation_id,
        metadata={"draft_id": str(draft.id)},
    )
    logger.info("conversation_handed_off", tenant_id=tenant_id, conversation_id=conversation_id)
    return {"conversation_id": conversation_id, "handed_off_at": now}


# AI reply-draft generation (SPEC-BE-028): calls SPEC-BE-027's
# generate_reply_draft() as-is and persists its result as the conversation's
# pending draft. No retrieval, LLM or moderation logic lives here; the LLM call
# is logged (with token counts) by SPEC-BE-027's llm_call span, not re-logged.
#
# Replace rule: generating again REPLACES the existing pending draft. After a
# successful generation, every pending draft of the conversation (SPEC-BE-026's
# definition: outbound, sender_type 'ai', sent_at NULL) is deleted and the new
# one inserted, in one commit, under a row lock on the conversation - so there
# is never more than one pending draft. Rejecting instead would strand
# conversations: SPEC-BE-026 has no discard action and handoff leaves the draft
# pending. Replacing discards manual edits to the old draft; the replaced ids
# are recorded in the audit row. If generation fails, nothing is deleted or
# written, so the existing draft survives.
def _generation_history(
    db: Session, tenant_id: str, conversation_id: str
) -> list[tuple[str, HistoryMessage]]:
    # The conversation's customer messages plus messages actually sent
    # (sent_at set), oldest first; unsent drafts are excluded.
    rows = (
        db.query(Message.id, Message.sender_type, Message.body)
        .filter(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation_id,
            or_(Message.sender_type == "customer", Message.sent_at.is_not(None)),
        )
        .order_by(Message.created_at, Message.id)
        .all()
    )
    return [(str(row.id), HistoryMessage(row.sender_type, row.body or "")) for row in rows]


def generate_draft(
    db: Session, tenant_id: str, conversation_id: str, user_id: str
) -> dict[str, Any]:
    _require_conversation(db, tenant_id, conversation_id)
    history = _generation_history(db, tenant_id, conversation_id)
    customer_ids = [
        message_id
        for message_id, message in history
        if message.sender_type == "customer" and message.body.strip()
    ]
    if not customer_ids:
        raise AppError("Conversation has no customer messages to reply to.", 422)

    # SPEC-BE-027's typed errors (LLMProviderError 503, DraftRejectedError 422)
    # propagate unchanged; nothing has been written at this point.
    draft = generate_reply_draft(db, tenant_id, [message for _, message in history])

    db.query(Conversation.id).filter(
        Conversation.id == conversation_id, Conversation.tenant_id == tenant_id
    ).with_for_update().one()
    pending = db.query(Message).filter(
        Message.tenant_id == tenant_id,
        Message.conversation_id == conversation_id,
        Message.direction == "outbound",
        Message.sender_type == "ai",
        Message.sent_at.is_(None),
    )
    replaced_ids = [str(message.id) for message in pending.all()]
    pending.delete(synchronize_session=False)

    # Persisted exactly as SPEC-BE-027 returned it - nothing re-derived.
    message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        direction="outbound",
        sender_type="ai",
        body=draft.body,
        ai_confidence=Decimal(str(draft.confidence)),
        ai_model=draft.model,
        ai_draft_of_id=customer_ids[-1],
        extra_metadata={
            "grounding_sources": [asdict(source) for source in draft.sources],
            "fallback": draft.fallback,
            "moderation_passed": draft.moderation_passed,
            "moderation_reasons": draft.moderation_reasons,
            "input_tokens": draft.input_tokens,
            "output_tokens": draft.output_tokens,
        },
    )
    db.add(message)
    db.flush()
    message_id = str(message.id)
    # write_audit_log commits: the delete, the insert and the audit row land
    # together.
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=user_id,
        action="conversation.draft_generated",
        resource_type="message",
        resource_id=message_id,
        metadata={
            "conversation_id": conversation_id,
            "replaced_draft_ids": replaced_ids,
            "fallback": draft.fallback,
        },
    )
    logger.info(
        "draft_persisted",
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        message_id=message_id,
        replaced=len(replaced_ids),
    )
    return get_pending_draft(db, tenant_id, conversation_id)
