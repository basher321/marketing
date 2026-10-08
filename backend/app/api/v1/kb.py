"""/kb/documents endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.kb_document import KnowledgeBaseDocument
from app.models.user import User
from app.services import kb_service

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


@router.get("/documents")
def list_documents(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    docs: list[KnowledgeBaseDocument] = kb_service.list_documents(db, current_user.tenant_id)
    return [{"id": d.id, "title": d.title, "embedding_status": d.embedding_status} for d in docs]


@router.post("/documents", status_code=201)
def ingest_document(
    title: str, content: str, db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),  # SPEC-BE-071 F5
):
    doc = kb_service.ingest_document(db, current_user.tenant_id, title, content)
    return {"id": doc.id, "title": doc.title}
