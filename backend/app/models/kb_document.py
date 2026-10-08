"""KnowledgeBaseDocument model.

SPEC-BE-071 F6: mapped to the live kb_documents table (body, document_type,
metadata, indexed_at). The old mapping (content / embedding_status /
extra_metadata as columns) didn't exist in the database and crashed every KB
document call. "Embedding status" is derived: indexed once indexed_at is set.
"""
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TenantScopedModel


class KnowledgeBaseDocument(Base, TenantScopedModel):
    __tablename__ = "kb_documents"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False, default="note")
    extra_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def embedding_status(self) -> str:
        return "indexed" if self.indexed_at else "pending"
