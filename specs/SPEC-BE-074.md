# SPEC-BE-074: Media library and storage (images and video for Organic Marketing)

Status: IMPLEMENTED (code, 2026-10-03; approved by the user). 19 no-DB checks pass, including AWS's published SigV4 test vectors. **Pending:** the DDL isn't applied yet and acceptance hasn't run on the live DB, because Postgres was unreachable. See "Implementation notes". Part of the Marketing restructure (SPEC-FE-049/050, SPEC-BE-074…078).
Decisions (user, 2026-10-03): D1 = local disk by default with an S3-compatible option, and signed public URLs. D3 = add Pillow for image crop/pad.

> **Live DB not inspected yet.** Postgres on localhost:5432 was unreachable on 2026-10-03. The table and enum facts below come from the ORM models and earlier specs. They are re-checked against `information_schema` before implementing, and any difference is reported.

## Purpose
Organic posts need images and videos that the company owns, independently of any ad account. Today an image only exists as an upload to an ad platform (`POST /meta/media`) or as a data-URL preview inside an AI run. `integrations/storage.py` is a stub.

This spec adds one media library that is used by manual uploads, photo/video generation (SPEC-BE-077) and social publishing (SPEC-BE-075).

## Storage backend (decision D1)
- `integrations/storage.py` becomes a small interface with two backends, chosen by `MEDIA_STORAGE`:
  - **`local` (default):** files under `MEDIA_ROOT` (default `backend/media/`, git-ignored), as `<tenant_id>/<media_id>.<ext>`.
  - **`s3`:** any S3-compatible bucket (`S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION`), signed with SigV4 over `httpx`. No new SDK.
- **Public URLs:** Instagram (and TikTok `PULL_FROM_URL`) fetch media from a public https URL.
  - Every media item gets a signed URL: `{PUBLIC_BASE_URL}/api/v1/media/f/{token}`. The token is an HMAC over `media_id` + expiry, signed with `SECRET_KEY`; it never contains the tenant ID.
  - The URL is served without auth and expires after `MEDIA_URL_TTL_HOURS` (default 24h). It is re-signed on every read.
  - The frontend uses the same URL for `<img>`/`<video>` previews, which can't send a bearer header.
  - In development, `PUBLIC_BASE_URL` defaults to `http://localhost:8000`. That works for previews, but Instagram can't reach it. Publishing to Instagram with a non-https or localhost `PUBLIC_BASE_URL` fails fast with a clear 409: "Instagram needs a public https address for media: set PUBLIC_BASE_URL (e.g. a tunnel) or use S3 storage."
- With `APP_ENV=production`, `PUBLIC_BASE_URL` must be https, and local storage logs a warning that it doesn't survive multiple servers.

## Table (additive DDL)
```sql
CREATE TABLE media_assets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  kind text NOT NULL CHECK (kind IN ('image','video')),
  mime text NOT NULL,
  bytes bigint NOT NULL,
  width int, height int, duration_ms int,
  sha256 text NOT NULL,
  storage_key text NOT NULL,
  source text NOT NULL CHECK (source IN ('upload','ai_image','ai_video','catalog','derived')),
  parent_id uuid REFERENCES media_assets(id) ON DELETE SET NULL,   -- crops/derivatives
  generation_job_id uuid,                                         -- SPEC-BE-077, no FK (created there)
  name text,
  metadata jsonb NOT NULL DEFAULT '{}',   -- provider, model, prompt, crop, approved_at, …
  created_by uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);
CREATE INDEX media_assets_tenant_idx ON media_assets (tenant_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX media_assets_dedupe ON media_assets (tenant_id, sha256, source) WHERE deleted_at IS NULL;
```
A model `MediaAsset` goes in a new `models/media.py`.

## Media checks
- **Types:** images JPG/PNG/WebP up to 30 MB; videos MP4/MOV up to 1 GB. The type is checked by magic bytes, reusing `meta_builder_service._kind_of` and `creative_providers.image_size`.
- **Size:** image width and height come from the file header. Video duration and size come from the MP4 `mvhd`/`tkhd` boxes (pure Python; no ffprobe). If a value can't be read it stays null, and platform checks that need it warn instead of failing.
- **Duplicates:** uploading the same file twice returns the existing row.
- **Body limit:** `middleware/body_limit.py` allows 1 GB on `POST /media`, as it does for ad media.

## Derivatives (decision D3)
- Platform adaptation (SPEC-BE-076) needs images in a platform's ratio (1:1, 4:5, 9:16, 1.91:1).
- With Pillow added to `requirements.txt`, `POST /media/{id}/derive {ratio, mode: crop|pad}` makes a `source='derived'` child. `crop` is a center crop; `pad` adds a blurred or brand-color fill.
- **Videos are never transcoded** (no ffmpeg). A video in the wrong ratio is a warning, and the fix is to regenerate it at the right ratio.

## API (`api/v1/media.py`, `services/media_service.py`)
| Method | Path | Role | Notes |
|---|---|---|---|
| POST | `/media` | agent+ | multipart upload → 201 `MediaOut` |
| GET | `/media` | viewer+ | `?kind=&source=&q=&page=` → `{count, items}` |
| GET | `/media/{id}` | viewer+ | 404 for another tenant's item |
| POST | `/media/{id}/derive` | agent+ | `{ratio, mode}` → 201 child |
| DELETE | `/media/{id}` | manager+ | soft delete; 409 if a scheduled or publishing post uses it |
| GET | `/media/f/{token}` | none | streams the file; supports `Range` (video); 403 on a bad token, 410 when expired |

`MediaOut`: id, kind, mime, bytes, width, height, duration_ms, source, name, url (signed), parent_id, created_at (UTC).

Every write is audited (`media.uploaded`, `media.derived`, `media.deleted`).

## Config (update SPEC-BE-002/003 to match)
`MEDIA_STORAGE`, `MEDIA_ROOT`, `MEDIA_URL_TTL_HOURS`, `PUBLIC_BASE_URL`, `S3_*`. Adding Pillow updates SPEC-BE-001.

## Acceptance criteria (live DB, rolled-back transaction, `MEDIA_ROOT` set to a temporary directory that is deleted afterwards)
1. PNG upload → 201. Width and height are correct. The signed URL streams the same bytes without auth. A tampered token → 403; an expired one → 410.
2. MP4 upload → duration and size are read. A `Range` request returns 206.
3. A text file renamed `.png` → 422. A 31 MB image → 413.
4. The same file uploaded twice → one row.
5. Another tenant's `GET /media/{id}` → 404. Agent `DELETE` → 403.
6. `derive` 4:5 crop of a 1:1 image → a child with the 4:5 size, `parent_id` set.
7. Deleting media used by a scheduled post → 409.
8. S3 backend: a SigV4 PUT/GET against a `httpx.MockTransport` returns the expected request signature (fixed clock).

## Target files
- New: `models/media.py`, `schemas/media.py`, `services/media_service.py`, `api/v1/media.py`.
- Changed: `integrations/storage.py` (stub → backends), `api/router.py`, `config.py`, `middleware/body_limit.py`, `requirements.txt` (Pillow), `.gitignore` (`backend/media/`).
- Specs: SPEC-BE-001/002/003 amendments.

## Out of scope
Video transcoding, a CDN, virus scanning, and per-tenant storage quotas (noted as a follow-up).

## Implementation notes (2026-10-03)
- **Config (deviation):** the existing `STORAGE_PROVIDER` / `STORAGE_BUCKET` / `STORAGE_ACCESS_KEY` / `STORAGE_SECRET_KEY` are reused instead of new `MEDIA_STORAGE` / `S3_*` names. New: `STORAGE_ENDPOINT`, `STORAGE_REGION`, `MEDIA_ROOT`, `MEDIA_URL_TTL_HOURS`, `PUBLIC_BASE_URL`. The `STORAGE_PROVIDER` default is now `local`, and `backend/.env` was changed from `s3` (its placeholder keys could never work) to `local`. SPEC-BE-001/002/003 are amended.
- **Public URLs for platforms:** with S3 storage, platforms get the bucket's own presigned URL (public https, no tunnel needed). With local storage they get the backend's signed URL, and only when `PUBLIC_BASE_URL` is public https; otherwise a 409 with the reason.
- **`kind_of()`** lives in `media_service`. It adds WebP to the Meta builder's JPG/PNG/MP4/MOV detection; the Meta builder keeps its own copy.
- **Writes:** `media_service.store()` is the single write path (uploads, AI results, catalog photos, derivatives). On a storage error it removes only its own row, never the caller's transaction.
- **Not done:** `.gitignore` for `backend/media/`. The repo isn't a git repository and has no `.gitignore`.
- **No-DB checks (pass):**
  - SigV4 header + presign (AWS vectors);
  - local put/get/range/delete and the path-traversal guard;
  - MP4 duration/size (and garbage → nulls);
  - magic-byte detection (PNG/JPEG/WebP/MP4; text refused);
  - crop 4:5 / 1:1 and pad 9:16 sizes;
  - signed token valid / tampered signature 403 / tampered expiry 403 / expired 410.
- **Pending (live DB):** apply the DDL above, then acceptance 1–8.
