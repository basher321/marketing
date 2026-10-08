"""Pagination helpers."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.schemas.common import Page


def paginate(db: Session, query, page: int, page_size: int, read_schema) -> Page:
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    items = db.execute(query.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return Page(
        items=[read_schema.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )
