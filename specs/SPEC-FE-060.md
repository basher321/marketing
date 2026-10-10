# SPEC-FE-060: "Sound for AI videos" card in AI Models

Status: IMPLEMENTED (2026-10-10). `tsc` and `next build` are clean. The card uses only endpoints verified
in SPEC-BE-094. It hasn't been clicked through in a browser yet.

## Requirements

- **FR1:** Integrations › AI Models, next to the creative settings, gets a "Sound for AI videos" card:
  - **Voiceover:** an on/off switch and a voice select with OpenAI's 11 voices.
  - **Background music:**
    - With a track set: its name, an `<audio controls>` preview (the signed URL), and "Remove".
    - Without one: "Upload music (MP3, M4A or WAV, up to 20 MB)", which uploads to the media library
      (`POST /media`) and then saves it as the track. Tracks already uploaded are listed with
      `GET /media?kind=audio`.
  - **Music volume:** a slider from 5 to 100 %.
  - **Explanation:** one line: "Used when OpenAI makes a slideshow video. Google Veo videos come with their
    own sound."
  - **Errors:** each action shows the backend message (`errorText`). Saving is manager+, and a role
    refusal shows the role message (SPEC-FE-059).
- **FR2:** `MediaKind` gets "audio". `lib/api/ai-campaigns.ts` gets `fetchVideoAudio` /
  `saveVideoAudio`, and `lib/types/ai-campaigns.ts` gets the types.

## Acceptance criteria

- **AC1:** upload an MP3 → it becomes the track and the preview plays. Remove → none.
- **AC2:** the voice and voiceover switch persist after a reload.
- **AC3:** `tsc` and `next build` pass.

## Target files

`components/integrations/ai-models.tsx`, `lib/api/ai-campaigns.ts`, `lib/types/ai-campaigns.ts`,
`lib/types/media.ts`.
