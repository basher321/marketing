# SPEC-FE-064: File upload in Command Chat

Status: IMPLEMENTED and verified (2026-10-10), stage 4 of 4. Backend: SPEC-BE-096.
**Browser E2E (2026-10-10):** headless Chrome on the running app (:3000 + :8000 + the live DB), a throwaway company with
pilotsonic's AI keys (deleted afterwards, 0 left): 22 checks; 21 pass and the 22nd is the console line of the deliberate
.exe upload (422). `tsc` and `next build` are clean.
- **AC1:** 📎 (CSV → "3 rows (sku, name, price, description)"), drag-and-drop (the overlay shows; the image gets a
  thumbnail) and paste (a text file) all upload, read and summarise; the sent bubble shows the file card.
- **AC2:** an .exe shows the backend's "isn't supported"; a 101 MB file is refused before upload; ✕ removes a file.
- **Deviation:** uploads use XMLHttpRequest for progress (`uploadChatFile` in `lib/api/orchestrator.ts`), with the same
  base URL and token as `apiFetch`; a 401 retries once through `apiFetch`, which refreshes the token.

## Requirements

- **FR1 (attach, ChatGPT/Claude style):**
  - a 📎 button in the composer;
  - drag-and-drop onto the chat, with a "Drop files to attach" overlay;
  - pasting images or files.
  - Up to 20 files per message; the types and 100 MB limit of SPEC-BE-096.
- **FR2 (chips):** each file shows above the textarea as a chip:
  - an icon by kind and a thumbnail for images;
  - name and size;
  - an upload progress bar (XHR progress), then "Reading…" while extraction runs, then the backend's short summary
    ("48 rows: sku, name, price…");
  - ✕ to remove it before sending.
  - Errors (422 type, 413 size) show on the chip with the backend's text.
- **FR3 (send):** Send waits for uploads to finish, then posts `{body, file_ids}`. A message with files and no text
  sends with "Read these files and suggest jobs". The user bubble shows the file cards (name, kind, size, summary;
  images as thumbnails), also after a reload.
- **FR4 (unchanged):** typed and voice messages without files.

## Acceptance criteria

- **AC1:** attach a PDF, an XLSX and two images by button, by drag-and-drop and by paste. Each shows progress, then its
  summary. Send → the bubble shows the cards.
- **AC2:** a 101 MB file and an .exe show their errors and aren't sent.
- **AC3:** `tsc` and `next build` pass; browser E2E (headless Chrome) passes.

## Target files

`components/chat/chat-panel.tsx`, `lib/api/orchestrator.ts`, `lib/types/orchestrator.ts`, `app/globals.css`.
**New (needs approval):** `components/chat/attachments.tsx` (picker, drop zone, chips, upload with progress).
