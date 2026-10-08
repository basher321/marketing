# SPEC-BE-067: Snapchat Ads — connect, build, publish, results

Status: IMPLEMENTED (2026-10-02), plan approved. Verified 2026-10-02 on the live DB in a rolled-back transaction with real tokens, with this platform's HTTP answered by the `dev_fakes` fixtures (42/42 checks across all six platforms + YouTube):
- connect through Integrations (encrypted, connection test by this adapter);
- location search and media upload;
- a draft with dates passes local + platform validation;
- an injected failure mid-publish → 502, the draft unchanged, the error kept, no IDs, and the created objects cleaned up;
- publish → running with campaign, group and ad IDs;
- pause/resume of the campaign and a group;
- the results import writes daily rows; a re-import is idempotent; Analytics, CTR 7d and the campaign list read them.
**Not yet run against the real platform:** that needs your approved API access (see SPEC-BE-062). Field names follow the docs as of 2026-10 and are kept in this one file.

Implementation notes: `integrations/snapchat_ads.py`.
- The access token is refreshed on demand (30-minute lifetime) and cached.
- Full-object PUT for pause/resume.
- Deviation: media over 32 MB (chunked upload) isn't supported; such files are refused with a clear message.
- Budgets are set per ad squad (validation says so); a campaign budget becomes a spend cap.

Follows SPEC-BE-062's adapter contract. New file: `backend/app/integrations/snapchat_ads.py`.

## API
- Snap Marketing API **v1**, `https://adsapi.snapchat.com/v1/`, OAuth2 bearer token.
- Refresh through `accounts.snapchat.com/login/oauth2/access_token`. Access tokens last about 30 minutes, so they're refreshed on demand and cached.
- 2026 change: the Campaign `objective` field is being phased out in favour of `objective_v2_properties`, and ad squads carry the optimisation goal. Use the current shape, and confirm it in the plan step.

## Connect
- Fields: `client_id`, `client_secret`, `refresh_token`, `ad_account_id`, `public_profile_id` (the brand profile ads run from).
- The verify test is `GET adaccounts/{id}` → name, currency and timezone.

## Objectives (`objective_v2_properties.objective_v2_type`)
| Snap | Ours |
|---|---|
| AWARENESS_AND_ENGAGEMENT | awareness or engagement |
| TRAFFIC | traffic |
| LEADS | leads |
| APP_PROMOTION | app_promotion |
| SALES | conversions |

## Pathway fields
- **Campaign:** name, status, start/end, optional spend cap (micros).
- **Ad squad:**
  - Type SNAP_ADS, placement (automatic, or Snapchat/Discover/Spotlight content).
  - Targeting: geos (country, region, metro, postal), age, gender, languages, interests (Snap Lifestyle Categories), custom/lookalike segments, device/OS.
  - Daily budget (micros, minimum 5 USD equivalent), bid strategy (AUTO_BID, LOWEST_COST_WITH_MAX_BID, TARGET_COST), optimisation goal (IMPRESSIONS, SWIPES, PIXEL_PURCHASE, APP_INSTALLS, …), pixel id, schedule.
- **Ad:**
  - Creative type: single image or video (9:16, uploaded through the media endpoints, chunked for video > 32 MB).
  - Brand name ≤ 25 characters, headline ≤ 34.
  - Attachment: web view URL, deep link, app install, or lead form. CTA.

## Publish
- Calls: campaign (PAUSED) → ad squads (PAUSED) → media → creatives → ads (ACTIVE).
- When mode=active, set the campaign and squads to ACTIVE.
- Rollback: DELETE ads, creatives, squads, then the campaign.
- Pause/resume: update `status` with a PUT of the entity.

## Rules checked by validate
- At least one geo.
- Ad squad minimum daily budget.
- 9:16 media, video 3–180 s.
- Text limits.
- The attachment URL is https.
- The optimisation goal fits the objective.

## Results
`campaigns/{id}/stats?granularity=DAY&fields=spend,impressions,swipes,conversion_purchases,conversion_purchases_value`. Stored with `source='snapchat'`. Spend is in micros.

## Acceptance
Same pattern as SPEC-BE-063, with mocked HTTP:
1. Token refresh on 401.
2. Create order.
3. Micros.
4. Reverse rollback.
5. Results import.
