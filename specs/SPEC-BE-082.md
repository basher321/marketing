# SPEC-BE-082: Meta builder — Ad setup formats (single media, carousel incl. product set, existing post)

Status: IMPLEMENTED and verified (2026-10-05). Acceptance 1–5 pass on the live Postgres (17/17 checks, one rolled-back transaction, `META_FAKE_TRANSPORT=true`, nothing persisted). Acceptance 6 passes: ruff 1 / mypy 7 errors, the unchanged baseline. Not yet run against the real Meta API. 2026-10-06 (SPEC-FE-053 E2E): `dev_fakes.py`'s organic `picture` catch-all no longer answers the ad video status poll (`fields=status,picture`), which had made `GET /meta/media/videos/{id}` return 500 under the fakes. Requested by the user. Frontend: SPEC-FE-053. Scope is limited to the Meta builder ad level (SPEC-BE-055); nothing else in the software changes.

## Goal
The ad level of the Meta builder (`/marketing/paid/{id}/edit`, Meta campaigns) supports three ad formats, as in Meta Ads Manager's "Ad setup":
- **a) Single image or video**: one uploaded image **or** one uploaded video.
- **b) Carousel**: either
  - **manual cards** (2–10), each with an image **or** a video, a headline, a description and a link; or
  - **cards filled dynamically from a product set** (a Meta catalog product set).
- **c) Use existing post**: either pick a post already on the connected Facebook Page or Instagram account, or create a new Facebook Page post from the builder and use it.

## Decisions (user, 2026-10-05)
- A post created here is **always published on the Facebook Page**; there is no ads-only option.
- A product-set carousel is offered on every campaign, but validation requires the **Sales** objective. Publish adds the catalog and product set to the campaign and ad set automatically.
- Existing posts can come from **Facebook and Instagram**. Creating a post is Facebook only.

## Data (no DDL; everything lives in `ads.metadata`)
- `format`: `image` | `video` | `carousel` | `existing_post`. `image`/`video` are the two halves of (a); the UI picks one from the uploaded file's type. Existing ads keep working unchanged.
- `carousel_source`: `manual` (default) | `product_set`.
- `cards[]` (manual): `type` `image` | `video` (default `image` for old rows), `image_hash` (image cards), `video_id` + `thumbnail_url` (video cards), `headline`, `description`, `link`.
- `product_set`: `{id, name, catalog_id, catalog_name}` (product-set carousel).
- `existing_post`: `{platform: facebook|instagram, id, message, picture, permalink_url, created_time}`. A Facebook `id` is Meta's `{page_id}_{post_id}`; an Instagram `id` is the IG media id.

## FR
1. **Schemas** (`schemas/meta.py`): `AdFields.format` adds `existing_post`. New optional `carousel_source`, `product_set`, `existing_post`. `Card` gets `type`, `video_id`. A card needs an `image_hash` (image) or a `video_id` (video). `BuilderAd` returns the new fields.
2. **Lookups** (`api/v1/meta.py` → `meta_builder_service`), all read-only:
   - `GET /meta/product-sets` lists the product sets of every catalog the ad account's business owns or has client access to: `act_{id}?fields=business` → `{business}/owned_product_catalogs` + `client_product_catalogs` → `{catalog}/product_sets`. Returns `{id, name, catalog_id, catalog_name, product_count}`. An ad account without a business returns `[]`.
   - `GET /meta/posts?platform=facebook|instagram&after=` returns `{items, next_cursor}` (25 per page), with items in the `existing_post` shape:
     - **facebook:** `{page_id}?fields=access_token` (system-user token → Page token), then `{page_id}/published_posts?fields=id,message,full_picture,permalink_url,created_time` with the Page token.
     - **instagram:** `{instagram_id}/media?fields=id,caption,media_type,media_url,thumbnail_url,permalink,timestamp`. For videos, the picture is `thumbnail_url`. No Instagram account connected → 409 "Connect an Instagram account to the Page in Integrations."
3. **Create a Facebook Page post** (`POST /meta/posts`, manager+, audited `meta.page_post_created`): body `{message, link?, image_url?}`, where `message` is required and `link`/`image_url` must be https. It is always published on the Page.
   - With an image: `POST {page}/photos` (`url`, `caption`), using the Page token.
   - Otherwise: `POST {page}/feed` (`message`, `link`).
   - Returns the post in the list shape (`platform=facebook`), so the UI can select it at once.
   - Video posts are out of scope.
4. **Creative** (`_creative_spec`):
   - `existing_post`, Facebook: `{"object_story_id": id}`, plus `instagram_user_id` (as now) and `url_tags`. No `object_story_spec`, text or CTA. Meta uses the post's own text and attachment.
   - `existing_post`, Instagram: `{"object_id": page_id, "instagram_user_id": instagram_id, "source_instagram_media_id": id}` + `url_tags`. The Instagram account is always included, whatever the `use_instagram` setting.
   - Manual carousel: a video card is a child attachment `{video_id, picture: thumbnail_url, …}`; image cards are unchanged.
   - Product-set carousel: `product_set_id` on the creative, plus `object_story_spec.template_data` with `{link, message, call_to_action, multi_share_end_card: false, name: "{{product.name}}", description: "{{product.price}}"}`.
5. **Publish rules for product sets:** Meta only allows these in a catalog Sales campaign. When any ad in the campaign uses a product set:
   - the campaign gets `promoted_object.product_catalog_id`;
   - the ad set gets `promoted_object.product_set_id`, merged with its pixel/event.

   All ads in one ad set must use the same product set.
6. **Validation** (`_ad_missing`):
   - `existing_post`: a post must be chosen. An Instagram post needs a connected Instagram account. Headline, primary text and destination URL are not required. It is not allowed with an instant-form or app destination ("An existing post can't be used with an instant form/app destination").
   - Manual carousel: 2–10 cards. A video card needs a `video_id` with status ready or missing.
   - Product-set carousel: a product set must be chosen, the campaign objective must be `sales` ("Product-set carousels need a Sales campaign"), and the ad set's ads must not mix product sets.
   - Primary text is required for every format except `existing_post`.
7. **Editing live ads:** `LIVE_AD_FIELDS` is unchanged, so format/source/post/product-set changes after publish return 409 as format changes do today.
8. **Dev fakes** (`integrations/dev_fakes.py`): answer `act_X?fields=business`, `owned_product_catalogs`, `client_product_catalogs`, `{catalog}/product_sets`, `{page}/published_posts` and GET `{ig}/media`. They must sit before the organic catch-alls that match `permalink`/`picture` in `fields`. POST `/feed` and `/photos` already exist.

## NFR
- The Page token is fetched per request and never stored, logged or returned.
- No changes outside the Meta builder: the multi-platform builder, AI Autopilot, organic publishing and Command Chat are untouched.

## Edge cases
- No Meta connection or no Page → 409 with the existing messages, from both the lookups and post creation.
- Old ads (no `carousel_source`, cards without `type`) read as `manual`/`image`.
- Switching format keeps the other formats' data, so switching back loses nothing. Only the selected format is validated and published.

## Acceptance (live DB, rolled-back transaction, `META_FAKE_TRANSPORT=true`)
1. PATCH an ad to `format=existing_post` with a Facebook post; validate shows no headline/URL issues; publish creates a creative whose form has `object_story_id` and no `object_story_spec`. With an Instagram post, the creative has `source_instagram_media_id` + `instagram_user_id` + `object_id`.
2. A manual carousel with 1 image + 1 video card publishes; the video child carries `video_id` + `picture`.
3. A product-set carousel on a Sales campaign publishes with `product_set_id` + `template_data`, campaign `promoted_object.product_catalog_id` and ad set `promoted_object.product_set_id`. On a Traffic campaign, validate reports the Sales rule.
4. `GET /meta/product-sets` and `GET /meta/posts?platform=facebook|instagram` return the fake items; `POST /meta/posts` returns a post id `{page}_{n}` and an audit row.
5. Old ad rows read back unchanged (`carousel_source=manual`, card `type=image`).
6. ruff/mypy add no new errors.

## Target files
- `backend/app/schemas/meta.py`
- `backend/app/services/meta_builder_service.py`
- `backend/app/api/v1/meta.py`
- `backend/app/integrations/meta_ads.py` (client calls: product sets, Page token, page posts, create post)
- `backend/app/integrations/dev_fakes.py` (fixtures)
