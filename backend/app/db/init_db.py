"""Initial data seeding script — creates tables (dev/test convenience).

In production, schema changes go through Alembic migrations
(`alembic upgrade head`). This helper is for local/dev bootstrapping and for
the test suite's SQLite fixtures.
"""
from app.db.base import Base
from app.db.session import engine

# Import every model module so they register on Base.metadata.
from app.models import (  # noqa: F401
    tenant,
    user,
    audit_log,
    product,
    inventory,
    pricing,
    shipping,
    customer,
    order,
    conversation,
    faq,
    brand,
    kb_document,
    content,
    scheduled_post,
    campaign,
    analytics,
    workflow,
    approval,
    integration,
    orchestrator,
)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Database tables created.")
