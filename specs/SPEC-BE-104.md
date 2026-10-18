# SPEC-BE-104: Organic Marketing and Command Chat publish through SocialAPI accounts

Status: IMPLEMENTED (2026-10-11). The UI part is SPEC-FE-071.
- **Checks:** ruff and mypy are at the baseline.
- **AC1–AC6:** 12/12 on the live DB with the dev fakes, rolled back.
- **Live, read-only:** tech-to-web's real SocialAPI Facebook account is a login with **no Page chosen yet**. It shows
  "needs attention: Choose its Facebook Page in Organic › SocialAPI" until one is chosen.

## The problem and the user's decision

- tech-to-web connected its Facebook Page through SocialAPI, but Organic Marketing said "Facebook Page: Facebook Page
  isn't connected."
- Organic Marketing (SPEC-BE-075/076) and Command Chat only use **direct** connections (`integrations`). SocialAPI
  (SPEC-BE-083) was built as a separate path.
- Since SPEC-BE-101, companies can't paste tokens, and PilotSonic's Meta app isn't set up, so SocialAPI is the only way
  a new company can connect.
- Decision (2026-10-11, "yes"):
  - Organic Marketing and Command Chat publish through the company's SocialAPI account for a platform when there's no
    usable direct connection.
  - A direct connection always comes first.

## Requirements

- **FR1 Which account.** `socialapi_service.organic_accounts(db, tenant_id)` → `{platform: account}` for facebook,
  instagram, tiktok and linkedin.
  - **Which one per platform:** the first active account, else the first one.
  - **Only an existing brand:** only for a company that already has its SocialAPI brand (`managed` + `brand_id`) and
    SocialAPI access (SPEC-BE-103). It never creates a brand.
  - **Cache:** cached per company for 60 s, and cleared when an account is connected, selected or disconnected.
  - **Errors:** any SocialAPI error means "no account". It never breaks an organic page.
- **FR2 Account status (`social_account_service`).** When the direct state is not_connected, expired or error and a
  SocialAPI account exists, the platform's account shows:
  - `connected_via: "socialapi"`, with the SocialAPI account id, name, handle and avatar;
  - status `connected`, or `error` with the reconnect reason;
  - default capabilities, except **Instagram stories off**;
  - a note: "Posts through SocialAPI (Organic › SocialAPI)".
- **FR3 Connection.** `connection()` keeps the direct path first. Otherwise it returns
  `{integration_id: None, via: "socialapi", fields: {key, account_id, platform}}`, with the company's restricted key. A
  platform with neither says "… isn't connected: connect it in Organic › SocialAPI."
- **FR4 Publishing (`integrations/socialapi_publisher.py`)**, using the SPEC-BE-075 contract:
  - **The request:** media from the library is uploaded to SocialAPI (bytes, so no public URL is needed). Then
    `POST /posts` with `publish_now` and one target. The link is added to the text when the payload carries it
    separately. TikTok privacy goes in `platform_data.tiktok.privacy_level`.
  - **Mapping the result:**
    - target `published` → published, with `external_id` = **the SocialAPI post id** (metrics are read by it) and
      `external_url` = the permalink;
    - `pending` / `publishing` → processing, with `ref` = `{post_id}`, then `poll` reads `GET /posts/{id}`;
    - `failed` → a SocialError with SocialAPI's message. Categories `rate_limit` / `system` are transient (retried);
      the rest are permanent;
    - HTTP 429 / 5xx → transient. **401 → transient**, because the next attempt's account lookup rebuilds the company
      key (SPEC-BE-101 Amendment A). It never marks a direct integration as expired.
  - **`metrics`:** `GET /posts/{id}/metrics` → likes, comments, shares, saves.
- **FR5 Wiring.**
  - `social_base.adapter(platform, via)` picks the SocialAPI publisher.
  - `organic_service.publish_one` / `_poll_one` pass `conn["via"]` and store `post.metadata.via`.
  - The organic results import only reads posts with the same `via` as the current connection.
  - In checks: an Instagram **story** via SocialAPI is an error ("not supported through SocialAPI"). The TikTok
    privacy-options check and the TikTok profile refresh apply only to direct connections.
- **FR6 Unchanged:**
  - companies with a direct connection;
  - the Organic › SocialAPI composer;
  - SocialAPI's own post list.

## Acceptance criteria (live DB, rolled back, dev fakes)

1. A company with only a SocialAPI Facebook account lists Facebook as connected via SocialAPI. A company with a direct
   connection keeps it.
2. Scheduling or publishing an organic post for it passes the checks. The publish job publishes it through SocialAPI,
   with the media uploaded, the post `published`, `external_url` = the permalink, and `via` = socialapi.
3. A post still publishing is polled to `published`. A failed target fails the post with SocialAPI's message; a rate
   limit is retried.
4. The results import writes rows for it.
5. Viewing pages for a company without a brand creates none. SocialAPI switched off (SPEC-BE-103) → not connected.
6. A Command Chat `create_organic_post` + schedule for that company works the same way (planner context shows the
   account).

## Files

- `services/socialapi_service.py`, `services/social_account_service.py`, `services/organic_service.py`,
  `services/analytics_service.py`.
- `integrations/social_base.py`, **new** `integrations/socialapi_publisher.py`.
- `schemas/social.py`.
