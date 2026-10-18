"""Command Chat history and Projects (SPEC-BE-099).

Each conversation is an `orchestrator_chats` row; its messages carry
`session_id = chat.id` (a live column that was unused before). Projects hold
instructions and knowledge files for their chats. Everything is private (the
user's choice): a chat or project is visible only to the user who made it;
anyone else's is 404, like another company's.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.exceptions import AppError, NotFoundError
from app.models.orchestrator import OrchestratorChat, OrchestratorFile, OrchestratorMessage, OrchestratorProject

logger = structlog.get_logger(__name__)

TITLE_MAX = 60
PROJECT_FILES_MAX = 20
INSTRUCTIONS_MAX = 4000
PROJECT_TEXT_MAX = 12_000  # project file text sent to the planner per message
NEW_TITLE = "New chat"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime | None) -> datetime | None:
    return value.astimezone(timezone.utc) if value else None


def _uuid_or_404(value: str | None, what: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError):
        raise NotFoundError(f"{what} not found.") from None


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------
def require_project(db: Session, tenant_id: str, user_id: str, project_id: str) -> OrchestratorProject:
    pid = _uuid_or_404(project_id, "Project")
    row = db.query(OrchestratorProject).filter(
        OrchestratorProject.id == pid, OrchestratorProject.tenant_id == tenant_id,
        OrchestratorProject.created_by == user_id).first()
    if row is None:
        raise NotFoundError("Project not found.")
    return row


def _project_files(db: Session, tenant_id: str, project_id: str) -> list[OrchestratorFile]:
    return (db.query(OrchestratorFile)
            .filter(OrchestratorFile.tenant_id == tenant_id, OrchestratorFile.project_id == project_id,
                    OrchestratorFile.status == "extracted")
            .order_by(OrchestratorFile.created_at.asc()).all())


def project_dict(db: Session, row: OrchestratorProject, with_files: bool = False) -> dict[str, Any]:
    tenant_id = str(row.tenant_id)
    stats = db.query(func.count(OrchestratorChat.id), func.max(OrchestratorChat.last_message_at)).filter(
        OrchestratorChat.tenant_id == tenant_id, OrchestratorChat.project_id == str(row.id),
        OrchestratorChat.deleted_at.is_(None)).one()
    out: dict[str, Any] = {
        "id": str(row.id), "name": row.name, "description": row.description or "", "instructions": row.instructions or "",
        "emoji": row.emoji or "📁", "archived": row.archived_at is not None, "chat_count": int(stats[0] or 0),
        "last_activity_at": _utc(stats[1]) or _utc(row.updated_at), "created_at": _utc(row.created_at),
    }
    if with_files:
        from app.services.file_extract_service import file_dict

        out["files"] = [file_dict(f) for f in _project_files(db, tenant_id, str(row.id))]
    return out


def list_projects(db: Session, tenant_id: str, user_id: str, archived: bool = False) -> list[dict[str, Any]]:
    q = db.query(OrchestratorProject).filter(OrchestratorProject.tenant_id == tenant_id,
                                             OrchestratorProject.created_by == user_id)
    q = q.filter(OrchestratorProject.archived_at.isnot(None) if archived else OrchestratorProject.archived_at.is_(None))
    rows = [project_dict(db, r) for r in q.all()]
    rows.sort(key=lambda p: p["last_activity_at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return rows


def create_project(db: Session, tenant_id: str, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
    row = OrchestratorProject(tenant_id=tenant_id, created_by=user_id, name=data["name"].strip(),
                              description=(data.get("description") or "").strip() or None,
                              instructions=(data.get("instructions") or "").strip() or None,
                              emoji=(data.get("emoji") or "").strip() or None)
    db.add(row)
    db.flush()
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=user_id, action="orchestrator.project_created",
                    resource_type="orchestrator_project", resource_id=str(row.id), metadata={"name": row.name})
    db.refresh(row)
    return project_dict(db, row, with_files=True)


def get_project(db: Session, tenant_id: str, user_id: str, project_id: str) -> dict[str, Any]:
    return project_dict(db, require_project(db, tenant_id, user_id, project_id), with_files=True)


def update_project(db: Session, tenant_id: str, user_id: str, project_id: str, data: dict[str, Any]) -> dict[str, Any]:
    row = require_project(db, tenant_id, user_id, project_id)
    for key in ("name", "description", "instructions", "emoji"):
        if key in data and data[key] is not None:
            value = str(data[key]).strip()
            if key == "name" and not value:
                raise AppError("A project needs a name.", 422)
            setattr(row, key, value or None)
    if "archived" in data and data["archived"] is not None:
        row.archived_at = _now() if data["archived"] else None
    row.updated_at = _now()
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=user_id, action="orchestrator.project_updated",
                    resource_type="orchestrator_project", resource_id=str(row.id),
                    metadata={"fields": sorted(k for k in data if data[k] is not None)})
    db.refresh(row)
    return project_dict(db, row, with_files=True)


def archive_project(db: Session, tenant_id: str, user_id: str, project_id: str) -> None:
    """Delete = archive: the project disappears from the list; its chats stay,
    outside any project, and its files stay in storage."""
    row = require_project(db, tenant_id, user_id, project_id)
    row.archived_at = _now()
    db.query(OrchestratorChat).filter(OrchestratorChat.tenant_id == tenant_id,
                                      OrchestratorChat.project_id == str(row.id)).update({"project_id": None})
    db.query(OrchestratorFile).filter(OrchestratorFile.tenant_id == tenant_id,
                                      OrchestratorFile.project_id == str(row.id)).update({"project_id": None})
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=user_id, action="orchestrator.project_archived",
                    resource_type="orchestrator_project", resource_id=str(row.id), metadata={})


def add_project_file(db: Session, tenant_id: str, user_id: str, project_id: str, file_id: str) -> dict[str, Any]:
    from app.services.file_extract_service import require as require_file

    row = require_project(db, tenant_id, user_id, project_id)
    f = require_file(db, tenant_id, file_id)
    if f.user_id and str(f.user_id) != str(user_id):
        raise NotFoundError("File not found.")
    if f.status != "extracted":
        raise AppError(f"{f.name} couldn't be read, so it can't be a project file.", 422)
    if len(_project_files(db, tenant_id, str(row.id))) >= PROJECT_FILES_MAX and f.project_id != str(row.id):
        raise AppError(f"A project holds at most {PROJECT_FILES_MAX} files.", 422)
    f.project_id = str(row.id)
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return project_dict(db, row, with_files=True)


def remove_project_file(db: Session, tenant_id: str, user_id: str, project_id: str, file_id: str) -> dict[str, Any]:
    row = require_project(db, tenant_id, user_id, project_id)
    fid = _uuid_or_404(file_id, "File")
    f = db.query(OrchestratorFile).filter(OrchestratorFile.tenant_id == tenant_id, OrchestratorFile.id == fid,
                                          OrchestratorFile.project_id == str(row.id)).first()
    if f is None:
        raise NotFoundError("File not found.")
    f.project_id = None
    db.commit()
    db.refresh(row)
    return project_dict(db, row, with_files=True)


def project_context(db: Session, tenant_id: str, project_id: str | None) -> tuple[dict[str, Any] | None, str, list[OrchestratorFile]]:
    """(planner context block, evidence text, files) for a chat's project. The
    instructions are data under the planner's rules; file values count as the
    user's (SPEC-BE-085 evidence)."""
    if not project_id:
        return None, "", []
    row = db.query(OrchestratorProject).filter(OrchestratorProject.id == project_id,
                                               OrchestratorProject.tenant_id == tenant_id).first()
    if row is None or row.archived_at is not None:
        return None, "", []
    files = _project_files(db, tenant_id, str(row.id))
    texts: list[str] = []
    records: list[dict[str, Any]] = []
    for f in files:
        ex = f.extracted or {}
        texts += [c["text"] for c in ex.get("text_chunks") or []]
        records += [r for r in ex.get("records") or [] if isinstance(r, dict)]
    joined = "\n\n".join(texts)
    block = {
        "name": row.name,
        "description": row.description or "",
        "instructions": (row.instructions or "")[:INSTRUCTIONS_MAX],
        "files": [{"name": f.name, "summary": (f.extracted or {}).get("summary") or ""} for f in files],
        "file_text_excerpt": joined[:PROJECT_TEXT_MAX],
        "file_records": records[:100],
    }
    evidence = "\n".join([row.instructions or "", joined, *(str(r) for r in records)])
    return block, evidence[:400_000], files


# ---------------------------------------------------------------------------
# Chats
# ---------------------------------------------------------------------------
def require_chat(db: Session, tenant_id: str, user_id: str, chat_id: str) -> OrchestratorChat:
    cid = _uuid_or_404(chat_id, "Chat")
    row = db.query(OrchestratorChat).filter(
        OrchestratorChat.id == cid, OrchestratorChat.tenant_id == tenant_id, OrchestratorChat.user_id == user_id,
        OrchestratorChat.deleted_at.is_(None)).first()
    if row is None:
        raise NotFoundError("Chat not found.")
    return row


def _visible(db: Session, chat_ids: list[str]) -> dict[str, tuple[int, str]]:
    """(message count, preview) per chat: user/AI messages only."""
    if not chat_ids:
        return {}
    counts: dict[str, int] = {
        str(cid): int(n)
        for cid, n in db.query(OrchestratorMessage.session_id, func.count(OrchestratorMessage.id))
        .filter(OrchestratorMessage.session_id.in_(chat_ids), OrchestratorMessage.role.in_(("user", "assistant", "ai")))
        .group_by(OrchestratorMessage.session_id).all()
    }
    out: dict[str, tuple[int, str]] = {}
    for cid in chat_ids:
        last = (db.query(OrchestratorMessage.content)
                .filter(OrchestratorMessage.session_id == cid, OrchestratorMessage.role.in_(("user", "assistant", "ai")))
                .order_by(OrchestratorMessage.created_at.desc(), OrchestratorMessage.id.desc()).first())
        out[str(cid)] = (int(counts.get(cid, 0)), " ".join(str(last[0]).split())[:120] if last else "")
    return out


def chat_dict(db: Session, row: OrchestratorChat, extra: tuple[int, str] | None = None) -> dict[str, Any]:
    if extra is None:
        extra = _visible(db, [str(row.id)]).get(str(row.id), (0, ""))
    project = None
    if row.project_id:
        p = db.query(OrchestratorProject).filter(OrchestratorProject.id == row.project_id).first()
        if p is not None and p.archived_at is None:
            project = {"id": str(p.id), "name": p.name, "emoji": p.emoji or "📁"}
    return {
        "id": str(row.id), "title": row.title, "title_source": row.title_source, "project": project, "pinned": bool(row.pinned),
        "archived": row.archived_at is not None, "message_count": extra[0], "preview": extra[1],
        "last_message_at": _utc(row.last_message_at), "created_at": _utc(row.created_at),
    }


def list_chats(db: Session, tenant_id: str, user_id: str, q: str | None = None, project_id: str | None = None,
               archived: bool = False, limit: int = 50, before: datetime | None = None) -> dict[str, Any]:
    query = db.query(OrchestratorChat).filter(OrchestratorChat.tenant_id == tenant_id, OrchestratorChat.user_id == user_id,
                                              OrchestratorChat.deleted_at.is_(None))
    query = query.filter(OrchestratorChat.archived_at.isnot(None) if archived else OrchestratorChat.archived_at.is_(None))
    if project_id:
        require_project(db, tenant_id, user_id, project_id)
        query = query.filter(OrchestratorChat.project_id == project_id)
    if q and q.strip():
        like = f"%{q.strip()}%"
        in_messages = (db.query(OrchestratorMessage.session_id)
                       .filter(OrchestratorMessage.tenant_id == tenant_id, OrchestratorMessage.content.ilike(like),
                               OrchestratorMessage.role.in_(("user", "assistant", "ai"))))
        query = query.filter(or_(OrchestratorChat.title.ilike(like), OrchestratorChat.id.in_(in_messages)))
    activity = func.coalesce(OrchestratorChat.last_message_at, OrchestratorChat.created_at)
    if before is not None:
        query = query.filter(activity < before)
    rows = query.order_by(OrchestratorChat.pinned.desc(), activity.desc()).limit(limit + 1).all()
    more = len(rows) > limit
    rows = rows[:limit]
    extra = _visible(db, [str(r.id) for r in rows])
    return {"items": [chat_dict(db, r, extra.get(str(r.id))) for r in rows], "has_more": more}


def create_chat(db: Session, tenant_id: str, user_id: str, project_id: str | None = None) -> OrchestratorChat:
    if project_id:
        project = require_project(db, tenant_id, user_id, project_id)
        if project.archived_at is not None:
            raise AppError("That project is archived.", 409)
    row = OrchestratorChat(tenant_id=tenant_id, user_id=user_id, project_id=project_id or None, title=NEW_TITLE,
                           title_source="auto")
    db.add(row)
    db.flush()
    return row


def update_chat(db: Session, tenant_id: str, user_id: str, chat_id: str, data: dict[str, Any]) -> dict[str, Any]:
    row = require_chat(db, tenant_id, user_id, chat_id)
    if data.get("title") is not None:
        title = " ".join(str(data["title"]).split())[:TITLE_MAX]
        if not title:
            raise AppError("A chat needs a title.", 422)
        row.title, row.title_source = title, "manual"
    if data.get("pinned") is not None:
        row.pinned = bool(data["pinned"])
    if "project_id" in data:
        pid = data["project_id"]
        if pid:
            project = require_project(db, tenant_id, user_id, pid)
            if project.archived_at is not None:
                raise AppError("That project is archived.", 409)
        row.project_id = pid or None
    if data.get("archived") is not None:
        row.archived_at = _now() if data["archived"] else None
    db.commit()
    db.refresh(row)
    return chat_dict(db, row)


def delete_chat(db: Session, tenant_id: str, user_id: str, chat_id: str) -> None:
    """Soft delete: hidden from every list; messages stay for audit, running
    plans keep running and their approvals stay in Pending Approvals."""
    row = require_chat(db, tenant_id, user_id, chat_id)
    row.deleted_at = _now()
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=user_id, action="orchestrator.chat_deleted",
                    resource_type="orchestrator_chat", resource_id=str(row.id), metadata={"title": row.title})


def latest_chat(db: Session, tenant_id: str, user_id: str) -> OrchestratorChat | None:
    return (db.query(OrchestratorChat)
            .filter(OrchestratorChat.tenant_id == tenant_id, OrchestratorChat.user_id == user_id,
                    OrchestratorChat.deleted_at.is_(None), OrchestratorChat.archived_at.is_(None))
            .order_by(func.coalesce(OrchestratorChat.last_message_at, OrchestratorChat.created_at).desc()).first())


def chat_for_send(db: Session, tenant_id: str, user_id: str, chat_id: str | None, project_id: str | None = None,
                  new_chat: bool = False) -> OrchestratorChat:
    """The chat a new message goes into: the given one (yours, not deleted); a
    new one when asked (`new_chat`, or starting in `project_id`); otherwise
    the user's latest chat, so older clients and multi-turn callers that send
    no chat id keep one continuous conversation."""
    if chat_id:
        row = require_chat(db, tenant_id, user_id, chat_id)
        if row.archived_at is not None:
            row.archived_at = None  # writing into an archived chat brings it back
        return row
    if not new_chat and not project_id:
        latest = latest_chat(db, tenant_id, user_id)
        if latest is not None:
            return latest
    return create_chat(db, tenant_id, user_id, project_id)


def touch(db: Session, chat: OrchestratorChat, first_message: str | None = None) -> bool:
    """Marks activity; on the first message sets the first-words title.
    True when an AI title should be written."""
    chat.last_message_at = _now()
    if first_message is not None and chat.title_source == "auto" and chat.title == NEW_TITLE:
        words = " ".join(first_message.split())
        chat.title = (words[: TITLE_MAX - 1] + "…") if len(words) > TITLE_MAX else (words or NEW_TITLE)
        return True
    return False


def chat_of_correlation(db: Session, tenant_id: str, correlation_id: str) -> str | None:
    """The chat of a plan's conversation turn: summaries and progress lines of a
    plan go into the chat whose message started it."""
    row = (db.query(OrchestratorMessage.session_id)
           .filter(OrchestratorMessage.tenant_id == tenant_id, OrchestratorMessage.correlation_id == correlation_id,
                   OrchestratorMessage.session_id.isnot(None))
           .order_by(OrchestratorMessage.created_at.asc()).first())
    return str(row[0]) if row and row[0] else None


_TITLE_SYSTEM = ("You name chat conversations. Write a short, specific title (2 to 6 words) for a chat that starts with the "
                 "user's message, in the same language and script as the message. No quotes, no emoji, no ending period. "
                 "Reply with the title only.")


def write_ai_title(db: Session, tenant_id: str, chat_id: str, first_message: str) -> None:
    """Background job: the company's AI text chain titles the chat. Keeps the
    first-words title when the AI fails or the user renamed the chat meanwhile."""
    from app.ai.llm_client import LLMProviderError, llm_client

    try:
        out = llm_client.complete_with_usage(_TITLE_SYSTEM, f"<message>\n{first_message[:1500]}\n</message>", 40, 20.0,
                                             db=db, tenant_id=tenant_id)
        if out.is_mock:
            return
        title = re.sub(r"^[\"'“”«»]+|[\"'“”«».!]+$", "", " ".join(out.text.split())).strip()[:TITLE_MAX]
    except LLMProviderError as exc:
        logger.info("chat_title_ai_failed", tenant_id=tenant_id, chat_id=chat_id, error=str(exc)[:120])
        return
    if not title:
        return
    row = db.query(OrchestratorChat).filter(OrchestratorChat.id == chat_id, OrchestratorChat.tenant_id == tenant_id).first()
    if row is None or row.title_source != "auto":
        return
    row.title, row.title_source = title, "ai"
    db.commit()
    logger.info("chat_titled", tenant_id=tenant_id, chat_id=chat_id)
