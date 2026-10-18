# SPEC-FE-065: Job board in Command Chat (review, edit, schedule, submit, live progress)

Status: IMPLEMENTED and verified (2026-10-10), stage 4 of 4. Backend: SPEC-BE-097 / SPEC-BE-098.
**Browser E2E (2026-10-10):** headless Chrome on the running app (:3000 + :8000 + the live DB), a throwaway company with
pilotsonic's AI keys (deleted afterwards, 0 left): 22 checks; 21 pass and the 22nd is the console line of the deliberate
.exe upload (422). `tsc` and `next build` are clean.
- **AC1:** the real AI made a draft board of 3 item groups and 6 jobs from a CSV; nothing ran. Edit (saved and flashed),
  remove (with confirm), add, duplicate and the filters all work.
- **AC2:** "Several at once (2)" was saved; the submit sheet said "Submit 6 job(s)? They run several at once (2 at a
  time)…".
- **AC3:** after submitting, editing is locked; live progress ran until all 6 jobs succeeded (real listings written and
  published), and the results summary arrived in the chat. An earlier run, with SKUs that already existed, showed the
  duplicate-SKU failures, the skipped dependants, a failure message and Retry.
- **AC4:** at 375 px, no row is wider than its group and there is no sideways scroll.
- **Fixes found by the E2E:**
  - Adding a whole-list job collapsed every item group: the first 8 groups now start open and stay as the user leaves them.
  - Long one-line descriptions widened the grid column, clipping badges at phone width (`.cc-job { min-width: 0 }`).
- **Extra target file:** `components/chat/plan-card.tsx` (a job list renders as the board).
- **Windowing:** 25 item groups at a time with "Show N more", not a virtual scroller.

## Requirements

- **FR1 (the board):** a job-list reply renders as a board card in the chat (generative UI, SPEC-FE-061):
  - **Header:** title, item and job counts, and the totals by status (draft / needs input / waiting for approval /
    scheduled / running / done / failed), with a progress bar.
  - **Item groups:** one collapsible group per item (product name/photo), each listing its jobs as rows: module icon,
    action, a one-line summary of the params, risk and approval badge, run time, status.
  - **Filters:** All / Needs input / By module; search by item name.
  - **Paging:** large lists are virtualised (hand-rolled windowing, no new library).
- **FR2 (review and edit before submit):**
  - **Per job:** Edit (form built from the params, like today's EditForm, with a date-time picker for `run_at` and a media
    picker for media ids), Remove (confirms when dependents go too) and Duplicate.
  - **Per item:** edit its fields; its jobs refresh.
  - **Adding:** "+ Add job" (choose an action, fill its form).
  - **Needs input:** jobs are highlighted and editing them clears the mark.
  - **Chat edits** (SPEC-BE-097 FR3) refresh the board, with the changed jobs flashed.
- **FR3 (run settings):** a "When should these run?" panel:
  - **One after another, now** (sequential), **Several at once** (parallel, 1-5 at a time), or **On a schedule:** a start date and time; "space them by N minutes/hours";
    or "one item per day at HH:MM".
  - Per-job times can be set in the job editor.
  - A preview line: "First job Oct 11 10:00 · last job Nov 9 10:00 (Asia/Dhaka)".
- **FR4 (submit):**
  - "Review & submit" shows a confirm sheet: how many jobs will run, which need a manager or the owner, how many publish
    or spend money, and the schedule. Then "Submit".
  - **409 handling:** a 409 lists the jobs that need input and scrolls to them.
  - **After submitting:** the board locks editing and shows Pause / Resume / Cancel.
- **FR5 (live reflection):** the board polls while anything is queued or running. Each job shows its state, its result
  link ("Open product", "Open post", "Open campaign") and errors with Retry. Progress, failure and summary messages
  arrive as chat messages (and are spoken after a voice command).
- **FR6 (unchanged):** small plans still render as today's plan card.

## Acceptance criteria

- **AC1:** a 60-product spreadsheet shows 60 groups / 240 jobs. Filter, search, edit, remove (with dependents), add and
  duplicate all work.
- **AC2:** a schedule preview matches the backend times; submit as owner/manager behaves per SPEC-BE-097 AC3.
- **AC3:** pause/resume/cancel and retry work; progress messages appear in the chat.
- **AC4:** `tsc` and `next build` pass; browser E2E passes with dev fakes; it is readable at 375 px.

## Target files

`components/chat/chat-panel.tsx`, `lib/api/orchestrator.ts`, `lib/types/orchestrator.ts`, `app/globals.css`.
**New (needs approval):** `components/chat/job-board.tsx` (board, groups, filters, windowing),
`components/chat/job-editor.tsx` (job/item forms, schedule panel, submit sheet).
