# SPEC-FE-056: Choose the ad's image or video from the media library in Command Chat

Status: IMPLEMENTED (2026-10-09), approved by the user. `npx tsc --noEmit` passes; `/chat` compiles on the
running dev server (200). The API round trip of every picker call (list, kind filter, name search, paging,
the answer completing the plan) was verified on the live DB in a rolled-back transaction; a click-through in
a real browser was not done in this session.
Originally DRAFT (2026-10-09). Requested by the user (see SPEC-BE-091 for the quote): when the chat
asks "Which image or video should the ad use?", let the user pick from the existing images and
videos, with search.

## Requirements

- **FR1:** when the latest AI message is a clarification whose `waiting_for` includes `media id`
  (the label SPEC-BE-090's question produces), the chat shows a "Choose from media library" button
  under that question.
- **FR2 (picker):** the button opens a panel listing the company's media library (`GET /media`,
  newest first, 40 per page, Previous/Next): thumbnail (image, or video with its length), name and
  kind. Filters: All / Images / Videos, and a search box that searches by name (`q`, debounced).
  Loading, empty ("No images or videos match") and error states.
- **FR3 (answer):** choosing an item sends the chat answer
  `Use the image "<name>" (<id>)` (or `video`), the same as typing it, and closes the panel. The user
  can still type an answer or press Start over instead.
- **FR4 (unchanged):** the rest of the chat page, the plan card and the organic media picker
  (`components/organic/media-picker.tsx`) stay as they are; `MediaThumb` is reused, not changed.

## Target files

- `frontend/components/chat/chat-panel.tsx` (button + picker panel)
- `frontend/lib/api/media.ts` (`fetchMedia` gets an optional `q` argument; existing calls unchanged)

No new files.

## Acceptance criteria

Against the running backend and the live DB:
1. The button appears only while the question waits for `media id`.
2. The panel lists only this company's media; the kind filter and name search narrow it; paging works.
3. Choosing an item sends the answer and the next reply is the plan with that `media_id`.
4. `npx tsc --noEmit` passes.
