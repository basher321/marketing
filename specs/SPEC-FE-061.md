# SPEC-FE-061: Command Chat redesign with generative UI

Status: IMPLEMENTED and verified (2026-10-10), approved by the user (2026-10-10). `tsc` and `next build` are clean.
Browser E2E (2026-10-10): headless Chrome with a fake microphone playing a Bengali command ("আমার পণ্যগুলো
দেখাও"), the real frontend + backend + live DB, pilotsonic's AI keys copied into a throwaway company (deleted afterwards,
0 rows left): **18/18 pass**. AC1-AC4 pass: the welcome cards, the plan timeline, the results card choosing Chart/Table by data shape, no
horizontal scroll at 375 px, and no console errors. The composer stays on screen at 1360×900, 1440×760 and 1920×1080.
- **Fixes found by the E2E:**
  - The result summary appeared only after a reload: the plan card now fetches the chat until the summary of a plan sent
    or seen running in this session arrives (≤ 8 tries, 1.5 s apart). This gap existed before this spec.
  - The panel was ~35 px taller than the screen (`calc(100vh - 200px)`).
  - The first view now jumps to the latest message.
- **Known, out of scope (not changed):** the app shell's 240 px sidebar doesn't collapse on phones, so at 375 px the chat
  gets ~100 px of width. That is the shell of every page (SPEC-FE-002), not this page.
Voice is SPEC-FE-062.

Asked: "In this page http://localhost:3000/chat has command chat, its UI of chatbox and its related UI is
not looking good, make it generative UI so people can attract to chat by using my system, you can follow
any other standard if have and higher than generative UI." and "do not change anything in the entire
software except this change."

## Approach

**Generative UI with a fixed component catalog** (the declarative pattern of Google's A2UI and Vercel AI
SDK generative UI): the AI's structured output picks which component renders, and each component is ours.
The backend already sends structured data (`kind`, `waiting_for`, `plan_id`, `results[].data`,
`results[].media`, plan actions with module, risk and status), so the UI is chosen from that data. The model
never sends markup or code, so nothing it writes can run in the browser (safer than free-form generated UI).
Nothing is computed or invented client-side: every number and label is the backend's.

**Deviation (asked by the user):** the page no longer copies the mockup's `.chat-*` look. It still uses only
the token colors (light and dark), and the old `.chat-*`/`.msg` classes stay in `globals.css` for other pages.

## Requirements

- **FR1 (layout):** a header with the orchestrator's identity (an animated gradient "orb", the title, "Online ·
  plans need your approval" status line); the conversation; a composer pinned to the bottom; the Pending
  Approvals panel on the right (below on phones). The chat fills the viewport height without page scrolling.
- **FR2 (welcome state):** with no messages: a greeting, one line on what it can do, and suggestion cards for
  E-Commerce, Paid Marketing, Organic Marketing, Workflows and Shipping. Each card has 2 example commands
  that use only existing chat actions (e.g. "Show products low on stock", "Create a workflow that alerts me
  when stock is low"). Clicking one sends it. Below a conversation, 3 compact suggestion chips stay above
  the composer while it's empty.
- **FR3 (message catalog):** each message renders by `kind`:
  - **user:** right-aligned accent bubble, time.
  - **message:** AI bubble with the orb avatar, time and Copy.
  - **clarification:** a "Needs a few details" question card: the questions, one chip per `waiting_for`
    field, the media library button (SPEC-FE-056) when it waits for `media id`, and "Start over".
  - **plan:** the plan card (FR4).
  - **summary:** a results card. Per result: a status icon, label and Open link, then by data shape:
    - one row with up to 6 numeric fields → metric tiles;
    - rows with one text column and one numeric column (≤ 12 rows) → a horizontal bar list (hand-drawn,
      no chart library), with a Table toggle;
    - anything else → the table (existing `ResultTable`, restyled, sticky header);
    - `media` → the existing image/video preview.
- **FR4 (plan card):** a vertical step timeline: a module icon and color per step, the description, risk
  and status badges, the dependency hint, the params as small key/value chips, a progress bar (steps done /
  total) and a live "Running…" shimmer. All buttons and behaviors of SPEC-FE-041 stay (Approve, Reject,
  Edit, Retry, Approve all I can, workflow preview, polling).
- **FR5 (thinking state):** while a message is being planned, an AI bubble with animated dots and rotating
  stage text ("Understanding your request…", "Checking your store data…", "Drafting a plan…"). This is
  decorative timing, not real progress, and says nothing that claims a step happened.
- **FR6 (composer):** an auto-growing textarea (Enter sends, Shift+Enter makes a new line), the send button
  as an icon, the placeholder showing what a pending question waits for, and the send error under it. The
  mic button slot is filled by SPEC-FE-062.
- **FR7 (motion and access):** messages fade/slide in, `prefers-reduced-motion` turns animations off, all
  buttons have labels, the conversation is an `aria-live="polite"` log, focus returns to the composer after
  sending.
- **FR8 (approvals panel):** restyled to match (cards, engine pill, relative time). Behavior unchanged.

## Acceptance criteria

- **AC1:** with dev-shop data, an empty conversation shows the welcome cards; clicking one sends it and a
  plan card renders with live status.
- **AC2:** a clarification shows the question card and chips; a summary with table data shows tiles, bars or
  a table by shape; generated media still previews.
- **AC3:** light and dark mode use only tokens; phone width (375 px) has no horizontal scroll.
- **AC4:** every SPEC-FE-041/056/057 behavior still works after a reload. `tsc` and `next build` pass.

## Target files

`app/(app)/chat/page.tsx`, `components/chat/chat-panel.tsx`, `components/chat/plan-card.tsx`,
`components/chat/approvals-panel.tsx`, `app/globals.css` (new `.cc-*` classes only).
**Deviation from the 3-file rule:** 4 files plus the page, because the plan card and approvals panel are
part of the chat's look.

## Amendment A (2026-10-10): chat bar in the middle when idle; multi-line composer

Asked: "make chatbar in the middle for idle and when user will write then it will go down as chatgpt claude and others do
and make it multiline it shows one line all text."

- **FR9 (idle composer):** with no messages, the composer sits in the middle of the panel, under the greeting and above
  the suggestion cards (ChatGPT / Claude style). Sending the first message (typed, a suggestion or voice) moves it to
  the bottom, with a short slide-down, and the conversation fills the space above. While the history loads, only a
  placeholder shows (no jump from bottom to middle).
- **FR10 (multi-line):** root cause, measured in Chrome: the textarea's height was set to 73 px (3 lines) but it rendered
  32 px, because `.cc-panel` is a flex column and the composer area could shrink when the content above was tall. The
  header, the composer area and the textarea no longer shrink; the textarea grows to 8 lines (200 px), then scrolls.
  Enter sends, Shift+Enter makes a new line (unchanged).
- **Result (2026-10-10):** headless Chrome on the running app, 20/20 twice:
  - **Idle:** the composer's centre is at 46 % of the panel height.
  - **After sending:** the composer is 15 px above the panel's bottom.
  - **Growth:** a long message + Shift+Enter is 3 lines (73 px); it grows to 200 px, then scrolls.
  - **Fit:** the composer is on screen at 375×667, 390×844, 768×1024 and 1360×900 (`100dvh` on phones).
  - **Phones:** the quick chips are one swipeable row.
  - **Voice regression:** 18/18 still pass.
- **AC5:** an empty chat shows the composer vertically centred; after sending it is at the bottom. A long message plus a
  Shift+Enter line shows as 3+ lines.

## Amendment B (2026-10-10): the assistant's name

Asked: "you can change AI Orchestrator as PilotSonic in command chat." The chat header's name is now **PilotSonic** (the
product name, as in the sidebar). Only that label changes.
