# SPEC-BE-063: TikTok Ads — connect, build, publish, results

Status: IMPLEMENTED (2026-10-02), plan approved. Verified 2026-10-02 on the live DB in a rolled-back transaction with real tokens, with this platform's HTTP answered by the `dev_fakes` fixtures (42/42 checks across all six platforms + YouTube):
- connect through Integrations (encrypted, connection test by this adapter);
- location search and media upload;
- a draft with dates passes local + platform validation;
- an injected failure mid-publish → 502, the draft unchanged, the error kept, no IDs, and the created objects cleaned up;
- publish → running with campaign, group and ad IDs;
- pause/resume of the campaign and a group;
- the results import writes daily rows; a re-import is idempotent; Analytics, CTR 7d and the campaign list read them.
**Not yet run against the real platform:** that needs your approved API access (see SPEC-BE-062). Field names follow the docs as of 2026-10 and are kept in this one file.

Implementation notes: `integrations/tiktok_ads.py`.
- Auth error codes are limited to TikTok's token errors (40102/40104/40105); 40100 is a rate limit (429).
- Results come from the BASIC daily report at campaign level. `conversion` maps to purchases, leads or installs by objective. The conversion value isn't requested, so ROAS stays null for TikTok.
- Rollback: deleting the campaign removes its ad groups and ads.

Follows SPEC-BE-062's adapter contract. File: `backend/app/integrations/tiktok_ads.py` (today a stub).

## API
- TikTok API for Business (Marketing API) **v1.3**, at `https://business-api.tiktok.com/open_api/v1.3/`. The header is `Access-Token`. Responses use `{code, message, data}`, and any `code != 0` is an error even with HTTP 200.
- Version and field names are re-checked against the live docs during the plan step.

## Connect (catalog fields)
- Required: `access_token` (a long-lived advertiser token from TikTok's OAuth app authorisation) and `advertiser_id`. Optional: `identity_id` (the TikTok account the ads post as).
- The verify test is `GET advertiser/info/?advertiser_ids=[id]` → account name, currency and timezone.

## Objectives (TikTok `objective_type` → our enum)
| TikTok | Label | Ours |
|---|---|---|
| REACH | Reach | reach |
| TRAFFIC | Traffic | traffic |
| VIDEO_VIEWS | Video views | awareness |
| ENGAGEMENT | Community interaction | engagement |
| LEAD_GENERATION | Lead generation | leads |
| APP_PROMOTION | App promotion | app_promotion |
| WEB_CONVERSIONS | Website conversions | conversions |
| PRODUCT_SALES | Product sales (needs a catalog) | conversions, unavailable with a reason unless a catalog is connected |

## Pathway fields
- **Campaign:** name, objective, budget mode (`BUDGET_MODE_INFINITE` | `BUDGET_MODE_DAY` | `BUDGET_MODE_TOTAL`), budget (campaign budget optimisation on or off).
- **Ad group:**
  - Placement: Automatic, or Select (TikTok, Pangle, Global App Bundle).
  - Promotion type and destination: website (pixel + optimisation event), app (app id), or lead form.
  - Targeting: locations (`location_ids` from lookup), age groups, gender, languages, interest and behaviour categories, custom/lookalike audiences, device OS.
  - Budget and schedule: daily or total, start/end.
  - Optimisation goal and bid: lowest cost, cost cap, or bid cap.
  - Billing event, and dayparting.
- **Ad:**
  - Identity.
  - Format: single video, image (Pangle placement only), or Spark Ad (existing post id).
  - Video upload (`file/video/ad/upload/`), cover image, ad text (1–100 characters), display name.
  - CTA from TikTok's list, landing URL with UTM, tracking pixel events.

## Publish
`campaign/create/` (operation_status DISABLE) → for each group, `adgroup/create/` → for each ad, `ad/create/` → when mode=active, `campaign/status/update/` ENABLE.

- Rollback: `campaign/status/update/` with DELETE on the created campaign. TikTok deletes its children.
- Pause/resume: `campaign|adgroup|ad/status/update/` with DISABLE or ENABLE.

## Rules checked by validate
- Budget minimums: campaign daily ≥ 50 USD equivalent and ad group daily ≥ 20 USD equivalent. Read the limit from the account where the API exposes it; otherwise these defaults, as documented in code.
- Video: 9:16, 16:9 or 1:1, at least 5 s, ≤ 500 MB.
- Ad text: 1–100 characters, no emoji at the start.
- A website destination needs a URL. Conversions need a pixel and an event.
- Spark Ads need an identity.

## Results
`report/integrated/get/` (BASIC report, AUCTION_AD, daily) → spend, impressions, clicks, conversions, and conversion value where the pixel reports it. Stored in `analytics_events` with `source='tiktok'`.

## Acceptance (mocked HTTP, live DB, rolled-back transaction)
1. The verify test maps a `code != 0` response to a failed connection with TikTok's message.
2. Publish sends the four call types in order, with correct units (currency amount, not cents).
3. An ad failure deletes the campaign and returns 502.
4. Pause/resume calls the status endpoint.
5. Results import writes daily rows, and re-import doesn't duplicate them.
6. One real verify call is made with your credentials, if provided.
