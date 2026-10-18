# SPEC-BE-098: AI product listings, website publishing, and richer creative jobs

Status: IMPLEMENTED and verified (2026-10-10), stage 3 of 4.
- **Checks:** 27/27 with dev fakes on the live DB, one rolled-back transaction, the listing AI stubbed:
  - **AC1:** photo + price + SKU → a draft product with every field and the photo; no photo → written from the details;
    a duplicate SKU → 409; no price → "What's the selling price?".
  - **AC2:** invented numbers dropped ("12 left", "30% off for 3 days", "#1 by 5000 buyers", "180 g"); the HTML is
    whitelisted (no script or link); an AI-invented price is removed by the guard.
  - **AC3:**
    - publish is a change step (a manager needs approval);
    - (a) website: active, web channel;
    - (b) Shopify: a failure deletes the half-made product and leaves the catalogue draft; publishing again updates,
      never duplicates;
    - WooCommerce: POST, then PUT; a failure → not published.
  - **AC4:** audience, background, mood and text go into the prompt; the user's voiceover words and chosen track are used.
  - **FR5:** listing → publish / posts / photo by `$1.product_id` / `$1.skus`.
- **AC5 real run** (pilotsonic's keys, Claude Sonnet 5.5, rolled back):
  - a drawn mug photo → "DHAKA BREW Black Mug with Gold Lettering, 350 ml", with "DHAKA BREW 350 ml" read off the label
    and every number from it;
  - SPEC-BE-097 AC6: a 3-product CSV + "create a listing and publish it on our website" → 6 jobs (listing → publish, SKUs
    and prices from the file) → submitted → 6/6 succeeded, three products live on the web channel.
- **Fixes found by the real run:**
  - A new listing's SKU can't already exist, so it is `new_sku`, checked against the user's words and files rather than
    the catalogue.
  - `publish_product` takes one `product` (`$n.product_id`, an id, or a SKU), so a missing one asks "Which product
    should I publish (its SKU)?".
  - A planner rule links publish / post / advertise steps to the listing step.
- **Deviations:**
  - The moderator prompt is unused in the codebase, so claim-softening is in the listing prompt plus the number check.
  - Store images need public URLs (S3 or https `PUBLIC_BASE_URL`); otherwise the product is published without them and
    the result says so.
  - Stock isn't set by a listing (inventory is per location).
- **Regressions:** stub eval 31/31; BE-095 27/27; BE-096 29/30 (known test-file artifact); BE-097 43/43; ruff 1 /
  mypy 7. Used by the job lists of SPEC-BE-097.

Asked: "1. AI-Powered Product Listing and Website Publishing. When a user uploads a product photo or provides product
details, the AI will analyze the information and automatically generate an attractive product title, professional
description, key features, specifications, and other relevant details. It will then publish the optimized product
listing on the website after the user's approval or according to predefined instructions." And "2. … Users can specify
the visual style, target audience, video duration, background, music, and other creative requirements."

**User's decision (2026-10-10):** publish to **both**: always the app's catalogue (a), and also the connected
Shopify/WooCommerce store when there is one (b).

## Context

- **Products can't be created today:** only `GET /products` and the chat's `update_product`. The live `products` table has
  `short_description`, `tags`, `images` (jsonb), `seo_title`, `seo_description`, `metadata`, `external_ids`, `brand`,
  `compare_at_price_cents`, `weight_grams` and `dimensions`.
- **No code publishes a product to a store.** Shopify and WooCommerce are connected only for shipping (SPEC-BE-058).
- **Already in place:** `generate_photo` / `generate_video` take a prompt, style, ratio, duration, platform and a
  reference image. Music and voiceover come from the company's settings (SPEC-BE-094).

## Requirements

- **FR1 (`analyze_product`, risk read):** photos (media ids) and/or details (text or an item from a file) → the vision
  model (SPEC-BE-096 FR4) returns what it can see and read: product type, brand, colour, material, visible text,
  size/variant hints. It never invents prices, stock or claims it can't see; unknown fields stay empty.
- **FR2 (`create_product_listing`, risk draft):** writes an **attractive, professional listing** in the brand voice and
  `primary_language` (Brand settings), and saves it as a **draft product** in the catalogue:
  - **What is written:** title (≤ 70 characters), short description, description (HTML: paragraphs and a features list),
    5–8 key features, a specifications table (`metadata.specifications`), tags, SEO title (≤ 60) and SEO description
    (≤ 160), slug and category suggestion.
  - **What is never AI-written:**
    - price, compare-at price, stock, SKU, weight and barcode come only from the user's data;
    - a missing price → the job is **Needs input** (SPEC-BE-097);
    - a missing SKU → one is generated from the title and shown for review.
  - **Images:** the photos are attached (`images` jsonb, media ids and signed URLs).
  - **Storage:** `metadata.ai = {model, generated_at, source_files}`, so it's clear what the AI wrote.
  - **Safety:** health, safety, "best"/"#1" and guarantee claims the input doesn't support are softened. The words are
    checked with the moderator prompt before saving.
- **FR3 (`publish_product`, risk change → manager+ approval, the owner's own command approves):** publishes the
  listing to the company's **website**. The target is chosen by the user (open decision in the plan):
  - **(a) Our catalogue:** status `active` and the `web` channel. This is what the app's own catalogue shows.
  - **(b) A connected store:** Shopify (GraphQL `productCreate` / `productUpdate` + media, the integration's saved token)
    or WooCommerce (REST `POST /wp-json/wc/v3/products`), and the store's id saved in `external_ids`. Re-publishing
    updates the store product, never duplicates it. All-or-nothing: a failed image upload leaves nothing half-made.
  - "According to predefined instructions" = a job list submitted with publish jobs, or a workflow (SPEC-BE-060)
    action `publish_product`, both still behind the approval rule.
- **FR4 (creative requirements):** `generate_photo` and `generate_video` get optional `audience`, `background`,
  `mood`, `text_overlay`. `generate_video` also gets `music_media_id` (an audio item; else the company default),
  `voiceover` (on/off) and `voiceover_text`. They go into the prompt and the SPEC-BE-094 sound step for this job only;
  the company settings stay the default.
- **FR5 (social and ads, reused):** `create_organic_posts` / `schedule_organic_posts` (captions and hashtags per platform)
  and `create_ai_campaign` / `publish_zernio_campaign` / the Meta builder actions (objective, audience, budget,
  platforms, schedule, approvals) are used as they are. They now accept `product_id` from a listing job's result, so a
  new product can be posted and advertised in the same job list.

## Acceptance criteria

- **AC1:** a product photo plus "price 1,850 BDT, SKU TEE-RED" → a draft product with a title, descriptions, features,
  specifications, tags, SEO fields, the photo, and the given price/SKU exactly. Without a price → Needs input.
- **AC2:** the listing text never contains a number that isn't in the input (guard + test), and the language follows Brand
  settings.
- **AC3:** `publish_product` as a manager needs approval; after approval the product is active (a), or created once in
  Shopify/WooCommerce (b, dev fakes; again → updated, not duplicated).
- **AC4:** a video job with audience, background, a chosen track and voiceover text uses them (job notes say so).
- **AC5:** real run (pilotsonic): one photo → a listing that a person would publish.

## Target files

`ai/command_actions.py`, `services/product_service.py`, `schemas/product.py`, `ai/creative_providers.py` (FR4 only),
`integrations/dev_fakes.py`. **New (needs approval):** `ai/prompts/product_listing.py`, and for (b)
`integrations/store_products.py` (Shopify + WooCommerce product calls).
