# SPEC-BE-096: Command Chat file attachments and extraction

Status: IMPLEMENTED and verified (2026-10-10), stage 1 of 4. The DDL is applied.
- **Checks** (live Postgres, one rolled-back transaction, stored blobs deleted afterwards): 30/30 with real generated
  files: a text PDF, DOCX (heading, table, picture), XLSX (2 sheets, numbers kept), CSV, JSON, image, and a ZIP of all of
  them.
- **Refused safely:** a zip bomb (1028×), a 1,001-entry ZIP, a renamed .exe, a legacy .xls, a 101 MB file (413), an empty
  file, a `../` entry (a label only), and an encrypted entry (skipped with a warning).
- **Isolation:** another company's file → 404 on read and as `file_ids`.
- **AC4, real vision** (pilotsonic's keys): a scanned invoice PDF read exactly ("INVOICE 4471 … TOTAL 4300 BDT"). Without a
  vision model: a warning, not a failure.
- **Baseline:** ruff 1 / mypy 7, unchanged.
- **Deviations:**
  - No download of the original file: the media library's signed links are tied to media items. Previews come from
    `GET /orchestrator/files/{id}`, and images are in the media library.
  - `services/tenant_service.py` (reset deletes `orchestrator_files` rows) is an extra target file.
  - Pictures on Excel sheets are kept but not linked to rows (warning). Part of the "files → job list" feature with SPEC-BE-097
(job board), SPEC-BE-098 (AI product listings) and SPEC-FE-064/065 (UI).

Asked: "In this command chat, I need some task as it will perform as extractor of pdf doc excel zip or any large or small
file and there have an upload options as do chatgpt or claude or others. After extracting it will list the job list and
give to user for review and edit options …" (full request in SPEC-BE-097).

**User's decisions (2026-10-10):** the core file set (PDF, DOCX, XLSX, CSV/TXT/JSON, images, ZIP); legacy .doc/.xls,
.pptx and RAR/7z are refused with a clear message.

## Context

- The chat takes text and voice only. No PDF/Word/Excel library is installed (only Pillow).
- Request bodies are capped at 2 MB except the media routes (`middleware/body_limit.py`).
- AI calls are text-only (`ai/providers.call`); nothing sends an image or document to a model yet.

## Requirements

- **FR1 (upload):** `POST /orchestrator/files` (any role, multipart, one file per call; the chat uploads several in
  parallel) → `{id, name, kind, bytes, status, summary, items_count, media_ids, warnings}`.
  - **Types, by magic bytes (never the name):** PDF; DOCX; XLSX; CSV/TSV/TXT/MD/JSON (UTF-8 or UTF-16 text); images
    JPG/PNG/WebP (and GIF as a still); ZIP. Anything else → 422 naming the supported types.
  - **Size:** up to **100 MB** per file (route limit in `body_limit.py`), 20 files per message.
  - **Storage:** the original goes to `integrations/storage` (local disk or S3) under `orchestrator-files/<tenant>/…`.
    Images (uploaded or found inside PDF/DOCX/ZIP) also go into the media library as normal uploads, so jobs can use
    them as product photos, post media or ad creatives.
- **FR2 (extraction, `services/file_extract_service.py`):**
  - **PDF:** text per page (`pypdf`) and embedded images ≥ 200×200. A page with almost no text (scanned) is read by
    the company's vision model (FR4) when one is set up; otherwise the file gets a warning.
  - **DOCX:** paragraphs, headings, tables (as rows), embedded images (`python-docx`).
  - **XLSX / CSV / TSV:** every sheet; the first non-empty row is the header; each later row is a record
    `{column: value}` (`openpyxl`, read-only mode, formulas as their cached values).
  - **Text / Markdown / JSON:** as text (JSON arrays of objects become records).
  - **Images:** stored (FR1); described by the vision model when the job needs it (SPEC-BE-098).
  - **ZIP:** each supported entry is extracted as above. Guards: ≤ 1,000 entries, ≤ 1 GB uncompressed in total, a
    compression ratio above 200:1 is refused (zip bomb), no nested ZIP beyond one level, entry names are never used as
    paths (no traversal), encrypted entries are skipped with a warning.
- **FR3 (result):** `orchestrator_files.extracted` (jsonb) holds `{text_chunks: [...], records: [...], images: [media ids],
  pages, sheets, warnings}`; text is kept up to 2 MB per file and records up to 5,000 per file (more → a warning that
  says how many were left out). A short `summary` ("Spreadsheet, 1 sheet, 48 rows: sku, name, price, …") is built
  without AI.
- **FR4 (vision input):** `ai/providers.call_vision(provider, key, model, system, user, images|pdf_pages)` for Claude,
  OpenAI and Gemini (each accepts images; Claude and Gemini also accept PDF). It uses the company's chain like text calls
  (`llm_client.complete_vision`), skipping providers without vision. No `.env` fallback (company models only, SPEC-BE-088).
- **FR5 (attach to a message):** `ChatMessageCreate` gets `file_ids: list[str]` (≤ 20, the company's own files, else
  404). The message stores them; `ChatMessage` returns `files: [{id, name, kind, bytes, summary}]`.
- **FR6 (privacy):** files are tenant-scoped (another company's id → 404), never logged, and deleted with
  `POST /tenants/me/reset`. `GET /orchestrator/files/{id}` returns the metadata and a short preview; the original is
  downloadable through a signed URL like the media library.

## DDL (additive)

```sql
CREATE TABLE orchestrator_files (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  message_id uuid REFERENCES orchestrator_messages(id) ON DELETE SET NULL,
  name text NOT NULL, kind text NOT NULL, mime text NOT NULL, bytes bigint NOT NULL, sha256 text NOT NULL,
  storage_key text NOT NULL, status text NOT NULL DEFAULT 'extracted', extracted jsonb, error text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX orchestrator_files_tenant ON orchestrator_files (tenant_id, created_at DESC);
```

## New dependencies (requirements.txt, SPEC-BE-001 updated)

`pypdf` (PDF text and images), `python-docx` (Word), `openpyxl` (Excel). All pure Python. ZIP and CSV use the standard
library.

## Acceptance criteria (live DB, rolled back; real files)

- **AC1:** a 3-page text PDF, a DOCX with a table and an image, an XLSX with 2 sheets, a CSV, and a ZIP holding all of
  them each extract to the right text/records/images.
- **AC2:** a 101 MB file → 413; a renamed `.exe` → 422; a zip bomb, a 1,001-entry ZIP and a `../` entry are refused
  safely; an encrypted entry is skipped with a warning.
- **AC3:** another company's file id → 404 on read and as `file_ids`.
- **AC4:** a scanned PDF page is read by the vision model (real key) or gets the warning without one.
- **AC5:** ruff/mypy baseline unchanged.

## Target files

`api/v1/orchestrator.py`, `schemas/orchestrator.py`, `services/orchestrator_service.py`, `ai/providers.py`,
`ai/llm_client.py`, `middleware/body_limit.py`, `requirements.txt`, `integrations/dev_fakes.py`.
**New (needs approval):** `services/file_extract_service.py`, `models/orchestrator.py` gets `OrchestratorFile`.
