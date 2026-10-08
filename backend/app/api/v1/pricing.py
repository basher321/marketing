"""/pricing/rules endpoints (SPEC-BE-042)."""
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.pricing import (
    PricingRuleCreate,
    PricingRuleList,
    PricingRuleRead,
    PricingRuleToggle,
)
from app.services import pricing_service

router = APIRouter(prefix="/pricing", tags=["pricing"])


@router.get("/rules", response_model=PricingRuleList, status_code=status.HTTP_200_OK)
def list_rules(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return pricing_service.list_rules(db, current_user.tenant_id)


@router.post("/rules", response_model=PricingRuleRead, status_code=status.HTTP_201_CREATED)
def create_rule(
    payload: PricingRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return pricing_service.create_rule(db, current_user.tenant_id, current_user.id, payload)


@router.patch("/rules/{rule_id}", response_model=PricingRuleRead, status_code=status.HTTP_200_OK)
def toggle_rule(
    rule_id: UUID,
    payload: PricingRuleToggle,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return pricing_service.set_enabled(
        db, current_user.tenant_id, current_user.id, str(rule_id), payload.enabled
    )
