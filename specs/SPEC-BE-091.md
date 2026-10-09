# SPEC-BE-091: Command Chat finds ad images and videos in the media library by name

Status: IMPLEMENTED and verified (2026-10-09), approved by the user ("approve and execute and run it").
- Live Postgres, rolled-back transaction, stub planner: AC1-AC3 pass (20 items, own company only, the
  name match first; "the summer banner" kept; a picker answer completes the draft). AC4: stub suite
  31/31, ruff 1 / mypy 7 (baselines).
- Real run (pilotsonic, Claude, DB rolled back, not approved): "use the web2 image" planned
  `publish_zernio_campaign` with `media_id` = web2.jpeg.
Originally DRAFT (2026-10-09). Requested by the user: "Which image or video should the ad use? … is
comming when i give prompt, but i need the option to sellect image or videos from existin page, so in
chat will direct me to show all existing post and select or chat will find the image or videos of
tilte or otheres search optioons do this chagees only. do not change anything in this existing sotware
execpt this." The picker half is SPEC-FE-056.

## Context

SPEC-BE-090's `publish_zernio_campaign` needs `media_id`. The planner only sees `recent_media` (what
Command Chat generated in the last 24 hours), so "use the Eid banner" or "use web2.jpeg" can't be
resolved and the chat asks "Which image or video should the ad use?". The media library
(`media_assets`, SPEC-BE-074) is never in the planner context.

## Requirements

- **FR1 (context):** the planner context gets `media_library`: up to 20 of the company's media
  items (not deleted), each `{media_id, name, kind, source}`. Items whose name contains a word of what
  the user typed (the message plus the open clarification chain; words of 3+ letters, case-insensitive)
  come first, then the newest. One query on `media_assets`, tenant-scoped.
- **FR2 (planner rule):** `media_id` may come from `media_library` when the user names the file or
  describes it by its name ("the Eid banner", "web2.jpeg"); a video when they say video, an image
  otherwise. If several items fit and the user didn't say which, or none fits, OMIT `media_id` so the
  system asks (the existing question).
- **FR3 (picker answer):** the SPEC-FE-056 picker answers the question with a message that contains
  the chosen item's id; the existing guard already accepts an id the user typed, and the pending
  draft is completed with it. No new endpoint.
- **FR4 (unchanged):** the question text, `recent_media`, the guard, every action and every other
  context key stay as they are.

## Target files

- `backend/app/services/orchestrator_service.py` (`_context`: `media_library`; one prompt line)
- `CLAUDE.md` (one line, shared with SPEC-FE-056)

No DDL, no new files, no schema change.

## Acceptance criteria

Live Postgres, rolled-back transaction, planner stubbed:
1. The context lists the company's media (never another company's), name matches first, at most 20.
2. "Run the ad … use the summer banner" with an item named `summer-banner.png` in the library: the
   planned `media_id` (that item's id) is kept by the guard.
3. Answering "which image" with a message containing an item id completes the pending draft into a
   plan with that `media_id`.
4. The SPEC-BE-085 stub suite stays 31/31; ruff/mypy stay at their baselines.
