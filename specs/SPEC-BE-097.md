# SPEC-BE-097: Job lists from files and commands (review, edit, submit, run in order or on schedule)

Status: IMPLEMENTED and verified (2026-10-10), stage 2 of 4. The DDL is applied. **Verification:** 43/43 checks on the
live DB in one rolled-back transaction, with the template AI stubbed (recorded answers):
- **AC1:** a 60-row XLSX → 60 items, 180 jobs, one AI call, nothing run; placeholders filled and `$n` references
  remapped per item; "one product a day at 10:00" → 60 run times, 10:00 local, a day apart.
- **AC2:** a job edit; a removal (dependents too: [5, 6]); an added job; an item edit (its jobs rebuilt); the chat edit
  "1 post instead of 2"; and a different request while a draft is open → a normal plan.
- **AC3:** `needs_input` → 409 listing the jobs; a fixed job clears; a manager's submit → change jobs wait; the owner's
  "approve all" → they run, dependencies first; a summary is posted.
- **AC4:**
  - scheduled jobs wait; a due job runs while later ones wait;
  - pause blocks due jobs; resume runs them; cancel skips the rest;
  - parallel runs 2 at once with the 3rd waiting, then fills the freed slots;
  - a 429 re-queues the job a minute later.
- **AC5:** a failure message at once, plus progress lines; "how far is it?" and "retry the failed ones" work from the
  chat.
- **Other:** a 5-step command → a draft list, while a 2-step one is unchanged; another company → 404.
- **Regressions:** stub eval 31/31; SPEC-BE-095 27/27; SPEC-BE-096 29/30 (the known test-file artifact); ruff 1 / mypy 7.
- **AC6 (real AI) passed in stage 3:** CSV → 6 jobs → submitted → 6/6 succeeded (details in SPEC-BE-098).
- **Fixes found by the checks:**
  - Jobs the user adds or edits by hand skip the faithfulness guard (their form values are their request; the schema
    still checks them).
  - A list where every step was left out replies with the reasons instead of storing an empty draft.
- **Extra target files:** `services/scheduler_service.py` (`inline_jobs()`) and `workers/tasks/plan_tasks.py` (new). Uses SPEC-BE-096 (files) and SPEC-BE-098 (product
listing actions); the UI is SPEC-FE-065.

Asked (2026-10-10): "In this command chat, I need some task as it will perform as extractor of pdf doc excel zip or any
large or small file and there have an upload options as do chatgpt or claude or others. After extracting it will list the
job list and give to user for review and edit options if need user will edit and finalize. after submit it will execute
all jobs accordingly time or sequentially as user want. In this case it will call any tools in this software and its all
jobs reflection will be shows in command chat. So that use can interact with this chat and have chain of chat." Plus the
agent's areas: (1) AI product listing and website publishing, (2) AI image and video generation, (3) social content
publishing and scheduling, (4) ad campaign creation and management, (5) other product, content, social and ad jobs.
"Overall objective: … minimal manual effort."

**User's decisions (2026-10-10):** run modes are sequential, **parallel** and scheduled; approved, built in stages.

## Context

- A plan's read/draft steps start at once and its change/spend steps wait for approval (SPEC-BE-059). Steps run one at a
  time, in order. There is no "run at" time for a step.
- The planner writes at most ~2,500 tokens, so it can't list hundreds of jobs for a 200-row spreadsheet.
- Every module's actions already exist in `ai/command_actions.py`: photos/videos, organic posts and scheduling, AI
  campaigns, Meta, Zernio, workflows, products (update only; listings come with SPEC-BE-098).

## Requirements

- **FR1 (when a job list is made):** a message with files, or a command that asks for ≥ 2 jobs, produces a **job list in
  draft** instead of a plan that starts by itself. Nothing in a draft runs, not even read or draft steps, until the user
  submits it. A short command with no files keeps today's behaviour.
- **FR2 (items and a job template, so any size works):**
  1. **Items:** the planner turns the extracted content into items: spreadsheet rows, the products in a catalogue PDF,
     one item per product photo, and so on. Large inputs are read in chunks of ≤ 40 records or ~12k characters, with one
     AI call per chunk. Item fields come only from the files and the message.
  2. **Template:** one AI call turns the user's instruction into a **job template**: the steps for one item, using the
     existing actions, with `{{item.<field>}}` placeholders and `depends_on` inside the item, plus one-off steps.
     Example: create listing → generate 1 photo → 3 posts on Facebook and Instagram → ad campaign.
  3. **Expansion:** the backend expands template × items deterministically into numbered jobs. At most 500 jobs per list;
     more → split into lists of 500, which the reply says.
  - Every job is validated by the action's strict schema and the faithfulness guard (SPEC-BE-085). **Evidence** now
    includes the attached files' extracted text and records, so a price from the spreadsheet counts as the user's. A job
    that fails validation stays in the list, marked **Needs input**, with the missing field named.
- **FR3 (review and edit, before submitting):**
  - `GET /orchestrator/plans/{id}` returns the draft with `jobs` grouped by item, and each job's params, status
    (`draft` / `needs_input`), risk, approval rule and `run_at`.
  - `PATCH …/actions/{index}` edits a job's params (exists; now also in draft). `DELETE …/actions/{index}` removes a job
    and its dependents (listed first). `POST …/actions` adds a job (an action + params, validated).
    `PATCH /orchestrator/plans/{id}/items/{key}` edits an item's fields and re-expands its jobs.
  - **Chat edits:** while a draft is open, a message like "make all captions shorter", "remove the TikTok posts" or
    "post at 7 pm instead" changes the draft. The planner gets the draft as context and returns the edits, which go
    through the same validation. The reply lists what changed.
- **FR4 (run settings):** `PATCH /orchestrator/plans/{id}/schedule` with
  `{mode: "sequential" | "parallel" | "scheduled", start_at?, per_job: {index: run_at}?, spacing_minutes?, concurrency?}`.
  - **sequential:** one after another as soon as each is allowed, in order (today's executor).
  - **parallel** (the user's choice): up to `concurrency` jobs at once (1-5, default 3), only jobs whose dependencies are
    done. A provider's 429 pauses that provider's jobs for a minute instead of failing them.
  - **scheduled:** each job runs at its `run_at` (company timezone; e.g. "one product a day at 10:00", "posts at 19:00");
    jobs without one run in order from `start_at`. Steps that already have their own time (an organic post's schedule,
    a campaign's start date) keep it.
  - A job never runs before the jobs it depends on, whatever its time says.
- **FR5 (submit = finalize):** `POST /orchestrator/plans/{id}/submit` locks the list (no `needs_input` jobs left, else
  409 listing them). It then applies the **existing approval policy** per job:
  - read/draft → ready;
  - change → manager+ (the owner's own submit approves);
  - spend → owner approval always.
  Approval cards stay grouped ("Approve all I can"). Ready jobs run by FR4.
- **FR6 (execution at scale):** a one-minute scheduler job (`plan_jobs` in `workers/tasks/`) runs due jobs of submitted
  lists: `SKIP LOCKED`, at most 20 jobs per company per minute, one at a time per list (so dependent jobs see earlier
  results; in parallel mode up to its `concurrency`), retrying a failed job only when the user presses Retry. Pause/Resume/Cancel for a running list:
  `POST /orchestrator/plans/{id}/pause|resume|cancel`.
- **FR7 (reflection in the chat):**
  - The job board updates live: each job is queued, waiting for its time, waiting for approval, running, done (with its
    link and result) or failed (with the reason and Retry).
  - The chat posts a progress message when a batch of jobs finishes (at most one per list every 5 minutes), one
    immediately for each failed job, and a summary when the list is done. These are normal AI messages, so voice replies
    (SPEC-BE-095) and follow-up questions work.
  - **Chain of chat:** the planner's context carries the open and recent job lists, so "how far is it?", "retry the
    failed ones" or "pause the ads" act on them. Retry/pause/cancel are actions with the usual approval rules.
- **FR8 (unchanged):** the single-command chat, approval roles, the spend-cap rule, every existing action and route.

## DDL (additive, applied 2026-10-10)

`plan_status` is a Postgres enum (not text as first written): `ALTER TYPE plan_status ADD VALUE 'draft' | 'submitted' |
'paused' | 'cancelled'`. `orchestrator_plans` gets `mode text`, `start_at timestamptz`, `concurrency integer`,
`submitted_at timestamptz`, `paused_at timestamptz`, `progress_at timestamptz` (progress-message throttle), `items jsonb`,
`template jsonb`. A job's `run_at`, `item_key` and `missing` live in `actions[i]` (jsonb, no DDL).

**Implementation choice (FR1):** to keep small multi-step commands exactly as today (and the SPEC-BE-085 golden set), a
command without files becomes a job list when it yields **≥ 5 steps**, not ≥ 2.

## Acceptance criteria (dev fakes + live DB, rolled back; one real run)

- **AC1:** an XLSX of 60 products + "for each: create a listing, one photo, 2 Facebook posts at 19:00 from tomorrow, one
  per day" → 60 items, 240 jobs, no job running before submit.
- **AC2:** edit a job, remove a job (its dependents too), add a job, edit an item (its jobs re-expand), and the chat edit
  "make captions shorter" each change the draft as expected.
- **AC3:** submit with a `needs_input` job → 409. Submit as a manager → spend jobs wait for the owner; as the owner →
  change jobs run.
- **AC4:** scheduled mode runs each job at its time (clock advanced in the test); a dependent never runs first; pause
  stops new jobs; resume continues; cancel skips the rest.
- **AC5:** the chat shows progress, failures and the summary; "retry the failed ones" retries them.
- **AC6:** a real run with pilotsonic's AI keys on a small file (3 products) goes from upload to listings and posts in
  draft, with nothing published without the approvals.

## Target files

`services/orchestrator_service.py`, `ai/command_actions.py`, `ai/command_guard.py`, `api/v1/orchestrator.py`,
`schemas/orchestrator.py`, `models/orchestrator.py`, `workers/schedules.py`.
**New (needs approval):** `services/job_board_service.py` (items, template expansion, edits, schedule),
`workers/tasks/plan_tasks.py` (the one-minute runner).
