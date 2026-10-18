"""/orchestrator endpoints (Command Chat messages and plans)."""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.orchestrator import (
    ChatMessage,
    ChatCreate,
    ChatList,
    ChatMessageCreate,
    ChatRead,
    ChatUpdate,
    FileDetail,
    FileRead,
    ItemEdit,
    JobCreate,
    JobSchedule,
    PlanActionEdit,
    PlanRead,
    ProjectCreate,
    ProjectFileAdd,
    ProjectRead,
    ProjectUpdate,
    SendMessageResult,
    SpeechRead,
    SpeechRequest,
    TranscriptRead,
)
from app.ai import speech
from app.services import chat_service, file_extract_service, job_board_service, orchestrator_service

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


@router.get("/messages", response_model=list[ChatMessage], status_code=status.HTTP_200_OK)
def list_messages(
    chat_id: str | None = Query(default=None, max_length=36),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[dict[str, Any]]:
    # A chat's messages (SPEC-BE-099); without chat_id, the user's latest chat (older clients).
    tenant_id, user_id = str(current_user.tenant_id), str(current_user.id)
    if chat_id:
        chat_service.require_chat(db, tenant_id, user_id, chat_id)
        return orchestrator_service.list_messages(db, tenant_id, chat_id)
    latest = chat_service.latest_chat(db, tenant_id, user_id)
    return orchestrator_service.list_messages(db, tenant_id, str(latest.id)) if latest else []


# Sending stores the user message, then plans it (SPEC-BE-059): a clarifying
# question, or a plan whose read/draft steps start right away in the background
# and whose change/spend steps wait for approval per the policy.
@router.post("/messages", response_model=SendMessageResult, status_code=status.HTTP_201_CREATED)
def send_message(
    payload: ChatMessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return orchestrator_service.send_message_and_plan(
        db,
        str(current_user.tenant_id),
        str(current_user.id),
        payload.body,
        current_user.role,
        voice=payload.voice is not None,
        voice_language=speech.language_code(payload.voice.language) if payload.voice else None,
        file_ids=payload.file_ids,
        chat_id=payload.chat_id,
        project_id=payload.project_id,
        new_chat=payload.new_chat,
    )


# ---- Chat history (SPEC-BE-099): the user's own chats only. ----
@router.get("/chats", response_model=ChatList, status_code=status.HTTP_200_OK)
def list_chats(
    q: str | None = Query(default=None, max_length=200),
    project_id: str | None = Query(default=None, max_length=36),
    archived: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    before: datetime | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return chat_service.list_chats(db, str(current_user.tenant_id), str(current_user.id), q, project_id, archived, limit, before)


@router.post("/chats", response_model=ChatRead, status_code=status.HTTP_201_CREATED)
def create_chat(payload: ChatCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    row = chat_service.create_chat(db, str(current_user.tenant_id), str(current_user.id), payload.project_id)
    db.commit()
    db.refresh(row)
    return chat_service.chat_dict(db, row)


@router.get("/chats/{chat_id}", response_model=ChatRead, status_code=status.HTTP_200_OK)
def get_chat(chat_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return chat_service.chat_dict(db, chat_service.require_chat(db, str(current_user.tenant_id), str(current_user.id), chat_id))


@router.get("/chats/{chat_id}/messages", response_model=list[ChatMessage], status_code=status.HTTP_200_OK)
def chat_messages(chat_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    chat_service.require_chat(db, str(current_user.tenant_id), str(current_user.id), chat_id)
    return orchestrator_service.list_messages(db, str(current_user.tenant_id), chat_id)


@router.patch("/chats/{chat_id}", response_model=ChatRead, status_code=status.HTTP_200_OK)
def update_chat(chat_id: str, payload: ChatUpdate, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return chat_service.update_chat(db, str(current_user.tenant_id), str(current_user.id), chat_id,
                                    payload.model_dump(include=payload.model_fields_set))


@router.delete("/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_chat(chat_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> None:
    chat_service.delete_chat(db, str(current_user.tenant_id), str(current_user.id), chat_id)


# ---- Projects (SPEC-BE-099): the user's own projects only. ----
@router.get("/projects", response_model=list[ProjectRead], status_code=status.HTTP_200_OK)
def list_projects(archived: bool = False, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    return chat_service.list_projects(db, str(current_user.tenant_id), str(current_user.id), archived)


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return chat_service.create_project(db, str(current_user.tenant_id), str(current_user.id), payload.model_dump())


@router.get("/projects/{project_id}", response_model=ProjectRead, status_code=status.HTTP_200_OK)
def get_project(project_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return chat_service.get_project(db, str(current_user.tenant_id), str(current_user.id), project_id)


@router.patch("/projects/{project_id}", response_model=ProjectRead, status_code=status.HTTP_200_OK)
def update_project(project_id: str, payload: ProjectUpdate, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return chat_service.update_project(db, str(current_user.tenant_id), str(current_user.id), project_id,
                                       payload.model_dump(include=payload.model_fields_set))


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def archive_project(project_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> None:
    chat_service.archive_project(db, str(current_user.tenant_id), str(current_user.id), project_id)


@router.post("/projects/{project_id}/files", response_model=ProjectRead, status_code=status.HTTP_200_OK)
def add_project_file(project_id: str, payload: ProjectFileAdd, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return chat_service.add_project_file(db, str(current_user.tenant_id), str(current_user.id), project_id, payload.file_id)


@router.delete("/projects/{project_id}/files/{file_id}", response_model=ProjectRead, status_code=status.HTTP_200_OK)
def remove_project_file(project_id: str, file_id: str, db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return chat_service.remove_project_file(db, str(current_user.tenant_id), str(current_user.id), project_id, file_id)


# Chat attachments (SPEC-BE-096): one file per call (the chat uploads several
# at once). It is stored and read right away; the answer has its summary.
@router.post("/files", response_model=FileRead, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    content = await file.read(file_extract_service.MAX_FILE_BYTES + 1)
    return file_extract_service.upload(db, str(current_user.tenant_id), str(current_user.id), file.filename or "", content)


@router.get("/files/{file_id}", response_model=FileDetail, status_code=status.HTTP_200_OK)
def get_file(
    file_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return file_extract_service.file_dict(file_extract_service.require(db, str(current_user.tenant_id), file_id), preview=True)


# Voice commands (SPEC-BE-095): the recording becomes text on the company's own
# OpenAI / Groq / Gemini key; the chat then sends that text like a typed command.
@router.post("/voice/transcribe", response_model=TranscriptRead, status_code=status.HTTP_200_OK)
async def transcribe_voice(
    audio: UploadFile = File(...),
    # The browser's languages (navigator.languages, comma-separated): a hint, never a rule.
    languages: str | None = Form(default=None, max_length=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    content = await audio.read(speech.MAX_AUDIO_BYTES + 1)
    browser = [x.strip() for x in (languages or "").split(",") if x.strip()][:6]
    return speech.transcribe(db, str(current_user.tenant_id), content, audio.content_type, browser)


# An AI reply read aloud in the voice command's language (SPEC-BE-095).
@router.post("/messages/{message_id}/speech", response_model=SpeechRead, status_code=status.HTTP_200_OK)
def speak_message(
    message_id: str,
    payload: SpeechRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return orchestrator_service.speak_message(db, str(current_user.tenant_id), message_id, payload.language, str(current_user.id))


@router.get("/plans/{plan_id}", response_model=PlanRead, status_code=status.HTTP_200_OK)
def get_plan(
    plan_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return orchestrator_service.get_plan(db, str(current_user.tenant_id), plan_id)


@router.patch("/plans/{plan_id}/actions/{index}", response_model=PlanRead, status_code=status.HTTP_200_OK)
def edit_plan_action(
    plan_id: str,
    index: int,
    payload: PlanActionEdit,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return orchestrator_service.edit_action(
        db, str(current_user.tenant_id), str(current_user.id), current_user.role, plan_id, index, payload.params, payload.run_at
    )


# ---- Job lists (SPEC-BE-097): review and edit a draft, schedule, submit, then pause/resume/cancel/retry.
@router.delete("/plans/{plan_id}/actions/{index}", response_model=PlanRead, status_code=status.HTTP_200_OK)
def remove_job(
    plan_id: str, index: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("manager"))
) -> dict[str, Any]:
    return job_board_service.remove_job(db, str(current_user.tenant_id), plan_id, index)


@router.post("/plans/{plan_id}/actions", response_model=PlanRead, status_code=status.HTTP_201_CREATED)
def add_job(
    plan_id: str, payload: JobCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("manager"))
) -> dict[str, Any]:
    return job_board_service.add_job(db, str(current_user.tenant_id), str(current_user.id), current_user.role, plan_id,
                                     payload.type, payload.params, payload.description, payload.item_key, payload.depends_on,
                                     payload.run_at)


@router.patch("/plans/{plan_id}/items/{key}", response_model=PlanRead, status_code=status.HTTP_200_OK)
def edit_item(
    plan_id: str, key: str, payload: ItemEdit, db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return job_board_service.edit_item(db, str(current_user.tenant_id), str(current_user.id), current_user.role, plan_id,
                                       key, payload.fields)


@router.patch("/plans/{plan_id}/schedule", response_model=PlanRead, status_code=status.HTTP_200_OK)
def set_schedule(
    plan_id: str, payload: JobSchedule, db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return job_board_service.set_schedule(db, str(current_user.tenant_id), plan_id, payload.model_dump(exclude_none=True))


# Submitting applies the normal approval policy per job, so any role may submit:
# change jobs then wait for a manager, spend jobs for the owner.
@router.post("/plans/{plan_id}/submit", response_model=PlanRead, status_code=status.HTTP_200_OK)
def submit_job_list(
    plan_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return job_board_service.submit(db, str(current_user.tenant_id), str(current_user.id), current_user.role, plan_id)


@router.post("/plans/{plan_id}/{op}", response_model=PlanRead, status_code=status.HTTP_200_OK)
def control_job_list(
    plan_id: str, op: str, db: Session = Depends(get_db), current_user: User = Depends(require_permission("manager"))
) -> dict[str, Any]:
    ops = {"pause": job_board_service.pause, "resume": job_board_service.resume, "cancel": job_board_service.cancel,
           "retry-failed": job_board_service.retry_failed}
    if op not in ops:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("Not found.")
    return ops[op](db, str(current_user.tenant_id), str(current_user.id), plan_id)


@router.post("/plans/{plan_id}/actions/{index}/skip", response_model=PlanRead, status_code=status.HTTP_200_OK)
def skip_plan_action(
    plan_id: str,
    index: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    """SPEC-BE-102: take one job out without cancelling the list."""
    return orchestrator_service.skip_action(db, str(current_user.tenant_id), str(current_user.id), plan_id, index)


@router.post("/plans/{plan_id}/actions/{index}/retry", response_model=PlanRead, status_code=status.HTTP_200_OK)
def retry_plan_action(
    plan_id: str,
    index: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manager")),
) -> dict[str, Any]:
    return orchestrator_service.retry_action(db, str(current_user.tenant_id), str(current_user.id), plan_id, index)


@router.post("/draft/discard", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def discard_draft(
    chat_id: str | None = Query(default=None, max_length=36),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
) -> None:
    tenant_id, user_id = str(current_user.tenant_id), str(current_user.id)
    if chat_id:
        chat_service.require_chat(db, tenant_id, user_id, chat_id)
    else:  # older clients: the user's latest chat
        latest = chat_service.latest_chat(db, tenant_id, user_id)
        chat_id = str(latest.id) if latest else None
    orchestrator_service.discard_draft(db, tenant_id, user_id, chat_id)
