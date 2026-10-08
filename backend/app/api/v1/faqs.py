"""/faqs endpoints (SPEC-BE-013, SPEC-BE-048).

Any authenticated user may list FAQs; adding, editing, enabling/disabling and
deleting one is manager+ because FAQs ground the AI's customer replies.
"""
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.faq import FAQCreate, FAQItem, FAQList, FAQUpdate
from app.services import faq_service

router = APIRouter(prefix="/faqs", tags=["faqs"])


@router.get("", response_model=FAQList, status_code=200)
def list_faqs(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return faq_service.list_faqs(db, str(current_user.tenant_id))


@router.post("", response_model=FAQItem, status_code=201)
def create_faq(
    payload: FAQCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return faq_service.create_faq(db, str(current_user.tenant_id), str(current_user.id), payload)


@router.patch("/{faq_id}", response_model=FAQItem, status_code=200)
def update_faq(
    faq_id: UUID,
    payload: FAQUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return faq_service.update_faq(db, str(current_user.tenant_id), str(current_user.id), str(faq_id), payload)


@router.delete("/{faq_id}", response_model=None, status_code=204)
def delete_faq(
    faq_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> None:
    faq_service.delete_faq(db, str(current_user.tenant_id), str(current_user.id), str(faq_id))
