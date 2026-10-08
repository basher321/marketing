"""Pricing rules: list, create, enable/disable (SPEC-BE-042).

Applying rules to prices at checkout is out of scope; the old evaluate_price()
was unused and written against columns the live table doesn't have, so it was
removed.
"""
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.exceptions import AppError, NotFoundError
from app.models.pricing import PricingRule
from app.models.product import Product
from app.models.tenant import Tenant
from app.schemas.pricing import PricingRuleCreate

logger = structlog.get_logger(__name__)


def _utc(value: datetime | None) -> datetime | None:
    return value.astimezone(timezone.utc) if value else None


def _state(rule: PricingRule, now: datetime) -> str:
    # Derived at request time (UTC): disabled wins; then not started yet ->
    # scheduled; past its end -> expired; otherwise active.
    if not rule.enabled:
        return "disabled"
    if rule.starts_at and rule.starts_at > now:
        return "scheduled"
    if rule.ends_at and rule.ends_at <= now:
        return "expired"
    return "active"


def _to_dict(rule: PricingRule, now: datetime) -> dict[str, Any]:
    return {
        "id": rule.id,
        "name": rule.name,
        "description": rule.description,
        "rule_type": rule.rule_type,
        "value": float(rule.value),
        "scope": rule.scope,
        # e.g. "3 products" in the UI; 0 for scope "all".
        "scope_count": len(rule.scope_ids or []),
        "min_quantity": rule.min_quantity,
        "starts_at": _utc(rule.starts_at),
        "ends_at": _utc(rule.ends_at),
        "priority": rule.priority,
        "enabled": rule.enabled,
        "state": _state(rule, now),
    }


def list_rules(db: Session, tenant_id: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    rules = (
        db.query(PricingRule)
        .filter(PricingRule.tenant_id == tenant_id)
        .order_by(
            PricingRule.enabled.desc(), PricingRule.priority.desc(), PricingRule.created_at.desc()
        )
        .all()
    )
    currency = db.query(Tenant.currency).filter(Tenant.id == tenant_id).scalar()
    return {
        "count": len(rules),
        "currency": currency,
        "items": [_to_dict(r, now) for r in rules],
    }


def create_rule(
    db: Session, tenant_id: str, actor_user_id: str, payload: PricingRuleCreate
) -> dict[str, Any]:
    product_ids = list(dict.fromkeys(str(p) for p in payload.product_ids))
    if product_ids:
        # scope "sku" stores product ids; each must be a live product of this tenant.
        found = {
            str(pid)
            for (pid,) in db.query(Product.id).filter(
                Product.tenant_id == tenant_id,
                Product.id.in_(product_ids),
                Product.deleted_at.is_(None),
            )
        }
        unknown = [p for p in product_ids if p not in found]
        if unknown:
            raise AppError(f"Unknown product ids: {', '.join(unknown)}", status_code=422)

    rule = PricingRule(
        tenant_id=tenant_id,
        name=payload.name,
        description=payload.description,
        scope=payload.scope,
        scope_ids=product_ids,
        rule_type=payload.rule_type,
        value=payload.value,
        min_quantity=payload.min_quantity,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        priority=payload.priority,
        enabled=True,
        created_by=actor_user_id,
    )
    db.add(rule)
    db.flush()
    # write_audit_log commits: the rule and its audit row land in one commit.
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="pricing_rule.create",
        resource_type="pricing_rule",
        resource_id=rule.id,
        metadata={
            "name": rule.name,
            "rule_type": rule.rule_type,
            "value": str(rule.value),
            "scope": rule.scope,
            "product_ids": product_ids,
        },
    )
    db.refresh(rule)
    logger.info("pricing_rule_created", tenant_id=tenant_id, rule_id=str(rule.id))
    return _to_dict(rule, datetime.now(timezone.utc))


def set_enabled(
    db: Session, tenant_id: str, actor_user_id: str, rule_id: str, enabled: bool
) -> dict[str, Any]:
    rule = (
        db.query(PricingRule)
        .filter(PricingRule.tenant_id == tenant_id, PricingRule.id == rule_id)
        .with_for_update()
        .first()
    )
    if rule is None:
        # Same 404 for a missing rule and another tenant's rule.
        raise NotFoundError("Pricing rule not found.")
    rule.enabled = enabled
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="pricing_rule.enable" if enabled else "pricing_rule.disable",
        resource_type="pricing_rule",
        resource_id=rule.id,
        metadata={"name": rule.name},
    )
    db.refresh(rule)
    logger.info("pricing_rule_toggled", tenant_id=tenant_id, rule_id=str(rule.id), enabled=enabled)
    return _to_dict(rule, datetime.now(timezone.utc))
