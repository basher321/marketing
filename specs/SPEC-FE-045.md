# SPEC-FE-045: Multi-platform campaign builder (TikTok, Google, YouTube, LinkedIn, X, Snapchat, Pinterest)

Status: IMPLEMENTED (2026-10-02), plan approved (with YouTube added at the user's request). Verified E2E in headless Edge on dev-shop against the running backend and the live DB:
- The Ad Manager shows 8 cards.
- A YouTube draft (Video views · Demand Gen) opens this builder with YouTube's names.
- Campaign budget, bidding and target autosave to the DB.
- Audience: a free-text location (`id: null`, flagged *), a keyword and an age are saved.
- Ad: the YouTube formats are offered. Format, video link, headline and URL are saved. The live counter turns red over 40, and the checklist and Validate list the limit; fixed, validation passes.
- Adding and deleting an ad group works. A reload shows the saved values.
- A LinkedIn draft shows "Campaign group → Campaign → Creative" with job titles and no age or gender.
- A Meta draft still opens the Meta builder.
- Publish is disabled with "isn't available yet" until the platform's publishing spec (063–068) is built.

All test drafts (4) and their audit rows were deleted afterwards. `tsc --noEmit` passes. `npm run build` was not run, because of the running `next dev`.

Found and fixed during verification: autosave merged quick successive edits shallowly, so two changes inside `fields`, `targeting` or `creative` within one second kept only the last one. Nested objects now merge key by key.

Deviation (approved in the plan): 5 components plus the edit page, beyond the "page + ≤ 3 files" rule. The shared field renderer (`FieldInput`) and the per-platform field definitions live in `platform-builder/tree.tsx`. The publish footer, checklist and status controls live in the edit page, next to the Meta ones.

Backend: SPEC-BE-062 to 068. The Meta builder (`components/campaigns/builder/*`) is **not changed**. `/campaigns/<id>/edit` routes a non-Meta campaign (`metadata.platform`) to this builder.

Amendment (2026-10-02): YouTube is included. It gets the video-ad formats (skippable in-stream, in-feed, Shorts, bumper), a YouTube video link/ID field, headline, long headline, description, business name, CTA and final URL, and keyword/topic targeting.

Field keys used by the forms (the adapters in SPEC-BE-063…068 read these):
- `campaign.fields`: `budget_optimization` (TikTok, Pinterest); `bidding`, `target_cpa`, `target_roas`, `search_partners`, `display_network` (Google); `bidding` (YouTube); `funding_instrument_id` (X).
- `group.fields`: `placement`, `placements[]`, `optimization_goal`, `bid_strategy`, `bid_amount`, `pixel_id`, `optimization_event`, `app_id`, `lead_form_id`, `conversion_ids`, `audience_expansion`, `default_cpc`, `conversion_tag_id` — each platform shows only its own.
- `group.targeting`: `locations[]`, `languages[]`, `age_min`, `age_max`, `genders[]`, `interests[]`, `keywords[]` (`{name, match}` on Google), `negative_keywords[]`, `topics[]` (YouTube), `job_titles[]`, `industries[]`, `company_sizes[]`, `seniorities[]`, `skills[]` (LinkedIn), `audiences[]`. Each entry is `{id|null, name}`. `id: null` is free text, typed while not connected, to be picked from the platform's list later.
- `ad.creative`: `format`, plus that format's fields (e.g. `headlines[]`, `descriptions[]`, `long_headline`, `path1`, `ad_text`, `display_name`, `identity_id`, `intro_text`, `headline`, `description`, `text`, `card_headline`, `brand_name`, `title`, `alt_text`, `board_id`, `existing_post_id`, `existing_pin_id`, `youtube_video`, `business_name`, `media[]`, `cta`, `destination_url`).

## Layout
It mirrors the Meta builder so the two feel the same:
- A left tree: Campaign → groups → ads, using each platform's own names (e.g. "Line item" on X, "Ad squad" on Snapchat, "Campaign group / Campaign / Creative" on LinkedIn).
- A form in the middle, with autosave on change (PATCH).
- A preview and checklist on the right.
- Bottom bar: Validate, "Publish as paused", and "Publish".

## Forms per level
Each form is built from the registry plus the platform spec's field list:
- **Campaign:** name, objective (and type for Google), budget and bidding at the levels that platform uses, dates.
- **Group:**
  - Targeting editor: location, language, age/gender, interests/keywords/job attributes, audiences. Each search box calls `GET /ads/{platform}/lookup/{kind}`.
  - Placements, budget, schedule, bid, optimisation goal, pixel or conversion.
- **Ad:**
  - Format picker (the platform's formats only).
  - Text fields with live character counters at the platform's limits.
  - Media upload (`POST /ads/{platform}/media`) with the platform's aspect-ratio and length hints.
  - Destination URL with UTM, and CTA.
  - Google Search shows a headline/description list editor (3–15 / 2–4). Performance Max shows an asset-group editor.

## Behavior
- **Not connected:** lookups show "Connect <platform> in Integrations to search its catalog". Free text is allowed and flagged. Publish is disabled with the same message.
- **Validate** lists issues by level, and clicking one selects that node.
- **Publish:**
  - Shows the approval outcome from the backend: either "Sent to the owner for approval" or "Published: <platform> ids".
  - A 502 shows the platform's error, and the draft stays editable.
- **After publishing:** status chips and pause/resume per level. Results (spend, CTR, ROAS) come from Analytics, or "—" when nothing is imported.
- Add, duplicate and delete groups and ads, within the 1–10 limits.

## Acceptance (E2E, headless Edge, dev-shop with `META_FAKE_TRANSPORT=true` dev fakes for each platform; real publish only where you supply approved credentials)
1. For each of the 6 platforms: create → fill → validate (errors shown, then fixed) → publish → pause → resume.
2. The DB holds the platform ids. Test rows are removed afterwards.
3. A Meta campaign still opens the Meta builder.
4. `npx tsc --noEmit` and `npm run build` pass.

## Target files
- `app/(app)/campaigns/[id]/edit/page.tsx` (platform switch)
- New: `components/campaigns/platform-builder/{tree.tsx, campaign-form.tsx, group-form.tsx, ad-form.tsx, targeting-editor.tsx}`
- `lib/api/ads.ts` and `lib/types/ads.ts` (from SPEC-FE-044)

Deviation from the frontend's "page + ≤ 3 files" rule: one builder serves six platforms, so it needs these five components. This needs your approval.
