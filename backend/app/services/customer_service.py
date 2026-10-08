"""Customer profile management (SPEC-BE-007)."""
from datetime import timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.customer import Customer
from app.schemas.customer import CustomerCreate

logger = structlog.get_logger(__name__)

CUSTOMERS_EMAIL_UNIQUE = "customers_tenant_email_unique"


def _to_read(customer: Customer) -> dict[str, Any]:
    return {
        "id": str(customer.id),
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "email": customer.email,
        "phone": customer.phone,
        "created_at": customer.created_at.astimezone(timezone.utc),
    }


def list_customers(db: Session, tenant_id: str) -> list[dict[str, Any]]:
    # Soft-deleted customers (deleted_at set) are excluded.
    customers = db.scalars(
        select(Customer)
        .where(Customer.tenant_id == tenant_id, Customer.deleted_at.is_(None))
        .order_by(Customer.created_at, Customer.id)
    ).all()
    return [_to_read(c) for c in customers]


def get_customer(db: Session, tenant_id: str, customer_id: str) -> Customer:
    customer = db.scalars(
        select(Customer).where(
            Customer.tenant_id == tenant_id,
            Customer.id == customer_id,
            Customer.deleted_at.is_(None),
        )
    ).first()
    if customer is None:
        raise NotFoundError("Customer not found.")
    return customer


def create_customer(db: Session, tenant_id: str, payload: CustomerCreate) -> dict[str, Any]:
    customer = Customer(tenant_id=tenant_id, **payload.model_dump())
    try:
        db.add(customer)
        db.commit()
    except IntegrityError as exc:
        # Live UNIQUE (tenant_id, email); email is citext, so this is case-insensitive.
        db.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == CUSTOMERS_EMAIL_UNIQUE:
            raise ConflictError("A customer with this email already exists.") from exc
        raise
    db.refresh(customer)
    logger.info("customer.created", tenant_id=tenant_id, customer_id=str(customer.id))
    return _to_read(customer)
