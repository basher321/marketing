"""Media library (SPEC-BE-074): uploads, AI results and derivatives, stored
through integrations/storage.py and shared through signed URLs.

Signed URL: {PUBLIC_BASE_URL}/api/v1/media/f/{media_id}.{expires}.{sig}, where
sig = HMAC-SHA256(SECRET_KEY, "media:{media_id}.{expires}") (hex, 32 chars).
The token carries no tenant id. A bad signature is 403 and an expired token
410 (the signature is checked first, so a tampered expiry is a 403). With S3
storage, platforms get the bucket's own presigned URL instead
(`platform_url`), which is public https without a tunnel.

Every query filters by tenant_id; another tenant's item is a 404.
"""
import hashlib
import hmac
import io
import struct
import time
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.ai.creative_providers import image_size, ratio_value
from app.config import get_settings
from app.core.audit import write_audit_log
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.integrations.storage import StorageError, get_storage
from app.models.media import MediaAsset

logger = structlog.get_logger(__name__)

IMAGE_MAX = 30 * 1024 * 1024
VIDEO_MAX = 1024 * 1024 * 1024
EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "video/mp4": "mp4", "video/quicktime": "mov"}
PIL_FORMAT = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}


def kind_of(content: bytes) -> str | None:
    """MIME from magic bytes, never the file name."""
    if content[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    if content[4:8] == b"ftyp":
        return "video/quicktime" if content[8:10] == b"qt" else "video/mp4"
    if content[4:8] in (b"moov", b"mdat", b"wide", b"free"):
        return "video/quicktime"
    return None


# ---------------------------------------------------------------------------
# MP4 / MOV header reading (no ffprobe): duration from moov/mvhd, size from
# the first moov/trak/tkhd with a non-zero width. Unreadable -> None.
# ---------------------------------------------------------------------------
def _boxes(data: bytes, start: int, end: int) -> list[tuple[bytes, int, int]]:
    out: list[tuple[bytes, int, int]] = []
    i = start
    while i + 8 <= end:
        size = struct.unpack(">I", data[i:i + 4])[0]
        kind = data[i + 4:i + 8]
        header = 8
        if size == 1:
            if i + 16 > end:
                break
            size = struct.unpack(">Q", data[i + 8:i + 16])[0]
            header = 16
        elif size == 0:
            size = end - i
        if size < header or i + size > end:
            break
        out.append((kind, i + header, i + size))
        i += size
    return out


def video_info(data: bytes) -> tuple[int | None, int | None, int | None]:
    """(duration_ms, width, height)."""
    try:
        moov = next(((s, e) for k, s, e in _boxes(data, 0, len(data)) if k == b"moov"), None)
        if moov is None:
            return None, None, None
        duration_ms = width = height = None
        for kind, s, e in _boxes(data, *moov):
            if kind == b"mvhd":
                version = data[s]
                if version == 1:
                    timescale, duration = struct.unpack(">IQ", data[s + 20:s + 32])
                else:
                    timescale, duration = struct.unpack(">II", data[s + 12:s + 20])
                if timescale:
                    duration_ms = int(duration * 1000 / timescale)
            elif kind == b"trak" and width is None:
                for k2, s2, _e2 in _boxes(data, s, e):
                    if k2 == b"tkhd":
                        off = s2 + (88 if data[s2] == 1 else 76)
                        w, h = struct.unpack(">II", data[off:off + 8])
                        if w >> 16:
                            width, height = w >> 16, h >> 16
        return duration_ms, width, height
    except (struct.error, IndexError):
        return None, None, None


# ---------------------------------------------------------------------------
# Signed URLs
# ---------------------------------------------------------------------------
def _sig(media_id: str, expires: int) -> str:
    key = get_settings().SECRET_KEY.get_secret_value().encode()
    return hmac.new(key, f"media:{media_id}.{expires}".encode(), hashlib.sha256).hexdigest()[:32]


def signed_url(media_id: str, ttl_hours: int | None = None) -> str:
    s = get_settings()
    expires = int(time.time()) + 3600 * (ttl_hours or s.MEDIA_URL_TTL_HOURS)
    return f"{s.PUBLIC_BASE_URL.rstrip('/')}/api/v1/media/f/{media_id}.{expires}.{_sig(media_id, expires)}"


def verify_token(token: str) -> str:
    """media id from a token; AppError 403 (bad) / 410 (expired)."""
    parts = token.split(".")
    if len(parts) != 3 or not parts[1].isdigit():
        raise AppError("Invalid media link.", 403)
    media_id, expires_s, sig = parts
    if not hmac.compare_digest(_sig(media_id, int(expires_s)), sig):
        raise AppError("Invalid media link.", 403)
    if int(expires_s) < time.time():
        raise AppError("This media link has expired.", 410)
    return media_id


def platform_url(asset: MediaAsset) -> str:
    """A URL a social platform can fetch (Instagram, TikTok pull). S3 gives a
    presigned bucket URL; local storage needs a public https PUBLIC_BASE_URL."""
    storage = get_storage()
    presigned = storage.presign_get(asset.storage_key, 6 * 3600)
    if presigned:
        return presigned
    base = get_settings().PUBLIC_BASE_URL
    if not base.startswith("https://") or "localhost" in base or "127.0.0.1" in base:
        raise ConflictError(
            "This platform needs a public https address for media: set PUBLIC_BASE_URL (e.g. a tunnel) or use S3 storage."
        )
    return signed_url(str(asset.id), 6)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
def media_dict(asset: MediaAsset) -> dict[str, Any]:
    md = asset.extra_metadata or {}
    return {
        "id": str(asset.id),
        "kind": asset.kind,
        "mime": asset.mime,
        "bytes": int(asset.bytes),
        "width": asset.width,
        "height": asset.height,
        "duration_ms": asset.duration_ms,
        "source": asset.source,
        "name": asset.name,
        "url": signed_url(str(asset.id)),
        "parent_id": str(asset.parent_id) if asset.parent_id else None,
        "approved": bool(md.get("approved_at")),
        "created_at": asset.created_at.astimezone(timezone.utc),
    }


def require(db: Session, tenant_id: str, media_id: str) -> MediaAsset:
    asset = (
        db.query(MediaAsset)
        .filter(MediaAsset.id == media_id, MediaAsset.tenant_id == tenant_id, MediaAsset.deleted_at.is_(None))
        .first()
    )
    if asset is None:
        raise NotFoundError("Media not found.")
    return asset


def media_rows(db: Session, tenant_id: str, ids: list[str]) -> list[MediaAsset]:
    """Rows in the given order; an unknown, deleted or foreign id is a 422."""
    if not ids:
        return []
    rows = {
        str(m.id): m
        for m in db.query(MediaAsset).filter(MediaAsset.tenant_id == tenant_id, MediaAsset.id.in_(ids), MediaAsset.deleted_at.is_(None))
    }
    if any(i not in rows for i in ids):
        raise AppError("Some media items don't exist (or were deleted).", 422)
    return [rows[i] for i in ids]


def get_media(db: Session, tenant_id: str, media_id: str) -> dict[str, Any]:
    return media_dict(require(db, tenant_id, media_id))


def list_media(
    db: Session, tenant_id: str, kind: str | None, source: str | None, q: str | None, page: int, page_size: int = 40
) -> dict[str, Any]:
    query = db.query(MediaAsset).filter(MediaAsset.tenant_id == tenant_id, MediaAsset.deleted_at.is_(None))
    if kind:
        query = query.filter(MediaAsset.kind == kind)
    if source:
        query = query.filter(MediaAsset.source == source)
    if q:
        query = query.filter(MediaAsset.name.ilike(f"%{q}%"))
    count = query.with_entities(func.count(MediaAsset.id)).scalar() or 0
    rows = query.order_by(MediaAsset.created_at.desc(), MediaAsset.id).offset((page - 1) * page_size).limit(page_size).all()
    return {"count": int(count), "items": [media_dict(r) for r in rows]}


def read_bytes(asset: MediaAsset) -> bytes:
    try:
        return get_storage().get(asset.storage_key)
    except StorageError as exc:
        raise AppError(str(exc), 502) from None


def public_lookup(db: Session, media_id: str) -> MediaAsset:
    """For the signed route only: the token already proved access."""
    asset = db.query(MediaAsset).filter(MediaAsset.id == media_id, MediaAsset.deleted_at.is_(None)).first()
    if asset is None:
        raise NotFoundError("Media not found.")
    return asset


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------
def store(
    db: Session,
    tenant_id: str,
    actor_user_id: str | None,
    content: bytes,
    *,
    name: str | None,
    source: str,
    parent_id: str | None = None,
    generation_job_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    audit: bool = True,
) -> MediaAsset:
    """Validate, store and record one file. The same bytes from the same
    source return the existing row (dedupe on tenant + sha256 + source)."""
    mime = kind_of(content)
    if mime is None:
        raise AppError("Upload a JPG, PNG or WebP image, or an MP4/MOV video.", 422)
    kind = "image" if mime.startswith("image/") else "video"
    if len(content) > (IMAGE_MAX if kind == "image" else VIDEO_MAX):
        raise AppError("The image can be at most 30 MB." if kind == "image" else "The video can be at most 1 GB.", 413)
    digest = hashlib.sha256(content).hexdigest()
    existing = (
        db.query(MediaAsset)
        .filter(MediaAsset.tenant_id == tenant_id, MediaAsset.sha256 == digest, MediaAsset.source == source,
                MediaAsset.deleted_at.is_(None))
        .first()
    )
    if existing is not None:
        return existing
    width = height = duration_ms = None
    if kind == "image":
        try:
            _, width, height = image_size(content)
        except ValueError:
            width = height = None
    else:
        duration_ms, width, height = video_info(content)
    asset = MediaAsset(
        tenant_id=tenant_id, kind=kind, mime=mime, bytes=len(content), width=width, height=height,
        duration_ms=duration_ms, sha256=digest, storage_key="", source=source, parent_id=parent_id,
        generation_job_id=generation_job_id, name=(name or None) and name[:200], extra_metadata=metadata or {},
        created_by=actor_user_id,
    )
    db.add(asset)
    db.flush()
    asset.storage_key = f"{tenant_id}/{asset.id}.{EXT[mime]}"
    try:
        get_storage().put(asset.storage_key, content, mime)
    except StorageError as exc:
        db.delete(asset)  # only this row; the caller's other work is untouched
        db.flush()
        raise AppError(str(exc), 502) from None
    db.flush()
    if audit:
        write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor_user_id, action="media.uploaded" if source == "upload" else "media.created",
                        resource_type="media", resource_id=str(asset.id),
                        metadata={"kind": kind, "bytes": len(content), "source": source})
    logger.info("media_stored", tenant_id=tenant_id, media_id=str(asset.id), kind=kind, source=source, bytes=len(content))
    return asset


def upload(db: Session, tenant_id: str, actor_user_id: str, filename: str, content: bytes) -> dict[str, Any]:
    return media_dict(store(db, tenant_id, actor_user_id, content, name=filename, source="upload"))


def _fit(img: Any, ratio: str, mode: str) -> Any:
    from PIL import Image, ImageFilter

    want = ratio_value(ratio)
    w, h = img.size
    if mode == "crop":
        if w / h > want:
            nw = int(round(h * want))
            left = (w - nw) // 2
            return img.crop((left, 0, left + nw, h))
        nh = int(round(w / want))
        top = (h - nh) // 2
        return img.crop((0, top, w, top + nh))
    # pad: the whole image on a blurred, cover-scaled copy of itself
    if w / h > want:
        cw, ch = w, int(round(w / want))
    else:
        cw, ch = int(round(h * want)), h
    scale = max(cw / w, ch / h)
    bg = img.resize((max(1, int(w * scale)), max(1, int(h * scale)))).filter(ImageFilter.GaussianBlur(24))
    bl, bt = (bg.width - cw) // 2, (bg.height - ch) // 2
    canvas = bg.crop((bl, bt, bl + cw, bt + ch))
    out = Image.new(img.mode, (cw, ch))
    out.paste(canvas, (0, 0))
    out.paste(img, ((cw - w) // 2, (ch - h) // 2))
    return out


def derive(db: Session, tenant_id: str, actor_user_id: str | None, media_id: str, ratio: str, mode: str) -> MediaAsset:
    """A copy of an image in another ratio (center crop, or padded on a
    blurred fill). Videos are never transcoded (422)."""
    from PIL import Image, UnidentifiedImageError

    parent = require(db, tenant_id, media_id)
    if parent.kind != "image":
        raise AppError("Videos can't be cropped here; regenerate or upload the video in the right ratio.", 422)
    try:
        img: Any = Image.open(io.BytesIO(read_bytes(parent)))
        img.load()
    except (UnidentifiedImageError, OSError):
        raise AppError("The image couldn't be read.", 422) from None
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.mode else "RGB")
    fitted = _fit(img, ratio, mode)
    fmt = PIL_FORMAT.get(parent.mime, "PNG")
    if fmt == "JPEG" and fitted.mode == "RGBA":
        fitted = fitted.convert("RGB")
    buf = io.BytesIO()
    fitted.save(buf, format=fmt, **({"quality": 92} if fmt in ("JPEG", "WEBP") else {}))
    base = (parent.name or "image").rsplit(".", 1)[0]
    child = store(
        db, tenant_id, actor_user_id, buf.getvalue(), name=f"{base} ({ratio} {mode})", source="derived",
        parent_id=str(parent.id), metadata={"derived": {"ratio": ratio, "mode": mode}}, audit=False,
    )
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor_user_id, action="media.derived", resource_type="media",
                    resource_id=str(child.id), metadata={"parent_id": str(parent.id), "ratio": ratio, "mode": mode})
    return child


def find_derived(db: Session, tenant_id: str, parent_id: str, ratio: str) -> MediaAsset | None:
    return (
        db.query(MediaAsset)
        .filter(MediaAsset.tenant_id == tenant_id, MediaAsset.parent_id == parent_id, MediaAsset.deleted_at.is_(None),
                MediaAsset.extra_metadata["derived"]["ratio"].astext == ratio)
        .order_by(MediaAsset.created_at.desc())
        .first()
    )


def in_use(db: Session, tenant_id: str, media_id: str) -> bool:
    """Used by a scheduled or publishing organic post (SPEC-BE-076):
    content_assets.media_urls holds media ids for organic versions."""
    row = db.execute(
        text(
            "SELECT 1 FROM scheduled_posts sp JOIN content_assets ca ON ca.id = sp.content_asset_id "
            "WHERE sp.tenant_id = :t AND sp.status IN ('pending','scheduled','publishing') "
            "AND ca.media_urls ? :m LIMIT 1"
        ),
        {"t": tenant_id, "m": media_id},
    ).first()
    return row is not None


def delete(db: Session, tenant_id: str, actor_user_id: str, media_id: str) -> None:
    asset = require(db, tenant_id, media_id)
    if in_use(db, tenant_id, media_id):
        raise ConflictError("This media is used by a scheduled post; cancel or change that post first.")
    asset.deleted_at = datetime.now(timezone.utc)
    write_audit_log(db, tenant_id=tenant_id, actor_user_id=actor_user_id, action="media.deleted", resource_type="media",
                    resource_id=media_id, metadata={"name": asset.name})


def mark_approved(db: Session, tenant_id: str, actor_user_id: str, asset: MediaAsset) -> None:
    md = dict(asset.extra_metadata or {})
    md["approved_at"] = datetime.now(timezone.utc).isoformat()
    md["approved_by"] = actor_user_id
    asset.extra_metadata = md
