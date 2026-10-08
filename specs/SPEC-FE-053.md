# SPEC-FE-053: Meta builder — "Ad setup" card with three formats

Status: IMPLEMENTED and verified (2026-10-06). `npx tsc --noEmit` and `next build` are clean (the build used `NEXT_BUILD_DIR`, so the dev server's `.next` was untouched). The headless Edge E2E passed 16 of 16 checks, covering acceptance 1–5 plus a layout check. It ran against a production build on :3010 pointed at an isolated backend on :8010 (`META_FAKE_TRANSPORT=true`, scheduler off), using a temporary company that was deleted afterwards. Requested by the user. Backend: SPEC-BE-082. Only the ad level of the Meta builder changes.

## Changes (`/marketing/paid/{id}/edit`, Ad step, Meta campaigns)
1. The **"Ad creative"** card is renamed **"Ad setup"**.
2. The Format dropdown becomes three option tiles (radio group):
   - **Single image or video**: one uploader that accepts an image or a video. The uploaded file's type sets `format` to `image` or `video`. It shows the current media with a "Replace" option. Video processing status shows as it does today.
   - **Carousel**: a source switch:
     - **Choose images, videos and links manually**: 2–10 cards. Each card has a thumbnail, an image/video badge, headline, description, link and remove, plus an "Add a card" uploader that accepts image or video.
     - **Fill carousel cards dynamically from a product set**: a product set dropdown from `GET /meta/product-sets` showing "Set name — Catalog (N products)". It notes that card name/price come from the catalog and that this needs a Sales campaign. An empty list explains how to create a catalog in Commerce Manager.
   - **Use existing post**: a switch:
     - **Select post**: Facebook / Instagram tabs, listing posts from `GET /meta/posts?platform=` (thumbnail, text excerpt, date, "View post"), with "Load more" (cursor). Clicking a post selects it. The Instagram tab shows the backend's message when no Instagram account is connected.
     - **Create post** (Facebook): message, optional link, optional image (uploads through the existing Meta media uploader and uses its URL). The form says "This post will be published on your Facebook Page." **Create post** → `POST /meta/posts`, and the new post is selected automatically.

     The chosen post shows as a preview with "Change".
3. With **Use existing post**, primary text, headline, description, call to action and website URL are hidden, with the note "Text, media and button come from the post." URL parameters stay.
4. With a **product-set carousel**, headline/description stay hidden (as for carousels today), and primary text, CTA and URL stay.
5. Draft-only rules are unchanged: format controls are disabled for published ads. Errors use `FieldIssues` (`media`, `cards`, `product_set`, `existing_post`).

## Acceptance (E2E against the running backend + live DB, `META_FAKE_TRANSPORT=true`)
1. The Ad step shows "Ad setup" with the three tiles. "Ad creative" no longer appears anywhere.
2. Uploading a video in "Single image or video" saves `format=video`; uploading an image saves `format=image`.
3. A manual carousel with an image card and a video card saves and validates.
4. The product set dropdown lists the fake set; choosing it saves `carousel_source=product_set` + `product_set`.
5. "Select post" lists the fake Facebook and Instagram posts. "Create post" creates one and selects it. The text/CTA fields hide.
6. `npx tsc --noEmit` and `next build` are clean.

## Target files
- `frontend/components/campaigns/builder/ad-form.tsx`
- `frontend/lib/api/meta.ts`
- `frontend/lib/types/meta.ts`

## Implementation notes (2026-10-06 verification)
- **Fixed in `ad-form.tsx`:** manual carousel card rows were wider than the builder's middle column, so the Ad setup card overflowed under the preview panel and clipped the product-set tile. A row is now thumbnail | stacked headline/description/link | remove.
- **Fixed in `ad-form.tsx`:** when a single video finished processing, its file name was replaced with "" ("Video: video"). The uploaded name is now kept.
- **Fixed in the backend dev fakes (SPEC-BE-082 target):** an organic catch-all answered the ad video status poll (`fields=status,picture`), so `GET /meta/media/videos/{id}` returned 500 and videos stayed "processing" forever under `META_FAKE_TRANSPORT`. Real Meta was not affected.
- **Open risk (not changed, `media-uploader.tsx` is outside this spec):** the uploader keeps polling a processing video after a new file is dropped, so with real Meta (processing takes minutes) the video's late "ready" report could replace a newer image. The E2E check passed, but the fake finishes within one poll, so that check doesn't settle it.

`media-uploader.tsx` is not changed: it already supports `accept="both"`. It calls `onUploaded` twice for a video (on upload, then again when Meta finishes processing), so the carousel must update a video card by `video_id` instead of appending a second card.
