"""KB vector retrieval (pgvector).

Structural stub: production implementation embeds the query and does a
pgvector cosine-distance query against `kb_documents`. For now, does a
naive substring search so the orchestrator has something real to call.

SPEC-BE-027 adds `retrieve_grounding()` and `get_brand_voice()` for reply
drafting. They read the live tables through lightweight table() constructs
rather than the KnowledgeBaseDocument / BrandSettings models, because those
models do not match the live schema (live kb_documents has `body`, not
`content`; live brand_settings has brand_name/voice_config/forbidden_terms/
primary_language, not tone/voice_guidelines/colors). Note that
retrieve_relevant_documents() below still uses the mismatched model and
fails on the live database; it is left untouched (out of scope).
"""
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import Float, and_, column, func, or_, select, table, true
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai import embeddings
from app.core.exceptions import NotFoundError
from app.models.kb_document import KnowledgeBaseDocument
from app.utils.locale_data import format_money

logger = structlog.get_logger(__name__)

_kb_documents = table(
    "kb_documents", column("id"), column("tenant_id"), column("title"), column("body")
)
_faqs = table(
    "faqs",
    column("id"),
    column("tenant_id"),
    column("question"),
    column("answer"),
    column("enabled"),
)
# Business policies (SPEC-BE-048): enabled rows in effect today ground replies.
_policies = table(
    "policies",
    column("id"),
    column("tenant_id"),
    column("title"),
    column("body"),
    column("enabled"),
    column("effective_from"),
    column("effective_until"),
)
_brand_settings = table(
    "brand_settings",
    column("tenant_id"),
    column("brand_name"),
    column("voice_config"),
    column("forbidden_terms"),
    column("primary_language"),
)

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "could", "do", "does",
    "for", "from", "get", "had", "has", "have", "hello", "hey", "hi", "how", "i", "if",
    "in", "is", "it", "its", "just", "me", "my", "no", "not", "of", "on", "or", "our",
    "please", "so", "thanks", "that", "the", "their", "there", "this", "to", "was", "we",
    "what", "when", "where", "which", "who", "why", "will", "with", "would", "you", "your",
}
_MAX_KEYWORDS = 12
_SNIPPET_CHARS = 1200


@dataclass(frozen=True)
class GroundingSource:
    kind: str  # "kb_document" | "faq" | "policy"
    id: str
    title: str
    snippet: str
    score: float


@dataclass(frozen=True)
class BrandVoice:
    brand_name: str | None = None
    tone: int = 50
    style: int = 50
    primary_language: str = "en"
    forbidden_terms: list[str] = field(default_factory=list)


def retrieve_relevant_documents(
    db: Session, tenant_id: str, query: str, limit: int = 3
) -> list[KnowledgeBaseDocument]:
    return (
        db.query(KnowledgeBaseDocument)
        .filter(
            KnowledgeBaseDocument.tenant_id == tenant_id,
            KnowledgeBaseDocument.body.ilike(f"%{query}%"),  # live column (SPEC-BE-071 F6)
        )
        .limit(limit)
        .all()
    )


def _keywords(query: str) -> list[str]:
    # Lowercased alphanumeric tokens, stopwords and 1-char tokens dropped,
    # de-duplicated in order, capped at 12. Only [a-z0-9] reaches to_tsquery,
    # so user text can never inject tsquery operators.
    seen: list[str] = []
    for token in re.findall(r"[a-z0-9]+", query.lower()):
        if len(token) > 1 and token not in _STOPWORDS and token not in seen:
            seen.append(token)
    return seen[:_MAX_KEYWORDS]


# Meaning-based search (SPEC-BE-087): a semantic hit needs cosine >=
# EMBEDDINGS_MIN_SIMILARITY, so questions the knowledge doesn't cover still get
# the hand-over template. The value is model-specific: 0.70 was measured for
# gemini-embedding-001 on the golden set (answers 0.64-0.79, best wrong match of
# an unanswerable question 0.683).
SEMANTIC_TOP = 10
_RRF_K = 60


def retrieve_grounding(
    db: Session, tenant_id: str, query: str, limit: int = 5
) -> list[GroundingSource]:
    # Full-text search (below), plus, when embeddings are configured
    # (EMBEDDINGS_PROVIDER / EMBEDDINGS_API_KEY), meaning-based search over the
    # same sources merged by reciprocal rank fusion (SPEC-BE-087). With
    # embeddings off or failing, the result is exactly the full-text one.
    keyword = _fulltext(db, tenant_id, query, limit)
    model = embeddings.model_id()
    if model is None:
        return keyword
    try:
        with db.begin_nested():  # a DB error here never poisons the caller's transaction
            return _hybrid(db, tenant_id, query, limit, keyword, model)
    except (embeddings.EmbeddingError, SQLAlchemyError) as exc:
        logger.warning("retrieval_semantic_unavailable", tenant_id=tenant_id, reason=f"{type(exc).__name__}: {str(exc)[:200]}")
        return keyword


def _hybrid(
    db: Session, tenant_id: str, query: str, limit: int, keyword: list[GroundingSource], model: str
) -> list[GroundingSource]:
    from app.services import knowledge_index_service as index

    current = index.units(db, tenant_id)
    if not current:
        return keyword
    index.refresh(db, tenant_id, current, model)
    query_vector = embeddings.embed([query], "query")[0]
    from app.config import get_settings

    threshold = get_settings().EMBEDDINGS_MIN_SIMILARITY
    semantic = index.search(db, tenant_id, query_vector, current, model, threshold, SEMANTIC_TOP)
    fused: dict[tuple[str, str], float] = {}
    sources: dict[tuple[str, str], GroundingSource] = {}
    for rank, source in enumerate(keyword, start=1):
        key = (source.kind, source.id)
        fused[key] = fused.get(key, 0.0) + 1.0 / (_RRF_K + rank)
        sources[key] = source
    semantic_rank = 0
    seen: set[tuple[str, str]] = set()
    for unit, _similarity in semantic:
        key = (unit.kind, unit.source_id)
        if key in seen:
            continue  # a later chunk of the same KB document
        seen.add(key)
        semantic_rank += 1
        fused[key] = fused.get(key, 0.0) + 1.0 / (_RRF_K + semantic_rank)
        if key not in sources or unit.kind == "kb_document":
            # The matching chunk is the better snippet for a KB document.
            sources[key] = GroundingSource(kind=unit.kind, id=unit.source_id, title=unit.title, snippet=unit.snippet, score=0.0)
    ranked = sorted(fused, key=lambda k: (-fused[k], k[0], k[1]))[:limit]
    return [GroundingSource(kind=sources[k].kind, id=sources[k].id, title=sources[k].title, snippet=sources[k].snippet,
                            score=round(fused[k], 6)) for k in ranked]


def _fulltext(
    db: Session, tenant_id: str, query: str, limit: int = 5
) -> list[GroundingSource]:
    # Grounding for reply drafting (SPEC-BE-027): the tenant's kb_documents
    # (title + body) and enabled faqs (question + answer), every query filtered
    # by tenant_id. Relevance = Postgres full-text search: the query's keywords
    # OR-ed into to_tsquery('english', ...), ranked by ts_rank_cd; rows that do
    # not match (rank 0) are not relevant. Empty list when nothing matches.
    # SPEC-BE-048 adds the tenant's policies: enabled, and in effect now
    # (effective_from NULL or <= now, effective_until NULL or > now).
    keywords = _keywords(query)
    if not keywords:
        return []
    tsquery = func.to_tsquery("english", " | ".join(keywords))
    now = func.now()
    policy_in_effect = and_(
        _policies.c.enabled.is_(True),
        or_(_policies.c.effective_from.is_(None), _policies.c.effective_from <= now),
        or_(_policies.c.effective_until.is_(None), _policies.c.effective_until > now),
    )

    sources: list[GroundingSource] = []
    for kind, tbl, title_col, text_col, extra in (
        ("kb_document", _kb_documents, _kb_documents.c.title, _kb_documents.c.body, true()),
        ("faq", _faqs, _faqs.c.question, _faqs.c.answer, _faqs.c.enabled.is_(True)),
        ("policy", _policies, _policies.c.title, _policies.c.body, policy_in_effect),
    ):
        document = func.to_tsvector("english", func.concat_ws(" ", title_col, text_col))
        rank = func.ts_rank_cd(document, tsquery, type_=Float).label("rank")
        rows = db.execute(
            select(tbl.c.id, title_col.label("title"), text_col.label("text"), rank)
            .where(and_(tbl.c.tenant_id == tenant_id, extra, document.op("@@")(tsquery)))
            .order_by(rank.desc(), tbl.c.id)
            .limit(limit)
        ).all()
        sources.extend(
            GroundingSource(
                kind=kind,
                id=str(row.id),
                title=row.title,
                snippet=row.text[:_SNIPPET_CHARS],
                score=float(row.rank),
            )
            for row in rows
        )
    sources.sort(key=lambda s: (-s.score, s.kind, s.id))
    return sources[:limit]


def _voice_value(voice_config: dict[str, Any], key: str) -> int:
    value = voice_config.get(key)
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100:
        return value
    return 50


def get_brand_voice(db: Session, tenant_id: str) -> BrandVoice:
    # Brand voice for reply drafting (SPEC-BE-027), read from the caller
    # tenant's live brand_settings row (filtered by tenant_id): brand_name,
    # voice_config->'tone' and voice_config->'style' (integers 0-100 per
    # SPEC-BE-012's contract; missing/invalid -> 50), primary_language, and
    # forbidden_terms (text[]). No row -> BrandVoice() defaults (no brand name,
    # tone 50, style 50, "en", no forbidden terms).
    row = db.execute(
        select(
            _brand_settings.c.brand_name,
            _brand_settings.c.voice_config,
            _brand_settings.c.forbidden_terms,
            _brand_settings.c.primary_language,
        )
        .where(_brand_settings.c.tenant_id == tenant_id)
        .limit(1)
    ).first()
    if row is None:
        return BrandVoice()
    voice_config = row.voice_config if isinstance(row.voice_config, dict) else {}
    return BrandVoice(
        brand_name=row.brand_name or None,
        tone=_voice_value(voice_config, "tone"),
        style=_voice_value(voice_config, "style"),
        primary_language=row.primary_language or "en",
        forbidden_terms=[t for t in (row.forbidden_terms or []) if t and t.strip()],
    )


# Product context for ad-creative generation (SPEC-BE-029). Read from the live
# products table through a table() construct because the Product model does not
# map short_description / compare_at_price_cents (model files are out of scope).
_products = table(
    "products",
    column("tenant_id"),
    column("sku"),
    column("title"),
    column("short_description"),
    column("description"),
    column("default_price_cents"),
    column("compare_at_price_cents"),
    column("currency"),
    column("status"),
    column("deleted_at"),
)
_SUMMARY_CHARS = 300


@dataclass(frozen=True)
class ProductContext:
    sku: str
    title: str
    summary: str  # short_description, else description; capped at 300 chars
    price: str  # e.g. "৳1,250.00" or "¥1,250" - utils.locale_data.format_money (SPEC-BE-072)
    compare_at_price: str | None
    status: str


def _money(cents: int | None, currency: str) -> str | None:
    # SPEC-BE-072: the currency's own symbol and decimals ("৳1,850.00", "¥1,500").
    return None if cents is None else format_money(cents, currency)


def get_products_by_sku(
    db: Session, tenant_id: str, skus: Sequence[str]
) -> list[ProductContext]:
    # The caller tenant's non-deleted products whose sku is in `skus`, in the
    # requested order. Filtered by tenant_id, so another tenant's product with
    # the same sku is never returned. SKUs that are not found are simply
    # absent; the caller decides how to treat them.
    if not skus:
        return []
    rows = db.execute(
        select(_products).where(
            _products.c.tenant_id == tenant_id,
            _products.c.sku.in_(list(skus)),
            _products.c.deleted_at.is_(None),
        )
    ).all()
    by_sku = {
        row.sku: ProductContext(
            sku=row.sku,
            title=row.title,
            summary=(row.short_description or row.description or "")[:_SUMMARY_CHARS],
            price=_money(row.default_price_cents, row.currency) or "",
            compare_at_price=_money(row.compare_at_price_cents, row.currency),
            status=row.status,
        )
        for row in rows
    }
    return [by_sku[sku] for sku in skus if sku in by_sku]


# Tenant spend limits for plan generation (SPEC-BE-032). Read from the live
# tenants table through a table() construct because the Tenant model does not
# match the live schema. Filtered by the tenant's own id.
_tenants = table(
    "tenants",
    column("id"),
    column("currency"),
    column("ad_daily_cap_cents"),
    column("llm_daily_cap_cents"),
)


@dataclass(frozen=True)
class TenantLimits:
    currency: str  # tenants.currency (ISO 4217)
    ad_daily_cap_cents: int  # tenants.ad_daily_cap_cents
    llm_daily_cap_cents: int  # tenants.llm_daily_cap_cents


def get_tenant_limits(db: Session, tenant_id: str) -> TenantLimits:
    row = db.execute(
        select(
            _tenants.c.currency, _tenants.c.ad_daily_cap_cents, _tenants.c.llm_daily_cap_cents
        ).where(_tenants.c.id == tenant_id)
    ).first()
    if row is None:
        raise NotFoundError("Tenant not found.")
    return TenantLimits(
        currency=row.currency.strip(),
        ad_daily_cap_cents=int(row.ad_daily_cap_cents),
        llm_daily_cap_cents=int(row.llm_daily_cap_cents),
    )
