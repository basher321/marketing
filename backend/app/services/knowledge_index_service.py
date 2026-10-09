"""Knowledge embedding index for AI reply retrieval (SPEC-BE-087).

Index units: enabled FAQs (question + answer), enabled in-effect policies
(title + body) and KB documents (title + body, in ~1,000-character chunks).
`refresh` embeds units that are new or whose content changed (SHA-256), at
most 50 per call, and deletes rows whose unit no longer exists, inside a
savepoint of the caller's session. The FAQ / policy / KB write paths are not
touched: the index catches up on the next retrieval.

Vectors live in knowledge_embeddings.embedding (real[], unit length); the
live server has no pgvector, so similarity is a dot product in Python (a
company's knowledge is hundreds of rows). Every query is tenant-filtered.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import REAL, and_, column, delete, func, or_, select, table, true
from sqlalchemy.dialects.postgresql import ARRAY, insert
from sqlalchemy.orm import Session

from app.ai import embeddings

logger = structlog.get_logger(__name__)

REFRESH_LIMIT = 50
CHUNK_CHARS = 1000
SNIPPET_CHARS = 1200  # same as ai/retrieval._SNIPPET_CHARS

_ke = table(
    "knowledge_embeddings",
    column("id"), column("tenant_id"), column("source_kind"), column("source_id"), column("chunk"),
    column("content_hash"), column("model"), column("dims"), column("embedding", ARRAY(REAL)), column("updated_at"),
)
_faqs = table("faqs", column("id"), column("tenant_id"), column("question"), column("answer"), column("enabled"))
_policies = table(
    "policies", column("id"), column("tenant_id"), column("title"), column("body"), column("enabled"),
    column("effective_from"), column("effective_until"),
)
_kb = table("kb_documents", column("id"), column("tenant_id"), column("title"), column("body"))


@dataclass(frozen=True)
class Unit:
    kind: str  # "faq" | "policy" | "kb_document" (GroundingSource.kind)
    source_id: str
    chunk: int
    title: str
    snippet: str
    text: str  # what is embedded

    @property
    def key(self) -> tuple[str, str, int]:
        return (self.kind, self.source_id, self.chunk)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def chunk_text(body: str, size: int = CHUNK_CHARS) -> list[str]:
    """Split at paragraph, then sentence boundaries into pieces of at most
    ~`size` characters (a longer sentence is cut hard)."""
    body = (body or "").strip()
    if len(body) <= size:
        return [body] if body else []
    pieces = [p for p in re.split(r"(?<=[.!?।])\s+|\n\s*\n", body) if p.strip()]
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        while len(piece) > size:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(piece[:size])
            piece = piece[size:]
        if current and len(current) + 1 + len(piece) > size:
            chunks.append(current)
            current = piece
        else:
            current = f"{current} {piece}".strip()
    if current:
        chunks.append(current)
    return chunks


def units(db: Session, tenant_id: str) -> list[Unit]:
    """The tenant's current index units, with the same validity rules as the
    full-text search (FAQ enabled; policy enabled and in effect now)."""
    now = func.now()
    found: list[Unit] = []
    for row in db.execute(select(_faqs.c.id, _faqs.c.question, _faqs.c.answer)
                          .where(_faqs.c.tenant_id == tenant_id, _faqs.c.enabled.is_(True))):
        found.append(Unit("faq", str(row.id), 0, row.question, (row.answer or "")[:SNIPPET_CHARS], f"{row.question}\n{row.answer}"))
    in_effect = and_(
        _policies.c.enabled.is_(True),
        or_(_policies.c.effective_from.is_(None), _policies.c.effective_from <= now),
        or_(_policies.c.effective_until.is_(None), _policies.c.effective_until > now),
    )
    for row in db.execute(select(_policies.c.id, _policies.c.title, _policies.c.body)
                          .where(_policies.c.tenant_id == tenant_id, in_effect)):
        found.append(Unit("policy", str(row.id), 0, row.title, (row.body or "")[:SNIPPET_CHARS], f"{row.title}\n{row.body}"))
    for row in db.execute(select(_kb.c.id, _kb.c.title, _kb.c.body).where(_kb.c.tenant_id == tenant_id, true())):
        for i, piece in enumerate(chunk_text(row.body or "")):
            found.append(Unit("kb_document", str(row.id), i, row.title, piece[:SNIPPET_CHARS], f"{row.title}\n{piece}"))
    return found


def refresh(db: Session, tenant_id: str, current: list[Unit], model: str) -> int:
    """Embeds up to REFRESH_LIMIT new/changed units and deletes rows of units
    that are gone. Returns how many units were embedded. Raises
    embeddings.EmbeddingError (nothing is written then)."""
    stored = {
        (r.source_kind, str(r.source_id), r.chunk): r.content_hash
        for r in db.execute(select(_ke.c.source_kind, _ke.c.source_id, _ke.c.chunk, _ke.c.content_hash)
                            .where(_ke.c.tenant_id == tenant_id, _ke.c.model == model))
    }
    wanted = {u.key: u for u in current}
    todo = [u for u in current if stored.get(u.key) != u.content_hash][:REFRESH_LIMIT]
    gone = [k for k in stored if k not in wanted]
    vectors = embeddings.embed([u.text for u in todo], "document") if todo else []
    if not todo and not gone:
        return 0
    with db.begin_nested():
        for kind, source_id, chunk in gone:
            db.execute(delete(_ke).where(_ke.c.tenant_id == tenant_id, _ke.c.model == model, _ke.c.source_kind == kind,
                                         _ke.c.source_id == source_id, _ke.c.chunk == chunk))
        for unit, vector in zip(todo, vectors, strict=True):
            stmt = insert(_ke).values(tenant_id=tenant_id, source_kind=unit.kind, source_id=unit.source_id, chunk=unit.chunk,
                                      content_hash=unit.content_hash, model=model, dims=len(vector), embedding=vector)
            db.execute(stmt.on_conflict_do_update(
                index_elements=["tenant_id", "source_kind", "source_id", "chunk", "model"],
                set_={"content_hash": stmt.excluded.content_hash, "dims": stmt.excluded.dims,
                      "embedding": stmt.excluded.embedding, "updated_at": func.now()}))
    logger.info("knowledge_index_refreshed", tenant_id=tenant_id, embedded=len(todo), removed=len(gone),
                pending=max(0, len([u for u in current if stored.get(u.key) != u.content_hash]) - len(todo)))
    return len(todo)


def search(db: Session, tenant_id: str, query_vector: list[float], current: list[Unit], model: str,
           threshold: float, top: int) -> list[tuple[Unit, float]]:
    """Valid units ranked by cosine similarity (≥ threshold), best first."""
    wanted = {u.key: u for u in current}
    scored: list[tuple[Unit, float]] = []
    for row in db.execute(select(_ke.c.source_kind, _ke.c.source_id, _ke.c.chunk, _ke.c.content_hash, _ke.c.embedding)
                          .where(_ke.c.tenant_id == tenant_id, _ke.c.model == model)):
        unit = wanted.get((row.source_kind, str(row.source_id), row.chunk))
        if unit is None or row.content_hash != unit.content_hash or len(row.embedding) != len(query_vector):
            continue  # removed, changed but not re-embedded yet, or another size
        similarity = sum(a * b for a, b in zip(query_vector, row.embedding))
        if similarity >= threshold:
            scored.append((unit, similarity))
    scored.sort(key=lambda pair: (-pair[1], pair[0].kind, pair[0].source_id, pair[0].chunk))
    return scored[:top]


def stats(db: Session, tenant_id: str) -> dict[str, Any]:
    rows = db.execute(select(_ke.c.model, func.count()).where(_ke.c.tenant_id == tenant_id).group_by(_ke.c.model)).all()
    return {str(m): int(n) for m, n in rows}
