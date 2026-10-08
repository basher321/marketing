"""Media library routes (SPEC-BE-074).

/media/f/{token} is the only unauthenticated route: the signed token is the
access check (403 bad, 410 expired). It supports Range requests so videos
can be scrubbed in the browser and fetched in parts by platforms.
"""
import re
from typing import Any

from fastapi import APIRouter, Depends, File, Header, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.db.session import get_db
from app.dependencies import get_current_user, require_permission
from app.integrations.storage import StorageError, get_storage
from app.models.user import User
from app.schemas import media as s
from app.services import media_service as svc

router = APIRouter(tags=["media"])
Agent = Depends(require_permission("agent"))
Manager = Depends(require_permission("manager"))
RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def _t(user: User) -> str:
    return str(user.tenant_id)


@router.post("/media", response_model=s.MediaOut, status_code=status.HTTP_201_CREATED)
async def upload(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Agent) -> dict[str, Any]:
    content = await file.read(svc.VIDEO_MAX + 1)
    return svc.upload(db, _t(user), str(user.id), file.filename or "", content)


@router.get("/media", response_model=s.MediaList, status_code=status.HTTP_200_OK)
def list_media(
    kind: str | None = Query(default=None, pattern="^(image|video)$"),
    source: str | None = Query(default=None, pattern="^(upload|ai_image|ai_video|catalog|derived)$"),
    q: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return svc.list_media(db, _t(user), kind, source, q, page)


@router.get("/media/f/{token}", status_code=status.HTTP_200_OK, response_class=Response)
def serve(token: str, range_header: str | None = Header(default=None, alias="Range"), db: Session = Depends(get_db)) -> Response:
    media_id = svc.verify_token(token)
    asset = svc.public_lookup(db, media_id)
    size = int(asset.bytes)
    start, end = 0, size - 1
    partial = False
    if range_header:
        m = RANGE_RE.match(range_header.strip())
        if not m or (not m.group(1) and not m.group(2)):
            raise AppError("Invalid Range.", 416)
        if m.group(1):
            start = int(m.group(1))
            end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
        else:
            start = max(0, size - int(m.group(2)))
        if start > end or start >= size:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        partial = True
    try:
        body = get_storage().open_range(asset.storage_key, start, end)
    except StorageError as exc:
        raise AppError(str(exc), 502) from None
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
        "Cache-Control": "private, max-age=3600",
        "X-Content-Type-Options": "nosniff",
    }
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(body, status_code=206 if partial else 200, media_type=asset.mime, headers=headers)


@router.get("/media/{media_id}", response_model=s.MediaOut, status_code=status.HTTP_200_OK)
def get_media(media_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    return svc.get_media(db, _t(user), media_id)


@router.post("/media/{media_id}/derive", response_model=s.MediaOut, status_code=status.HTTP_201_CREATED)
def derive(media_id: str, payload: s.DeriveRequest, db: Session = Depends(get_db), user: User = Agent) -> dict[str, Any]:
    return svc.media_dict(svc.derive(db, _t(user), str(user.id), media_id, payload.ratio, payload.mode))


@router.delete("/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete(media_id: str, db: Session = Depends(get_db), user: User = Manager) -> Response:
    svc.delete(db, _t(user), str(user.id), media_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
