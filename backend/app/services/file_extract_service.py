"""Command Chat file attachments and extraction (SPEC-BE-096).

A file is recognised by its bytes (never its name), stored as-is, and read:

- PDF: text per page (pypdf) and embedded images; a page with almost no text
  (a scan) is read by the company's vision model from its page image.
- DOCX: paragraphs, headings and tables (python-docx), plus embedded images.
- XLSX / CSV / TSV: every sheet; the first non-empty row is the header and each
  later row a record {column: value} (openpyxl read-only, cached formula values).
- Text / Markdown / JSON: text; a JSON array of objects becomes records.
- Images: stored in the media library so jobs can use them.
- ZIP: each supported entry as above, with zip-bomb, size, count, nesting and
  path guards (entry names are labels only, never paths).

Images found anywhere go into the media library as normal uploads. Nothing
here calls an AI model except the scanned-page reading.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError
from app.models.orchestrator import OrchestratorFile

logger = structlog.get_logger(__name__)

MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_FILES_PER_MESSAGE = 20
MAX_TEXT_CHARS = 2_000_000  # per file
MAX_RECORDS = 5000  # per file
MAX_IMAGES = 60  # per file (ZIP included)
MIN_IMAGE_SIDE = 200  # smaller embedded images are icons/logos
CHUNK_CHARS = 4000
ZIP_MAX_ENTRIES = 1000
ZIP_MAX_TOTAL = 1024 * 1024 * 1024
ZIP_MAX_RATIO = 200
OCR_MAX_PAGES = 20

SUPPORTED = "PDF, Word (.docx), Excel (.xlsx), CSV/TSV/TXT/Markdown/JSON, JPG/PNG/WebP/GIF images or ZIP"
KIND_LABEL = {"pdf": "PDF", "docx": "Word document", "xlsx": "Spreadsheet", "csv": "CSV", "text": "Text",
              "json": "JSON", "image": "Image", "zip": "ZIP archive"}


class _Refused(Exception):
    """A file (or ZIP entry) that isn't supported; the message says why."""


@dataclass
class _Out:
    text_chunks: list[dict[str, str]] = field(default_factory=list)
    records: list[dict[str, Any]] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    pages: int = 0
    sheets: list[dict[str, Any]] = field(default_factory=list)
    entries: list[dict[str, Any]] = field(default_factory=list)
    chars: int = 0
    records_dropped: int = 0
    images_dropped: int = 0

    def add_text(self, source: str, text: str) -> None:
        text = text.strip()
        if not text:
            return
        room = MAX_TEXT_CHARS - self.chars
        if room <= 0:
            return
        if len(text) > room:
            text = text[:room]
            self.warnings.append("The text was cut at 2 million characters.")
        self.chars += len(text)
        for i, chunk in enumerate(_chunks(text)):
            self.text_chunks.append({"source": source if i == 0 else f"{source} (cont.)", "text": chunk})

    def add_record(self, record: dict[str, Any]) -> None:
        if len(self.records) >= MAX_RECORDS:
            self.records_dropped += 1
            return
        self.records.append(record)


def _chunks(text: str) -> list[str]:
    """~CHUNK_CHARS pieces, split at paragraph, then line, then space boundaries."""
    out: list[str] = []
    while len(text) > CHUNK_CHARS:
        cut = max(text.rfind("\n\n", 0, CHUNK_CHARS), text.rfind("\n", 0, CHUNK_CHARS), text.rfind(" ", 0, CHUNK_CHARS))
        cut = cut if cut > CHUNK_CHARS // 2 else CHUNK_CHARS
        out.append(text[:cut].strip())
        text = text[cut:]
    if text.strip():
        out.append(text.strip())
    return out


# ---------------------------------------------------------------------------
# Recognising a file by its bytes
# ---------------------------------------------------------------------------
def _decode_text(data: bytes) -> str | None:
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    for enc in (("utf-16",) if data[:2] in (b"\xff\xfe", b"\xfe\xff") else ("utf-8",)):
        try:
            text = data.decode(enc)
        except UnicodeDecodeError:
            return None
        sample = text[:5000]
        bad = sum(1 for ch in sample if ord(ch) < 32 and ch not in "\t\r\n\f")
        return text if not sample or bad / len(sample) < 0.01 else None
    return None


def detect(data: bytes, name: str = "") -> tuple[str, str]:
    """(kind, mime) from the bytes. The name only tells CSV/TSV/Markdown apart
    once the bytes are known to be text."""
    head = data[:16]
    if head.startswith(b"%PDF-"):
        return "pdf", "application/pdf"
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        raise _Refused("Old Word/Excel files (.doc/.xls) aren't supported: save them as .docx/.xlsx and upload again.")
    if head.startswith(b"Rar!") or head.startswith(b"7z\xbc\xaf"):
        raise _Refused("RAR and 7z archives aren't supported: upload a ZIP instead.")
    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        try:
            names = set(zipfile.ZipFile(io.BytesIO(data)).namelist())
        except zipfile.BadZipFile:
            raise _Refused("The ZIP file is damaged.") from None
        if "word/document.xml" in names:
            return "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if "xl/workbook.xml" in names:
            return "xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if any(n.startswith("ppt/") for n in names):
            raise _Refused("PowerPoint files aren't supported: export the slides as PDF and upload that.")
        return "zip", "application/zip"
    if head.startswith(b"\xff\xd8\xff"):
        return "image", "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image", "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image", "image/webp"
    if head[:4] in (b"GIF8",):
        return "image", "image/gif"
    text = _decode_text(data)
    if text is not None:
        stripped = text.lstrip()
        lower = name.lower()
        if stripped[:1] in "[{":
            try:
                json.loads(text)
                return "json", "application/json"
            except ValueError:
                pass
        if lower.endswith((".csv", ".tsv")):
            return "csv", "text/csv"
        return "text", "text/plain"
    raise _Refused(f"This file type isn't supported. Upload {SUPPORTED}.")


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------
def _cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, (int, float, bool)):
        return value
    text = str(value).strip()
    return text or None


def _header(row: list[Any]) -> list[str]:
    names: list[str] = []
    for i, v in enumerate(row):
        base = str(v).strip() if v not in (None, "") else f"column_{i + 1}"
        name, n = base, 2
        while name in names:
            name, n = f"{base}_{n}", n + 1
        names.append(name)
    return names


def _rows_to_records(rows: list[list[Any]], source: str, out: _Out) -> dict[str, Any]:
    rows = [r for r in rows if any(v not in (None, "") for v in r)]
    if not rows:
        return {"name": source, "rows": 0, "columns": []}
    header = _header(rows[0])
    for n, row in enumerate(rows[1:], start=2):
        rec = {header[i]: _cell(v) for i, v in enumerate(row) if i < len(header) and _cell(v) is not None}
        if rec:
            rec["_source"] = f"{source} row {n}"
            out.add_record(rec)
    return {"name": source, "rows": len(rows) - 1, "columns": header}


class _Ctx:
    """What a reader needs to store images and read scans."""

    def __init__(self, db: Session, tenant_id: str, actor: str | None) -> None:
        self.db, self.tenant_id, self.actor = db, tenant_id, actor

    def store_image(self, data: bytes, name: str, out: _Out) -> str | None:
        from PIL import Image, UnidentifiedImageError

        from app.services import media_service

        if len(out.images) >= MAX_IMAGES:
            out.images_dropped += 1
            return None
        try:
            img: Any = Image.open(io.BytesIO(data))
            img.load()
        except (UnidentifiedImageError, OSError, ValueError):
            return None
        if min(img.size) < MIN_IMAGE_SIDE:
            return None
        if media_service.kind_of(data) is None or img.format == "GIF":
            # CMYK/odd PDF images, GIFs: re-encode so the media library accepts them.
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA" if "A" in img.mode else "RGB")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            data = buf.getvalue()
        try:
            asset = media_service.store(self.db, self.tenant_id, self.actor, data, name=name[:200], source="upload",
                                        metadata={"from_chat_file": True}, audit=False)
        except AppError as exc:
            out.warnings.append(f"An image in {name} wasn't kept: {exc.detail}")
            return None
        out.images.append(str(asset.id))
        return str(asset.id)

    def ocr(self, images: list[bytes], label: str, out: _Out) -> str | None:
        """Text of scanned pages via the company's vision model; None (and a
        warning) when there is none or it fails."""
        from app.ai.llm_client import LLMProviderError, llm_client

        try:
            res = llm_client.complete_vision(
                "You transcribe scanned documents. Return the text exactly as written, in its original language and "
                "script, keeping line breaks and table rows (cells separated by ' | '). No commentary.",
                f"Transcribe all text on these page images of {label}.",
                [("image/png", b) for b in images], max_tokens=4000, db=self.db, tenant_id=self.tenant_id,
            )
        except LLMProviderError as exc:
            out.warnings.append(f"{label}: scanned pages couldn't be read ({str(exc)[:160]}).")
            return None
        return res.text


def _png(img: Any) -> bytes:
    if img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _read_pdf(data: bytes, name: str, ctx: _Ctx, out: _Out) -> None:
    from PIL import Image
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise _Refused(f"{name} is password-protected.")
        pages = list(reader.pages)
    except PdfReadError:
        raise _Refused(f"{name} couldn't be read as a PDF.") from None
    out.pages += len(pages)
    scans: list[tuple[int, bytes]] = []
    for n, page in enumerate(pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - one bad page never fails the file
            text = ""
        out.add_text(f"{name} p.{n}", text)
        try:
            page_images = list(page.images)
        except Exception:  # noqa: BLE001
            page_images = []
        biggest: tuple[int, bytes] | None = None
        for k, im in enumerate(page_images, start=1):
            raw = im.data
            ctx.store_image(raw, f"{name} p{n} image {k}", out)
            try:
                size = Image.open(io.BytesIO(raw)).size
                area = size[0] * size[1]
                if biggest is None or area > biggest[0]:
                    biggest = (area, raw)
            except Exception:  # noqa: BLE001
                pass
        if len(text.strip()) < 20 and biggest is not None:
            scans.append((n, biggest[1]))
    if scans:
        todo = scans[:OCR_MAX_PAGES]
        if len(scans) > OCR_MAX_PAGES:
            out.warnings.append(f"{name}: only the first {OCR_MAX_PAGES} scanned pages were read.")
        imgs = []
        for _, raw in todo:
            try:
                imgs.append(_png(Image.open(io.BytesIO(raw))))
            except Exception:  # noqa: BLE001
                continue
        for i in range(0, len(imgs), 5):  # 5 pages per vision call
            scanned = ctx.ocr(imgs[i:i + 5], name, out)
            if scanned is None:
                break
            first, last = todo[i][0], todo[min(i + 4, len(todo) - 1)][0]
            out.add_text(f"{name} p.{first}-{last} (scanned)", scanned)


def _read_docx(data: bytes, name: str, ctx: _Ctx, out: _Out) -> None:
    import docx

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception:  # noqa: BLE001 - python-docx raises many kinds
        raise _Refused(f"{name} couldn't be read as a Word document.") from None
    lines: list[str] = []
    for p in document.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        style = (p.style.name if p.style is not None else "") or ""
        lines.append(("#" * int(style[-1]) + " " if style.startswith("Heading") and style[-1:].isdigit() else "") + text)
    out.add_text(name, "\n".join(lines))
    for t, table in enumerate(document.tables, start=1):
        rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
        sheet = _rows_to_records(rows, f"{name} table {t}", out)
        out.sheets.append(sheet)
        out.add_text(f"{name} table {t}", "\n".join(" | ".join(r) for r in rows))
    k = 0
    for rel in document.part.rels.values():
        if "image" in rel.reltype:
            k += 1
            try:
                ctx.store_image(rel.target_part.blob, f"{name} image {k}", out)
            except Exception:  # noqa: BLE001 - linked (external) images have no blob
                continue


def _read_xlsx(data: bytes, name: str, ctx: _Ctx, out: _Out) -> None:
    import openpyxl  # type: ignore[import-untyped]  # no stubs installed

    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001
        raise _Refused(f"{name} couldn't be read as an Excel workbook.") from None
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        sheet = _rows_to_records(rows, f"{name} › {ws.title}", out)
        out.sheets.append(sheet)
    wb.close()
    # Pictures placed on sheets live in xl/media/; they can't be tied to rows reliably.
    zf = zipfile.ZipFile(io.BytesIO(data))
    pics = [n for n in zf.namelist() if n.startswith("xl/media/")]
    for k, entry in enumerate(pics, start=1):
        ctx.store_image(zf.read(entry), f"{name} picture {k}", out)
    if pics:
        out.warnings.append(f"{name}: {len(pics)} picture(s) on the sheets were kept, but aren't linked to rows.")


def _read_csv(text: str, name: str, out: _Out) -> None:
    sample = text[:20000]
    try:
        dialect: Any = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel_tab if name.lower().endswith(".tsv") else csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    out.sheets.append(_rows_to_records(rows, name, out))


def _read_json(text: str, name: str, out: _Out) -> None:
    value = json.loads(text)
    items: list[Any] | None = None
    if isinstance(value, list):
        items = value
    elif isinstance(value, dict):
        items = next((v for v in value.values() if isinstance(v, list)), None)
    if items and all(isinstance(i, dict) for i in items):
        for n, item in enumerate(items, start=1):
            rec = {str(k): _cell(v) if not isinstance(v, (list, dict)) else v for k, v in item.items()}
            rec["_source"] = f"{name} item {n}"
            out.add_record(rec)
        out.sheets.append({"name": name, "rows": len(items), "columns": sorted({k for i in items for k in i})[:50]})
    else:
        out.add_text(name, json.dumps(value, ensure_ascii=False, indent=1))


def _read(kind: str, data: bytes, name: str, ctx: _Ctx, out: _Out, depth: int = 0) -> None:
    if kind == "pdf":
        _read_pdf(data, name, ctx, out)
    elif kind == "docx":
        _read_docx(data, name, ctx, out)
    elif kind == "xlsx":
        _read_xlsx(data, name, ctx, out)
    elif kind in ("csv", "text", "json"):
        text = _decode_text(data) or ""
        if kind == "csv":
            _read_csv(text, name, out)
        elif kind == "json":
            _read_json(text, name, out)
        else:
            out.add_text(name, text)
    elif kind == "image":
        if ctx.store_image(data, name, out) is None and len(out.images) < MAX_IMAGES:
            out.warnings.append(f"{name}: the image is too small (under {MIN_IMAGE_SIDE}px) or couldn't be read.")
    elif kind == "zip":
        _read_zip(data, name, ctx, out, depth)


def _read_zip(data: bytes, name: str, ctx: _Ctx, out: _Out, depth: int) -> None:
    if depth >= 2:
        out.warnings.append(f"{name}: a ZIP inside a ZIP inside a ZIP was skipped.")
        return
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        infos = [i for i in zf.infolist() if not i.is_dir()]
    except zipfile.BadZipFile:
        raise _Refused(f"{name} is a damaged ZIP file.") from None
    if len(infos) > ZIP_MAX_ENTRIES:
        raise _Refused(f"{name} has {len(infos)} files; a ZIP can hold at most {ZIP_MAX_ENTRIES}.")
    total = sum(i.file_size for i in infos)
    if total > ZIP_MAX_TOTAL:
        raise _Refused(f"{name} unpacks to more than 1 GB.")
    for info in infos:
        label = f"{name} › {info.filename}"
        base = info.filename.replace("\\", "/").rsplit("/", 1)[-1]
        if base.startswith(".") or info.filename.startswith("__MACOSX/"):
            continue
        if info.flag_bits & 0x1:
            out.warnings.append(f"{label}: password-protected, skipped.")
            continue
        if info.compress_size and info.file_size > 1024 * 1024 and info.file_size / info.compress_size > ZIP_MAX_RATIO:
            raise _Refused(f"{name} looks like a zip bomb ({label} expands {info.file_size // info.compress_size}×).")
        # Read with a hard cap, whatever the header claims.
        with zf.open(info) as fh:
            content = fh.read(info.file_size + 1)
        if len(content) > info.file_size:
            raise _Refused(f"{name} is damaged ({label} is larger than it says).")
        try:
            kind, _ = detect(content, base)
        except _Refused as exc:
            out.entries.append({"name": info.filename, "kind": None, "skipped": str(exc)})
            out.warnings.append(f"{label}: {exc}")
            continue
        out.entries.append({"name": info.filename, "kind": kind, "bytes": len(content)})
        try:
            _read(kind, content, label, ctx, out, depth + 1)
        except _Refused as exc:
            out.warnings.append(f"{label}: {exc}")


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------
def _summary(kind: str, out: _Out) -> str:
    parts = [KIND_LABEL.get(kind, kind)]
    if out.pages:
        parts.append(f"{out.pages} page{'s' if out.pages != 1 else ''}")
    for sheet in out.sheets[:3]:
        cols = ", ".join(str(c) for c in sheet["columns"][:6]) + ("…" if len(sheet["columns"]) > 6 else "")
        parts.append(f"{sheet['rows']} rows ({cols})" if sheet["rows"] else "")
    if len(out.sheets) > 3:
        parts.append(f"+{len(out.sheets) - 3} more tables")
    if out.entries:
        parts.append(f"{len(out.entries)} files inside")
    if out.images:
        parts.append(f"{len(out.images)} image{'s' if len(out.images) != 1 else ''}")
    if out.chars and not out.sheets:
        words = sum(len(c["text"].split()) for c in out.text_chunks)
        parts.append(f"~{words:,} words")
    return " · ".join(p for p in parts if p)


def file_dict(row: OrchestratorFile, preview: bool = False) -> dict[str, Any]:
    ex = row.extracted or {}
    out: dict[str, Any] = {
        "id": str(row.id), "name": row.name, "kind": row.kind, "mime": row.mime, "bytes": row.bytes,
        "status": row.status, "summary": ex.get("summary") or "", "items_count": len(ex.get("records") or []),
        "media_ids": ex.get("images") or [], "warnings": ex.get("warnings") or [],
        "created_at": row.created_at.astimezone(timezone.utc) if row.created_at else None,
    }
    if preview:
        chunks = ex.get("text_chunks") or []
        out["preview_text"] = (chunks[0]["text"][:1500] if chunks else "")
        out["preview_records"] = (ex.get("records") or [])[:5]
    return out


def upload(db: Session, tenant_id: str, actor_user_id: str, filename: str, content: bytes) -> dict[str, Any]:
    """Store and extract one file (SPEC-BE-096 FR1-FR3)."""
    from app.integrations.storage import get_storage

    if not content:
        raise AppError("The file is empty.", 422)
    if len(content) > MAX_FILE_BYTES:
        raise AppError("The file can be at most 100 MB.", 413)
    name = (filename or "file").replace("\\", "/").rsplit("/", 1)[-1][:200] or "file"
    try:
        kind, mime = detect(content, name)
    except _Refused as exc:
        raise AppError(str(exc), 422) from None
    digest = hashlib.sha256(content).hexdigest()
    row = OrchestratorFile(tenant_id=tenant_id, user_id=actor_user_id, name=name, kind=kind, mime=mime,
                           bytes=len(content), sha256=digest, storage_key="", status="extracting")
    db.add(row)
    db.flush()
    key = f"orchestrator-files/{tenant_id}/{row.id}/{re.sub(r'[^A-Za-z0-9._-]', '_', name)[:80]}"
    get_storage().put(key, content, mime)
    row.storage_key = key
    out = _Out()
    try:
        _read(kind, content, name, _Ctx(db, tenant_id, actor_user_id), out)
        row.status = "extracted"
    except _Refused as exc:
        row.status, row.error = "failed", str(exc)
        out.warnings.append(str(exc))
    if out.records_dropped:
        out.warnings.append(f"Only the first {MAX_RECORDS:,} rows were kept ({out.records_dropped:,} left out).")
    if out.images_dropped:
        out.warnings.append(f"Only the first {MAX_IMAGES} images were kept ({out.images_dropped} left out).")
    if row.status == "extracted" and not (out.text_chunks or out.records or out.images):
        out.warnings.append("Nothing readable was found in this file.")
    row.extracted = {
        "summary": _summary(kind, out), "text_chunks": out.text_chunks, "records": out.records, "images": out.images,
        "pages": out.pages, "sheets": out.sheets, "entries": out.entries[:ZIP_MAX_ENTRIES], "warnings": out.warnings[:50],
    }
    db.commit()
    db.refresh(row)
    logger.info("chat_file_extracted", tenant_id=tenant_id, file_id=str(row.id), kind=kind, bytes=len(content),
                records=len(out.records), images=len(out.images), status=row.status)
    if row.status == "failed":
        raise AppError(row.error or "The file couldn't be read.", 422)
    return file_dict(row)


def require(db: Session, tenant_id: str, file_id: str) -> OrchestratorFile:
    try:
        import uuid

        uuid.UUID(str(file_id))
    except ValueError:
        raise NotFoundError("File not found.") from None
    row = db.query(OrchestratorFile).filter(OrchestratorFile.id == str(file_id),
                                           OrchestratorFile.tenant_id == str(tenant_id)).first()
    if row is None:
        raise NotFoundError("File not found.")
    return row


def files_for_message(db: Session, tenant_id: str, file_ids: list[str]) -> list[OrchestratorFile]:
    """The company's own extracted files, in the given order (404 for any other)."""
    if len(file_ids) > MAX_FILES_PER_MESSAGE:
        raise AppError(f"Attach at most {MAX_FILES_PER_MESSAGE} files per message.", 422)
    rows = [require(db, tenant_id, fid) for fid in dict.fromkeys(file_ids)]
    for r in rows:
        if r.status != "extracted":
            raise AppError(f"{r.name} couldn't be read, so it can't be sent.", 422)
    return rows

