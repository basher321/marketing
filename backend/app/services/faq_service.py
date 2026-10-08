"""FAQ business logic (SPEC-BE-013)."""
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.exceptions import NotFoundError
from app.models.faq import FAQ
from app.schemas.faq import FAQCreate, FAQUpdate

logger = structlog.get_logger(__name__)


def _to_item(faq: FAQ) -> dict[str, Any]:
    # channels [] means "All channels" - the empty array is returned as-is and the
    # frontend renders the wording; it is never expanded into the full enum list.
    return {
        "id": str(faq.id),
        "question": faq.question,
        "answer": faq.answer,
        "enabled": faq.enabled,
        "channels": list(faq.channels or []),
    }


def _get(db: Session, tenant_id: str, faq_id: str) -> FAQ:
    faq = db.scalars(select(FAQ).where(FAQ.tenant_id == tenant_id, FAQ.id == faq_id)).first()
    if faq is None:
        # Same 404 for a missing FAQ and another tenant's FAQ.
        raise NotFoundError("FAQ not found.")
    return faq


def update_faq(
    db: Session, tenant_id: str, actor_user_id: str, faq_id: str, payload: FAQUpdate
) -> dict[str, Any]:
    # SPEC-BE-048: edit / enable / disable. A disabled FAQ stays listed here but
    # is excluded from the AI's reply grounding (retrieval filters enabled).
    faq = _get(db, tenant_id, faq_id)
    sent = payload.model_fields_set
    for field in ("question", "answer", "enabled"):
        if field in sent and getattr(payload, field) is not None:
            setattr(faq, field, getattr(payload, field))
    if "channels" in sent and payload.channels is not None:
        faq.channels = list(payload.channels)
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="faq.update",
        resource_type="faq",
        resource_id=str(faq.id),
        metadata={"fields": sorted(sent)},
    )
    db.refresh(faq)
    return _to_item(faq)


def delete_faq(db: Session, tenant_id: str, actor_user_id: str, faq_id: str) -> None:
    faq = _get(db, tenant_id, faq_id)
    question = faq.question
    db.delete(faq)
    db.flush()
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="faq.delete",
        resource_type="faq",
        resource_id=faq_id,
        metadata={"question": question[:200]},
    )


def list_faqs(db: Session, tenant_id: str) -> dict[str, Any]:
    # Every FAQ of the tenant, enabled or not, in the order they were added.
    faqs = db.scalars(
        select(FAQ).where(FAQ.tenant_id == tenant_id).order_by(FAQ.created_at, FAQ.id)
    ).all()
    items = [_to_item(f) for f in faqs]
    return {"count": len(items), "items": items}


def create_faq(
    db: Session, tenant_id: str, actor_user_id: str, payload: FAQCreate
) -> dict[str, Any]:
    # tags, language, priority, times_used and enabled take their database/model defaults:
    # none of them is shown or editable in the mockup.
    faq = FAQ(
        tenant_id=tenant_id,
        question=payload.question,
        answer=payload.answer,
        channels=list(payload.channels),
    )
    db.add(faq)
    db.flush()
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="faq.created",
        resource_type="faq",
        resource_id=str(faq.id),
        metadata={"channels": list(payload.channels)},
    )
    logger.info("faq.created", tenant_id=tenant_id, faq_id=str(faq.id))
    return _to_item(faq)
