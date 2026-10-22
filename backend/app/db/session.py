"""DB engine, session factory, get_db dependency.

Uses DATABASE_URL_SYNC (psycopg2), not the async DATABASE_URL (asyncpg),
even though SPEC-BE-001/002/003 set the project up for an async stack. The
service layer (app/services/*.py, app/dependencies.py) still uses the sync
`Session` API (`.query()`, `.commit()`, no `await`) end to end, so switching
this engine to async would break every one of those call sites. This module
just needs to connect; migrating the service layer to AsyncSession is a
separate, much larger piece of work.
"""
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL_SYNC.get_secret_value(),
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    echo=settings.APP_DEBUG,
    # A serverless Postgres (Neon) suspends when idle and drops open
    # connections; check each pooled connection before handing it out.
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
