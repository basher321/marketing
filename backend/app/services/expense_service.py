"""Business expenses for profit & loss (SPEC-BE-110 FR1).

Amounts are integer cents in the company's currency; another currency is refused
(no conversion). Deletes are soft (`deleted_at`), and every write is audited.
"""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.exceptions import AppError, NotFoundError
from app.models.expense import Expense
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.expense import ExpenseCreate, ExpensePatch

logger = structlog.get_logger(__name__)


def _currency(db: Session, tenant_id: str) -> str:
    return (db.scalar(select(Tenant.currency).where(Tenant.id == tenant_id)) or "USD").strip()


def _today(db: Session, tenant_id: str) -> date:
    tz = db.scalar(select(Tenant.timezone).where(Tenant.id == tenant_id)) or "UTC"
    return db.execute(text("SELECT (now() AT TIME ZONE :tz)::date"), {"tz": tz}).scalar_one()


def _read(e: Expense, names: dict[str, str]) -> dict[str, Any]:
    return {
        "id": str(e.id), "category": e.category, "amount": float(Decimal(e.amount_cents) / 100),
        "currency": e.currency.strip(), "incurred_on": e.incurred_on, "description": e.description,
        "vendor": e.vendor, "created_by_name": names.get(str(e.created_by)) if e.created_by else None,
        "created_at": e.created_at.astimezone(timezone.utc),
    }


def _names(db: Session, tenant_id: str, rows: list[Expense]) -> dict[str, str]:
    ids = {str(r.created_by) for r in rows if r.created_by}
    if not ids:
        return {}
    users = db.query(User.id, User.first_name, User.last_name, User.email).filter(
        User.tenant_id == tenant_id, User.id.in_(ids)
    )
    return {str(i): (" ".join(p for p in (f, ln) if p) or em) for i, f, ln, em in users}


def _get(db: Session, tenant_id: str, expense_id: str) -> Expense:
    try:
        uuid.UUID(str(expense_id))
    except ValueError:
        raise NotFoundError("Expense not found.") from None
    row = db.scalars(select(Expense).where(
        Expense.tenant_id == tenant_id, Expense.id == expense_id, Expense.deleted_at.is_(None)
    )).first()
    if row is None:
        raise NotFoundError("Expense not found.")
    return row


def list_expenses(
    db: Session, tenant_id: str, start: date | None, end: date | None, category: str | None,
    limit: int, offset: int,
) -> dict[str, Any]:
    filters = [Expense.tenant_id == tenant_id, Expense.deleted_at.is_(None)]
    if start:
        filters.append(Expense.incurred_on >= start)
    if end:
        filters.append(Expense.incurred_on <= end)
    if category:
        filters.append(Expense.category == category)
    total, cents = db.execute(
        select(func.count(Expense.id), func.coalesce(func.sum(Expense.amount_cents), 0)).where(*filters)
    ).one()
    rows = list(db.scalars(
        select(Expense).where(*filters).order_by(Expense.incurred_on.desc(), Expense.created_at.desc())
        .limit(limit).offset(offset)
    ))
    names = _names(db, tenant_id, rows)
    return {"total": int(total), "sum": float(Decimal(cents) / 100), "currency": _currency(db, tenant_id),
            "items": [_read(r, names) for r in rows]}


def _check_day(db: Session, tenant_id: str, day: date) -> None:
    if day > _today(db, tenant_id):
        raise AppError("An expense can't be dated in the future.", 422)


def create_expense(db: Session, tenant_id: str, actor: User, payload: ExpenseCreate) -> dict[str, Any]:
    currency = _currency(db, tenant_id)
    if payload.currency and payload.currency != currency:
        raise AppError(f"Expenses are recorded in the company currency ({currency}).", 422)
    _check_day(db, tenant_id, payload.incurred_on)
    row = Expense(
        tenant_id=tenant_id, category=payload.category, amount_cents=int(payload.amount * 100),
        currency=currency, incurred_on=payload.incurred_on, description=payload.description,
        vendor=payload.vendor or None, created_by=str(actor.id),
    )
    db.add(row)
    db.flush()
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=str(actor.id), action="expense.created",
                    resource_type="expense", resource_id=str(row.id),
                    metadata={"category": row.category, "amount_cents": row.amount_cents})
    return _read(row, _names(db, tenant_id, [row]))


def update_expense(db: Session, tenant_id: str, actor: User, expense_id: str, payload: ExpensePatch) -> dict[str, Any]:
    row = _get(db, tenant_id, expense_id)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("incurred_on"):
        _check_day(db, tenant_id, changes["incurred_on"])
    for field, value in changes.items():
        if value is None and field != "vendor":
            continue
        if field == "amount":
            row.amount_cents = int(value * 100)
        else:
            setattr(row, field, value)
    row.updated_at = datetime.now(timezone.utc)
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=str(actor.id), action="expense.updated",
                    resource_type="expense", resource_id=str(row.id), metadata={"fields": sorted(changes)})
    return _read(row, _names(db, tenant_id, [row]))


def delete_expense(db: Session, tenant_id: str, actor: User, expense_id: str) -> None:
    row = _get(db, tenant_id, expense_id)
    row.deleted_at = datetime.now(timezone.utc)
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=str(actor.id), action="expense.deleted",
                    resource_type="expense", resource_id=str(row.id), metadata={"amount_cents": row.amount_cents})
