# SPEC-BE-076: Organic content, platform adaptation and the post scheduler

Status: IMPLEMENTED (code, 2026-10-03; approved by the user). The rules, time conversion and schemas are checked without a DB (19 checks). **Pending:** the `organic_contents` DDL, a check of the `scheduled_posts` columns, and acceptance 1–11 on the live DB (Postgres unreachable). Depends on SPEC-BE-074 (media) and SPEC-BE-075 (adapters).

> **Live DB not inspected yet** (Postgres unreachable 2026-10-03). `scheduled_posts` columns `external_post_id`, `external_url`, `error_message`, `retry_count`, `metadata`, `created_by` are listed as "exists, unmapped" in `models/scheduled_post.py`. They are confirmed before mapping.

## Purpose
- One **master content** (caption, media, link, CTA, hashtags) produces **platform versions** for Facebook, Instagram, TikTok and LinkedIn.
- Each version can be edited, previewed, saved as a draft, scheduled, published now, cancelled or rescheduled.
- A real background job publishes on time and records the history and any errors.
- Two creation modes: **Manual** and **AI/Prompt**.

## Data model
| Layer | Storage |
|---|---|
| Master content | **new table `organic_contents`** |
| Platform version | `content_assets` row: `channel` = platform, `format = 'organic_post'`, `variants = [{caption, hashtags, cta, link_url, title}]` (index 0 = current; earlier generations kept for regenerate/undo), `media_urls = [media_id…]`, `metadata = {organic_content_id, integration_id, post_format, platform_options, warnings, edited: bool}` |
| Scheduled/published post | `scheduled_posts` row per version: `channel`, `scheduled_at` (UTC), `status`, `external_post_id`, `external_url`, `error_message`, `retry_count`, `metadata = {timezone, local_time, attempts:[…], next_attempt_at}`, `created_by` |

```sql
CREATE TABLE organic_contents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  title text,
  mode text NOT NULL CHECK (mode IN ('manual','ai')),
  prompt text,                         -- AI mode
  caption text NOT NULL DEFAULT '',
  hashtags text[] NOT NULL DEFAULT '{}',
  cta text, link_url text,
  media_ids uuid[] NOT NULL DEFAULT '{}',
  product_ids uuid[] NOT NULL DEFAULT '{}',
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','needs_approval','approved','archived')),
  approved_by uuid REFERENCES users(id) ON DELETE SET NULL, approved_at timestamptz,
  metadata jsonb NOT NULL DEFAULT '{}',   -- ai model/tokens/cost, tone, chat conversation id
  created_by uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
```

**Status mapping:**
- `post_status`: `pending` = waiting for content approval, `scheduled`, `publishing`, `published`, `failed`, `cancelled`.
- `content_status` on a version: `draft` → `approved` → `published`; `archived` when removed.

## Platform adaptation (`ai/prompts/organic_adapter.py`, new)
`PLATFORM_RULES` is one table per platform:
- caption max (FB 63 206, IG 2 200, TikTok 2 200 for video / 90-char title + 4 000-char description for photo, LinkedIn 3 000);
- hashtag max and style (IG ≤ 30 at the end; TikTok 3–5 inline; LinkedIn 3–5; FB 0–3);
- whether links are clickable (IG and TikTok are not, so the CTA becomes "link in bio");
- allowed formats and media ratios (IG feed 4:5–1.91:1, Reel/Story 9:16; TikTok 9:16; LinkedIn 1.91:1 / 1:1 / 4:5; FB any);
- video length limits;
- tone hints (LinkedIn professional, TikTok casual…).

Two adapters share these rules:
- **Rules adapter** (no AI; always available; used in Manual mode):
  - truncates at a word boundary and warns;
  - trims and dedupes hashtags to the platform's limit;
  - moves links into the CTA where they aren't clickable;
  - picks or derives media in the platform's ratio (SPEC-BE-074 `derive`).
- **AI adapter:** one LLM call (`creative_providers` kind `copy`, the company's model chain) with the master text, brand voice (`ai/retrieval.get_brand_voice`), platform rules and products. It returns strict JSON per platform: `{caption, hashtags, cta, title?}`. The rules adapter then enforces the limits on the output.
  - If the LLM fails, the rules adapter is used and a warning is shown. It is never silent and never a mock: `complete_with_usage` raises on provider failure, and a mock answer counts as a failure.

Each version stores `warnings` (e.g. "caption cut to 2 200 characters", "video is 16:9; Reels prefer 9:16").

## Creation modes
- **Manual** `POST /organic/contents` with:
  - `{caption, hashtags?, cta?, link_url?, media_ids[], targets: [{integration_id, post_format?, platform_options?}], adapt: "rules"|"ai"}`;
  - result: the master + versions (rules adaptation by default), status `draft`.
- **AI** `POST /organic/contents/ai` with:
  - `{prompt, product_ids?, tone?, targets[…], media: {mode: "none"|"use"|"generate_photo"|"generate_video", media_ids?, generation?: <SPEC-BE-077 request>}}`;
  - the copy is generated synchronously (a 503 if no AI model works);
  - photo/video generation starts as SPEC-BE-077 jobs, and the versions show `media_pending` until they finish;
  - the master is `needs_approval`.

## API (`api/v1/organic.py`, `services/organic_service.py`)
| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/organic/contents` | viewer+ | filters: status, platform, q, page |
| GET | `/organic/contents/{id}` | viewer+ | master + versions + posts |
| PATCH | `/organic/contents/{id}` | agent+ | master edit; `{readapt: bool}` re-adapts versions not edited by hand |
| POST | `/organic/contents/{id}/targets` | agent+ | add or remove platform versions |
| PATCH | `/organic/versions/{id}` | agent+ | edit a version's caption/hashtags/cta/title/media/options; sets `edited` |
| POST | `/organic/versions/{id}/regenerate` | agent+ | `{parts: ["caption","hashtags","cta","title"], instruction?, keep_media: true}`; parts not named stay as they are; the old text is kept in `variants` |
| POST | `/organic/versions/{id}/revert` | agent+ | `{variant_index}` back to an earlier generation |
| GET | `/organic/versions/{id}/preview` | viewer+ | composed final text (exactly what is sent), media URLs, warnings, blocking errors |
| POST | `/organic/contents/{id}/approve` | manager+ | `needs_approval` → `approved` (AI content); scheduling is blocked until approved |
| POST | `/organic/versions/{id}/schedule` | manager+ | `{scheduled_at_local: "2026-10-04T20:00", timezone?: IANA (default tenants.timezone)}` |
| POST | `/organic/contents/{id}/schedule` | manager+ | `{items: [{version_id, scheduled_at_local, timezone?}]}` all-or-nothing |
| POST | `/organic/versions/{id}/publish-now` | manager+ | queues an immediate publish (`scheduled_at = now`) and returns the post |
| POST | `/organic/posts/{id}/cancel` | manager+ | only `scheduled`/`pending` |
| POST | `/organic/posts/{id}/reschedule` | manager+ | only `scheduled`/`pending`/`failed` |
| POST | `/organic/posts/{id}/retry` | manager+ | only `failed` |
| GET | `/organic/calendar` | viewer+ | `?from=&to=` (≤ 62 days, tenant-local dates) → days with posts |
| GET | `/organic/history` | viewer+ | published/failed/cancelled, newest first, with error and external_url |
| GET | `/organic/summary` | viewer+ | dashboard: scheduled next 7d, published 30d, failed open, per-platform counts |

**Validation before schedule/publish (422 with a list of `{version_id, field, message}`):**
- the account is connected;
- the format is allowed;
- media is present where required (IG and TikTok);
- media is ready (no pending generation);
- the caption is within the limit;
- the time is ≥ now + 1 minute and ≤ now + 365 days;
- the timezone is a valid IANA zone (`utils/locale_data`).

**Other rules:**
- **Schedule edits:** an already scheduled version can't be edited while `publishing`. Editing a `scheduled` one keeps the schedule.
- **Roles:** agent+ creates and edits drafts; manager+ approves, schedules and publishes.
- **Audit:** every mutation is audited (`organic.*`).
- **Tenancy:** every query filters by `tenant_id`; another tenant's row → 404.

## Publishing job
`workers/tasks/publish_tasks.publish_scheduled_post` (stub → real) runs **every minute** (it is hourly today):
1. Select due posts: `status='scheduled' AND scheduled_at <= now() AND (next_attempt_at IS NULL OR <= now())`, `FOR UPDATE SKIP LOCKED`, max 20 per run.
2. Set `publishing` and commit, then call the adapter (SPEC-BE-075).
3. **Success:** `published`, `published_at`, `external_post_id`, `external_url`; the version and the master become `published`; audit `organic.published`.
4. **Transient error:** `retry_count + 1`, `next_attempt_at` +1 / 5 / 15 min, back to `scheduled`. After 3 retries → `failed`.
5. **Permanent or auth error:** `failed` with `error_message`, plus a `notifications` row to the creator and the owner(s).
6. **Idempotency:** a post with an `external_post_id` is never re-sent. A post stuck in `publishing` for over 30 min becomes `failed` with "Publishing state unknown — check the platform before retrying", so it is never posted twice.
7. Async platforms (IG video containers, TikTok uploads) store the job ref in `metadata` and are re-polled by the next run until done, for up to 30 min.

Posts publish only while the backend (scheduler) is running. This is shown on the scheduler page as "Scheduler: running/stopped" (`get_scheduler_status`).

## Acceptance criteria (live DB, rolled back, `INLINE_JOBS`, MockTransport/dev_fakes, `LLM_PROVIDER=fixture`)
1. Manual: caption + image + FB/IG/TikTok/LinkedIn targets → 4 versions; the IG caption has ≤ 30 hashtags and a "link in bio" CTA; LinkedIn has no clickable-link rewrite; the warnings are right.
2. AI: a prompt produces master + versions from the fixture LLM; the content is `needs_approval`; scheduling before approval → 409; after approval → 201.
3. `regenerate` with `parts=["caption"]` changes only the caption; media and hashtags are unchanged; `revert` restores it.
4. Schedule at local 20:00 Asia/Dhaka → stored as 14:00 UTC. A past time → 422. An unknown timezone → 422.
5. Job run with fake time past `scheduled_at` → `published` with external_id/url, audited, the calendar shows it.
6. Transient fake error → retried with backoff, then `failed` after 3. Permanent error → `failed` immediately + notification.
7. Two concurrent job runs → one publish (SKIP LOCKED).
8. Cancel → `cancelled`; reschedule → new time; retry of a failed post → `scheduled`.
9. Agent schedule → 403. Another tenant's version → 404.
10. `/organic/calendar` puts posts on tenant-local dates; `/organic/history` lists failed posts with `error_message`.
11. The existing `GET /scheduled-posts/count` and `/scheduled-posts/calendar` still return correct values with organic posts present.

## Target files
- New: `models/organic.py` (`OrganicContent`), `schemas/organic.py`, `services/organic_service.py`, `api/v1/organic.py`, `ai/prompts/organic_adapter.py`.
- Changed: `models/scheduled_post.py` (map the remaining live columns), `models/content.py` (nothing expected; checked), `workers/tasks/publish_tasks.py`, `workers/schedules.py` (every minute), `api/router.py`, `services/scheduler_service.py` (calendar unchanged; checked).

## Out of scope
Comment moderation, best-time-to-post suggestions, first-comment hashtags, and recurring posts.

## Implementation notes (2026-10-03)
- **Master status:** `organic_contents.status` has no `published` value. The master stays `approved`, and "published" is shown per version/post (the versions' `content_status` becomes `published`). Spec text adjusted here: "the master becomes published" is dropped.
- **Images per platform:** an image outside a platform's ratio range is replaced, for that platform only, by a centre crop in the platform's preferred ratio (created once and reused, `source='derived'`). Videos only get a warning.
- **Regenerate** keeps the parts that weren't named exactly as they were (after `enforce()`), appends a new variant and selects it. `revert` selects an earlier one. Up to 20 variants are kept.
- **Publishing job:** `organic_service.run_due()`, called every minute by `workers/tasks/publish_tasks.py`.
  - Due posts are claimed with `FOR UPDATE SKIP LOCKED`, marked `publishing` and committed before the platform call. Only organic posts (`content_assets.format='organic_post'`) are claimed.
  - Async platforms keep `metadata.ref` and are polled on later runs.
  - `publishing` with no ref for over 30 minutes → failed "state unknown".
  - An unexpected exception fails the post, never retries (it may have posted).
  - Publish-now and retry run the same path at once through `scheduler_service.run_soon`.
- **Failure notifications:** a `notifications` row goes to the owner(s) and to the creator if they aren't an owner.
- **Roles:** agent+ creates and edits; manager+ approves, schedules, publishes, cancels, reschedules and retries; viewer reads.
- **Also added:** `DELETE /organic/contents/{id}` (manager+) archives a content (409 if a version is scheduled).
- **`scheduled_posts` model:** now maps `external_post_id`, `external_url`, `error_message`, `retry_count`, `metadata`, `created_by`. Their live types (text, text, text, int, jsonb, uuid) are assumed from the old model docstring and are checked first on the DB.
- **No-DB checks (pass):**
  - IG hashtags capped at 30 and de-duplicated; link → "link in bio" with no URL in the text;
  - LinkedIn keeps a clickable link; TikTok caption shortened (with a warning) and title ≤ 90;
  - IG needs media; reel ratio is a warning; TikTok over-length video is an error; a carousel needs 2;
  - default formats;
  - 20:00 Asia/Dhaka → 14:00 UTC; unknown timezone 422; past time 422;
  - http link refused; offset in the local time refused; `keep_media` must be true.
- **Pending (live DB):** the DDL, then acceptance 1–11.
