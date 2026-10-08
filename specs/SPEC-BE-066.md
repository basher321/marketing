# SPEC-BE-066: X (Twitter) Ads — connect, build, publish, results

Status: IMPLEMENTED (2026-10-02), plan approved. Verified 2026-10-02 on the live DB in a rolled-back transaction with real tokens, with this platform's HTTP answered by the `dev_fakes` fixtures (42/42 checks across all six platforms + YouTube):
- connect through Integrations (encrypted, connection test by this adapter);
- location search and media upload;
- a draft with dates passes local + platform validation;
- an injected failure mid-publish → 502, the draft unchanged, the error kept, no IDs, and the created objects cleaned up;
- publish → running with campaign, group and ad IDs;
- pause/resume of the campaign and a group;
- the results import writes daily rows; a re-import is idempotent; Analytics, CTR 7d and the campaign list read them.
**Not yet run against the real platform:** that needs your approved API access (see SPEC-BE-062). Field names follow the docs as of 2026-10 and are kept in this one file.

Implementation notes: `integrations/x_ads.py`.
- The OAuth 1.0a signer reproduces X's documented example signature exactly (`hCtSmYh+iHYCEqBWrE7C7hYmtUk=`).
- Posts are nullcast; website cards go through the cards endpoint. Promoted posts pause with `paused`.
- Stats are pulled in 7-day windows. X reports no conversion value here, so ROAS stays null.

Follows SPEC-BE-062's adapter contract. New file: `backend/app/integrations/x_ads.py`.

## API
- X Ads API **v12**, `https://ads-api.x.com/12/`.
- **OAuth 1.0a** user context is required for ad writes: consumer key and secret, plus access token and secret. Requests are signed with HMAC-SHA1 in our own small signer over `httpx`, so no new dependency is needed. The signer is unit-tested against X's documented signature example.
- Ads API access is a separate X approval on top of a developer app.

## Connect
- Fields: `consumer_key`, `consumer_secret`, `access_token`, `access_token_secret`, `account_id`. Optional: `funding_instrument_id`; the first active one is used otherwise.
- The verify test is `GET accounts/{id}` → name, plus `funding_instruments` → currency.

## Objectives (`objective`)
| X | Ours |
|---|---|
| REACH | reach |
| ENGAGEMENTS | engagement |
| VIDEO_VIEWS | awareness |
| WEBSITE_CLICKS | traffic |
| WEBSITE_CONVERSIONS | conversions |
| APP_INSTALLS | app_promotion |
| FOLLOWERS | engagement |

## Pathway fields
- **Campaign:** name, funding instrument, daily budget, total budget, start/end.
- **Line item:**
  - Objective, placements (ALL_ON_TWITTER, PUBLISHER_NETWORK), bid strategy (AUTO, MAX, TARGET), bid amount, pay-by.
  - Targeting criteria: locations, languages, gender, age buckets, interests, follower look-alikes, keywords, conversation topics, tailored audiences, devices/platforms.
- **Promoted post:** either pick an existing post, or create a new promotable-only ("nullcast") post. The text is ≤ 280 characters, with media uploaded via the media upload endpoint and a website card (URL, headline) for click and conversion objectives.

## Publish
- Calls: campaign (`entity_status` PAUSED) → line items (PAUSED) → targeting criteria (batch) → cards/posts → promoted_tweets.
- When mode=active, set the campaign and line items to ACTIVE.
- Rollback: DELETE the line items, then the campaign (X allows soft-deleting them), then the created nullcast posts.
- Pause/resume: `entity_status`.
- Limits: 100 line items per campaign and 256 active per account. Our cap of 10 per campaign stays below both.

## Rules checked by validate
- At least one targeting criterion with a location.
- Bid amount for MAX/TARGET.
- Post length ≤ 280 (URLs count as 23 characters).
- Card URL is https.
- Funding instrument is active and has budget.

## Results
Synchronous `stats/accounts/{id}` for entity CAMPAIGN, metric groups ENGAGEMENT and BILLING, granularity DAY, segmented by campaign, at most 7-day windows. Stored with `source='x'`. Spend is in micros.

## Acceptance
Same pattern as SPEC-BE-063, with mocked HTTP:
1. OAuth1 signatures match X's reference vector.
2. Create order and PAUSED-first.
3. Rollback deletes in reverse.
4. Results import.
