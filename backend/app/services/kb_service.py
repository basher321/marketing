"""Knowledge base ingestion, retrieval."""
from sqlalchemy.orm import Session

from app.ai.retrieval import retrieve_relevant_documents
from app.models.kb_document import KnowledgeBaseDocument


def list_documents(db: Session, tenant_id: str) -> list[KnowledgeBaseDocument]:
    return db.query(KnowledgeBaseDocument).filter(KnowledgeBaseDocument.tenant_id == tenant_id).all()


def ingest_document(db: Session, tenant_id: str, title: str, content: str, source_url: str | None = None) -> KnowledgeBaseDocument:
    # SPEC-BE-071 F6: the live column is `body`; document_type is required.
    document = KnowledgeBaseDocument(
        tenant_id=tenant_id, title=title, body=content, source_url=source_url, document_type="note", extra_metadata={}
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def search(db: Session, tenant_id: str, query: str) -> list[KnowledgeBaseDocument]:
    return retrieve_relevant_documents(db, tenant_id, query)
