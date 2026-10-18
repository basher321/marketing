# SPEC-FE-067: Command Chat — open the last chat, and show each step's outcome with how to fix it

Status: IMPLEMENTED and verified (2026-10-10). Approved by the user: "write spec for fix and execute…". Backend:
SPEC-BE-100.
- **Verified:** a headless-Chrome E2E on the running app, 9/9 (AC1–AC4). A throwaway company was seeded with a submitted
  list: job #1 failed for real on an over-long value, and job #4 was a display-only Facebook failure, so the link
  renders. Save & retry turned #1 into Done. `tsc` and `next build` are clean. The SPEC-FE-066 E2E passes every feature
  check (3 runs); its only failure is the app's missing `/favicon.ico`.
- **Deviations:**
  - `components/chat/chat-sidebar.tsx` is unchanged: the page does the navigation, so "+ New chat" → `?new=1` lives
    in `page.tsx`.
  - `components/chat/job-editor.tsx` gained an optional `saveLabel` prop ("Save & retry").
  - Fix links open in a new tab, like every other Command Chat link (SPEC-FE-058), not the same tab.
  - Deleting the open chat also goes to `?new=1`.

## Context

The user's job list was running, but `/chat` opened an empty new chat (SPEC-FE-066), so they saw nothing. Its messages
were in "Earlier chat". Failed jobs showed an error but not what to do about it, and a failed job couldn't be corrected.

## Requirements

- **FR1 (open the last chat):**
  - `/chat` without `?c=` opens the user's most recent chat (the first non-archived chat, pinned ones first, as listed),
    by replacing the URL with `?c=<id>`.
  - "+ New chat" (and "+ New chat in this project") goes to `/chat?new=1` (`&p=` kept), which shows the empty chat as
    today.
  - A user with no chats sees the empty chat.
- **FR2 (each step's status):** on the job board and the plan card, every step shows its status badge, as today. A failed
  step shows:
  - the error;
  - a **"How to fix:"** line with the backend's `fix.text`;
  - a link (`fix.link_label` → `fix.href`, a new tab like every Command Chat link) when there is one;
  - Retry.

  The chat's per-job lines (SPEC-BE-100 FR4) render as the compact progress lines they already are.
- **FR3 (fix then retry):** a failed `read`/`draft` step has **Edit**. Its form is the job form or the plan card's step
  form, with **Save & retry**, which saves and then retries. A queued `read`/`draft` job in a submitted job list has
  **Edit** (save only). `change`/`spend` steps keep Retry only.
- **FR4 (summary):** a finished plan's results card shows "How to fix" and the link under each failed result.

## Acceptance criteria (browser E2E on the running app)

- **AC1:** `/chat` opens the latest chat with its messages; "+ New chat" shows the empty chat with `?new=1`; reloading
  keeps either.
- **AC2:** a failed job shows the error, "How to fix" and its link (e.g. "Connect accounts" → `/marketing/organic/accounts`).
- **AC3:** editing a failed draft job with "Save & retry" runs it again with the new values, and it shows Done.
- **AC4:** the chat shows a line per finished job with the count; `tsc` and `next build` pass.

## Target files

`app/(app)/chat/page.tsx`, `components/chat/chat-sidebar.tsx` (the new-chat links), `components/chat/job-board.tsx`,
`components/chat/plan-card.tsx`, `components/chat/chat-panel.tsx` (the summary's fix), `lib/types/orchestrator.ts`.
No new files. This is more than the usual 3 component files, because the step's status shows on the board, the plan card
and the summary.
