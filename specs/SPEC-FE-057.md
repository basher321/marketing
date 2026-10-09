# SPEC-FE-057: Command Chat shows the Nano Banana image / Google Flow video it made

Status: IMPLEMENTED (2026-10-09), approved by the user. `npx tsc --noEmit` and `npm run build` pass (AC3).
AC1/AC2 rest on SPEC-BE-092's verified `media` items and GET /media/{id}. They haven't been clicked
through in a browser yet. `fetchMediaItem` was added because `fetchMedia` is already the list call. Backend half: SPEC-BE-092.

## Context

Command Chat's result summary (`components/chat/chat-panel.tsx`, `Results`) shows a step's status,
summary text and an "Open" link. A generated image or video can only be seen on the Organic Photo or
Video Generation page.

## Requirements

- **FR1:** `ResultItem` in `lib/types/orchestrator.ts` gets `media: { id: string; kind: "image" | "video" }
  | null`, mirroring SPEC-BE-092 FR7.
- **FR2:** when a succeeded result has `media`, the chat shows the step's summary text, then a preview
  below the step line:
  - an image as an `<img>` (max 320 px wide, rounded, `object-contain`);
  - a video as a `<video controls playsInline>` of the same size.
  The source is the `url` from `GET /media/{id}` (TanStack Query, key per media id), so it is always a
  fresh signed URL. The preview has a "Download" link to the same URL and keeps the existing "Open" link.
- **FR3:** while the URL loads, a grey placeholder of the same box. If the media was deleted (404), the
  text "This file was deleted from the media library."
- **FR4:** nothing else in the chat changes. Plan cards, the media picker (SPEC-FE-056), tables and links
  stay as they are. Colours come from the CSS tokens only.

## Acceptance criteria

- **AC1:** "make an image of a red sneaker on a beach with nano banana" → approve if asked → the summary
  shows the image inline (dev fakes), and it still shows after a page reload.
- **AC2:** "make a 8 second google flow video of …" → the summary shows a playable video.
- **AC3:** `npx tsc --noEmit` and `npm run build` pass.

## Target files

- `frontend/lib/types/orchestrator.ts`
- `frontend/lib/api/media.ts`: a `fetchMedia(id)`, only if no single-item fetch exists yet.
- `frontend/components/chat/chat-panel.tsx`
