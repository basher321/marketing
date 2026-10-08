# SPEC-BE-068: Pinterest Ads — connect, build, publish, results

Status: IMPLEMENTED (2026-10-02), plan approved. Verified 2026-10-02 on the live DB in a rolled-back transaction with real tokens, with this platform's HTTP answered by the `dev_fakes` fixtures (42/42 checks across all six platforms + YouTube):
- connect through Integrations (encrypted, connection test by this adapter);
- location search and media upload;
- a draft with dates passes local + platform validation;
- an injected failure mid-publish → 502, the draft unchanged, the error kept, no IDs, and the created objects cleaned up;
- publish → running with campaign, group and ad IDs;
- pause/resume of the campaign and a group;
- the results import writes daily rows; a re-import is idempotent; Analytics, CTR 7d and the campaign list read them.
**Not yet run against the real platform:** that needs your approved API access (see SPEC-BE-062). Field names follow the docs as of 2026-10 and are kept in this one file.

Implementation notes: `integrations/pinterest_ads.py`.
- Deviation: Pinterest has no standalone image upload, so image Pins take a public https **Image URL** (an editor field). Videos go through the media API.
- Rollback archives the campaign, ad group and ads, and deletes the new Pins.
- Age targeting still uses AGE_BUCKET until Pinterest retires buckets.

Follows SPEC-BE-062's adapter contract. New file: `backend/app/integrations/pinterest_ads.py`.

## API
- Pinterest API **v5**, `https://api.pinterest.com/v5/`, OAuth2 bearer token.
- Scopes: `ads:read`, `ads:write`, `pins:read`, `pins:write`, `boards:read`.
- Refresh through `oauth/token`. Access tokens last 30 days, refresh tokens 1 year.
- Ads writes need "Standard" API access.

## Connect
- Fields: `access_token`, `refresh_token`, `client_id`, `client_secret`, `ad_account_id`.
- The verify test is `GET ad_accounts/{id}` → name and currency.

## Objectives (`objective_type`)
| Pinterest | Ours |
|---|---|
| AWARENESS | awareness |
| VIDEO_VIEW / VIDEO_COMPLETION | awareness |
| CONSIDERATION | traffic |
| WEB_CONVERSION | conversions |
| CATALOG_SALES | conversions, unavailable unless a catalog exists |

## Pathway fields
- **Campaign:** name, objective, lifetime/daily spend cap (micro-currency), campaign budget optimisation on or off, start/end.
- **Ad group:**
  - Budget (daily or lifetime), bid strategy (AUTOMATIC_BID, MAX_BID, TARGET_AVG), billable event, optimisation goal.
  - Placement: ALL, BROWSE or SEARCH.
  - Targeting:
    - locations
    - languages
    - gender
    - age, using **min/max age** (age buckets are being deprecated in 2026)
    - interests and keywords
    - audiences
    - devices
  - Promotion ids (optional, up to 5).
  - Conversion tag (for WEB_CONVERSION).
- **Ad (Promoted Pin):** either an existing Pin id, or a new Pin created on a chosen board with:
  - image or video (uploaded through the media API)
  - title ≤ 100 characters
  - description ≤ 500
  - link (https)
  - alt text

## Publish
- Calls: campaigns (PAUSED) → ad_groups (PAUSED) → Pins (new ones only) → ads.
- When mode=active, set the campaign and groups to ACTIVE.
- Rollback: archive the ads, groups and campaign (Pinterest archives instead of deleting), then delete the created Pins.
- Pause/resume: `status` PAUSED/ACTIVE through the bulk PATCH endpoints.

## Rules checked by validate
- At least one location.
- Spend amounts are greater than 0, in micro-currency.
- MAX_BID needs a bid.
- Pin text limits.
- The link is https.
- Image 2:3 recommended (warning otherwise).
- Video 4 s–15 min.

## Results
`ad_accounts/{id}/campaigns/analytics` with daily granularity and columns SPEND_IN_MICRO_DOLLAR, IMPRESSION_1, CLICKTHROUGH_1, TOTAL_CONVERSIONS, TOTAL_CONVERSIONS_VALUE_IN_MICRO_DOLLAR. Stored with `source='pinterest'`.

## Acceptance
Same pattern as SPEC-BE-063, with mocked HTTP:
1. Token refresh.
2. Create order.
3. Micro-currency.
4. Rollback archives everything and deletes new Pins.
5. Results import.
