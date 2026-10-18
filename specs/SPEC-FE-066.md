# SPEC-FE-066: Command Chat — chat history and Projects UI

Status: IMPLEMENTED and verified (2026-10-10). Backend: SPEC-BE-099.
- **Verified:** a headless-Chrome E2E on the running app (:3000 + :8000 + live DB), with a throwaway company and real AI
  (pilotsonic's keys), passed every AC check in two consecutive runs (26 checks). AC3's plan wrote "Eid Tee at 1,850 BDT"
  from the project's CSV. The one remaining console error is the app's missing `/favicon.ico` (pre-existing).
  `tsc` and `next build` are clean. Regressions: voice E2E 18/18, job-board E2E 21/22 (the 22nd is the deliberate
  `.exe` 422, as before).
- **Deviations:**
  - `components/chat/plan-card.tsx` was also touched: its live summary lookup reads every chat's message cache
    (`getQueriesData` on the `messages` prefix) instead of the single old key.
  - Deleting the open chat: the page treats it as closed at once and drops its cached queries, so nothing refetches it
    (it would 404) before the URL updates.

**User's decisions (2026-10-10):** the right column, top (Chats | Projects), with Pending Approvals collapsible below;
everything private; AI titles. Approved as written.

## Requirements

- **FR1 (where):** the right column of `/chat` (the user's suggestion). Its **upper part** becomes a "Chats | Projects"
  panel; Pending Approvals moves below it as a collapsible section (open when anything is pending). On screens under
  1024 px, a "🕘 Chats" button in the chat header opens the same panel as a drawer.
- **FR2 (chat history):**
  - **"+ New chat"**, and a search box (titles and message text, debounced).
  - **The list:** pinned first, then grouped Today / Yesterday / Previous 7 days / Previous 30 days / Older. Each row has
    the title, the project's emoji, a preview line and relative time.
  - **Opening a chat:** loads its messages into the chat (`/chat?c=<id>`, so reload and the back button keep it);
    sending continues it.
  - **Row menu (⋯):** Rename (inline), Pin/Unpin, Move to project…, Archive, Delete (confirm). An "Archived" toggle at
    the bottom.
  - **New conversations:** an empty chat shows today's welcome screen; the first message creates the chat, which
    appears at the top of the list with its title updating when the AI title arrives.
- **FR3 (projects, like Claude Projects):**
  - **The Projects tab** lists the projects (emoji, name, chat count) plus "+ New project".
  - **Opening a project:** shows its header (emoji, name, description), "Instructions" (an editable box, saved) and
    "Files" (add from 📎 upload or attach an existing chat file; remove). Below are its chats, and "+ New chat in this
    project".
  - **While a project chat is open:** the chat header shows a project chip ("📦 Eid launch").
- **FR4 (unchanged):** messages, voice, attachments, job boards, approvals and every other page.

## Acceptance criteria (browser E2E on the running app)

- **AC1:** start two chats, switch between them, and each keeps its own messages after a reload (`?c=`).
- **AC2:** search finds a chat by a word in its messages; rename, pin, archive, delete and move work.
- **AC3:** create a project with instructions and a file; a chat in it shows the chip; its plan uses the project's file
  data.
- **AC4:** at 375 px the drawer works, with no sideways scroll; `tsc` and `next build` pass.

## Target files

`app/(app)/chat/page.tsx`, `components/chat/chat-panel.tsx`, `components/chat/approvals-panel.tsx`,
`lib/api/orchestrator.ts`, `lib/types/orchestrator.ts`, `app/globals.css`. **New (needs approval):**
`components/chat/chat-sidebar.tsx` (history + projects panel).
