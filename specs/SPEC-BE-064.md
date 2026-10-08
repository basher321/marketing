# SPEC-BE-064: Google Ads — connect, build, publish, results

Status: IMPLEMENTED (2026-10-02), plan approved. Verified 2026-10-02 on the live DB in a rolled-back transaction with real tokens, with this platform's HTTP answered by the `dev_fakes` fixtures (42/42 checks across all six platforms + YouTube):
- connect through Integrations (encrypted, connection test by this adapter);
- location search and media upload;
- a draft with dates passes local + platform validation;
- an injected failure mid-publish → 502, the draft unchanged, the error kept, no IDs, and the created objects cleaned up;
- publish → running with campaign, group and ad IDs;
- pause/resume of the campaign and a group;
- the results import writes daily rows; a re-import is idempotent; Analytics, CTR 7d and the campaign list read them.
**Not yet run against the real platform:** that needs your approved API access (see SPEC-BE-062). Field names follow the docs as of 2026-10 and are kept in this one file.

Implementation notes: `integrations/google_ads.py` (REST), also used for YouTube.
- `GOOGLE_ADS_API_VERSION=v25` in config.py (SPEC-BE-002/003 updated).
- Deviations: the **Video** campaign type is listed but unavailable, because the API can't create those subtypes. YouTube ads publish as **Demand Gen** video ads. The in-stream, in-feed and Shorts formats set the ad group's channel controls. **Bumper was removed** (it needs a Video campaign). YouTube ads gained a required logo image.
- Google applies locations and languages per campaign, so the union of the ad groups' is used.
- One atomic mutate creates everything; a failure creates nothing.
- To confirm on the first real run: the campaign date fields (`startDate`/`endDate`) and the Demand Gen field names.

Follows SPEC-BE-062's adapter contract. File: `backend/app/integrations/google_ads.py` (today a stub).

Amendment (2026-10-02): this adapter also publishes **YouTube** campaigns (registry key `youtube`, SPEC-BE-062 amendment):
- Demand Gen: a video ad with a YouTube video asset, headline ≤ 40, long headline ≤ 90, description ≤ 90, business name, final URL and CTA.
- Video: only the subtypes the API can create.
- Same connection, same atomic mutate. Results are stored with `source='google'` and split by `metadata.platform`.

## API
- Google Ads API over REST (`https://googleads.googleapis.com/vXX/`), not the gRPC client library, so no new dependency is needed.
- Use the newest supported major version at implementation time. v26 is due October 2026, v25 was released July 2026. Keep it in one constant, `GOOGLE_ADS_API_VERSION`, in `config.py`, documented in SPEC-BE-003, since versions now sunset roughly 12 months after release.

## Connect (catalog fields)
- `developer_token` (Basic or Standard access)
- OAuth client: `client_id`, `client_secret`, `refresh_token` (from Google's OAuth consent with the `adwords` scope)
- `customer_id` (10 digits, dashes stripped)
- optional `login_customer_id` (manager/MCC account)

The access token is refreshed through `oauth2.googleapis.com/token` and cached in memory until it expires. The verify test is `customers/{id}:searchStream` reading `customer.descriptive_name, currency_code, time_zone`.

## Campaign types and objectives
| Google channel | Label | Ours |
|---|---|---|
| SEARCH | Search (text ads on Google) | traffic or conversions or leads (the goal is picked separately) |
| PERFORMANCE_MAX | Performance Max (all Google channels) | conversions |
| DISPLAY | Display | awareness or traffic |
| DEMAND_GEN | Demand Gen (YouTube, Discover, Gmail) | engagement or traffic or conversions |
| VIDEO | YouTube video | awareness: only the subtypes the API allows creating; others are unavailable with the reason |

## Pathway fields
- **Campaign:**
  - Name, type, budget (`CampaignBudget`, daily, amount_micros), bidding (Maximize clicks, Maximize conversions with optional tCPA, Maximize conversion value with optional tROAS, Target impression share for Search), start/end.
  - Networks (Search: partners and Display toggles), locations and languages (Google sets these at campaign level), conversion goals.
  - Ad schedule.
- **Ad group (not used by Performance Max, which uses asset groups):**
  - Name, default CPC bid.
  - Keywords with match type (broad, phrase, exact), and negative keywords.
  - Audiences (observation or targeting).
- **Ads:**
  - Search: Responsive Search Ad, with 3–15 headlines (≤ 30 characters), 2–4 descriptions (≤ 90), final URL, paths 1/2 (≤ 15 each).
  - Display and Demand Gen: responsive display/Demand Gen ad, with images uploaded as assets (landscape 1.91:1, square 1:1, logo), headlines, long headline (≤ 90), descriptions, business name.
  - Performance Max: an asset group with final URL, 3–15 headlines, 1–5 long headlines, 2–5 descriptions, images, logos, optional YouTube video ids, and business name.

## Publish
- One `googleAds:mutate` request with temporary resource names (negative ids): budget → campaign (status PAUSED) → ad groups / asset group → criteria → ads/assets.
- Google applies a mutate **atomically** when `partialFailure=false`, so a failure creates nothing. That is the all-or-nothing rule here; no manual rollback is needed.
- When mode=active, a second mutate sets the campaign to ENABLED. If that step fails, the campaign is removed.
- Pause/resume: `status` PAUSED/ENABLED on campaign, ad_group or ad_group_ad.
- `validateOnly=true` backs `/validate`.

## Rules checked by validate
- The text limits above, and unique headlines.
- A Search ad group needs at least one keyword.
- A Performance Max asset group needs the asset minimums.
- The budget is greater than 0. Bidding targets are positive.
- Final URLs are https and well-formed.
- The account currency equals the tenant currency.

## Results
GAQL `segments.date, metrics.cost_micros, impressions, clicks, conversions, conversions_value` by campaign, last 3 days. Stored in `analytics_events` with `source='google'`.

## Acceptance (mocked HTTP, live DB, rolled-back transaction)
1. The token refresh and verify mapping work, and the login-customer-id header is sent when set.
2. Publish builds one atomic mutate with temporary ids, in micros. A mocked mutate error → 502 with nothing in the DB.
3. A Search, a Performance Max and a Demand Gen tree each validate and publish against the mock.
4. Pause/resume and the results import work.
5. A real verify call is made with your developer token, if provided.
