# SPEC-BE-065: LinkedIn Ads — connect, build, publish, results

Status: IMPLEMENTED (2026-10-02), plan approved. Verified 2026-10-02 on the live DB in a rolled-back transaction with real tokens, with this platform's HTTP answered by the `dev_fakes` fixtures (42/42 checks across all six platforms + YouTube):
- connect through Integrations (encrypted, connection test by this adapter);
- location search and media upload;
- a draft with dates passes local + platform validation;
- an injected failure mid-publish → 502, the draft unchanged, the error kept, no IDs, and the created objects cleaned up;
- publish → running with campaign, group and ad IDs;
- pause/resume of the campaign and a group;
- the results import writes daily rows; a re-import is idempotent; Analytics, CTR 7d and the campaign list read them.
**Not yet run against the real platform:** that needs your approved API access (see SPEC-BE-062). Field names follow the docs as of 2026-10 and are kept in this one file.

Implementation notes: `integrations/linkedin_ads.py`.
- `LINKEDIN_API_VERSION=202609` in config.py.
- Campaign groups and campaigns are created as DRAFT, then activated; on failure the drafts and dark posts are deleted.
- A 401 refreshes the token once (kept in memory).
- An end date is required (API 202605+).
- Integrations fields: access token, optional refresh token / client ID / client secret, ad account, organization URN.

Follows SPEC-BE-062's adapter contract. New file: `backend/app/integrations/linkedin_ads.py`.

## API
- LinkedIn Marketing API (REST), `https://api.linkedin.com/rest/`, with headers `Linkedin-Version: YYYYMM` and `X-Restli-Protocol-Version: 2.0.0`.
- Use the newest version at implementation time (202609 is listed as of September 2026), kept in one constant. LinkedIn retires versions about a year after release.
- Since 202605, a campaign create **must** include `endsAt`, or a run-until-paused equivalent. Confirm the exact rule against the docs in the plan step.

## Connect
- Fields: `access_token` (OAuth with `rw_ads` and `r_ads_reporting`), `refresh_token`, `client_id`, `client_secret`, `ad_account_id`, `organization_urn` (the Page that ads post as).
- The verify test is `GET adAccounts/{id}` → name, currency and status.
- The token is refreshed before it expires (60-day access tokens, 1-year refresh tokens).

## Hierarchy
LinkedIn's **campaign group** = our campaign. LinkedIn's **campaign** = our ad group. LinkedIn's **creative** = our ad.

## Objectives
| LinkedIn | Ours |
|---|---|
| BRAND_AWARENESS | awareness |
| WEBSITE_VISIT | traffic |
| ENGAGEMENT | engagement |
| VIDEO_VIEW | awareness |
| LEAD_GENERATION | leads |
| WEBSITE_CONVERSION | conversions |
| TALENT_LEADS / JOB_APPLICANT | unavailable (out of scope, with the reason) |

## Pathway fields
- **Campaign group:** name, total budget, run dates.
- **Campaign:**
  - Objective, format: single image, video, carousel, text ad, or document. Message/Conversation ads are out of scope and listed unavailable.
  - Targeting (`targetingCriteria`):
    - locations (required)
    - languages
    - company names, industries, company size
    - job titles, functions, seniorities, skills
    - matched audiences
    - Audience Expansion toggle
  - Budget (daily and/or total), bidding (maximum delivery, cost cap, manual CPC/CPM), schedule (`runSchedule`), conversions (conversion rule ids), lead form (for LEAD_GENERATION).
- **Creative:**
  - Text: intro ≤ 600 characters (150 recommended), headline ≤ 200 (70 recommended), description.
  - Image (1.2:1 / 1:1 / 1:1.91) or video uploaded through the Images/Videos API.
  - Landing URL and CTA.

## Publish
- Calls in order: campaign group (status DRAFT) → campaigns (DRAFT) → posts (`/rest/posts` as a dark post, owned by the organization) → creatives referencing the post.
- When mode=active, set the group and campaigns to ACTIVE.
- Rollback: delete the DRAFT entities (LinkedIn only allows deleting drafts, which is why everything is created as DRAFT first).
- Pause/resume: PAUSED / ACTIVE.

## Rules checked by validate
- At least one location.
- A minimum audience size of 300, using the audience counts API where available.
- Minimum daily budget: 10 USD equivalent.
- The text limits above.
- A lead form is required for LEAD_GENERATION.

## Results
`adAnalytics` with q=analytics, pivot CAMPAIGN, timeGranularity DAILY, fields costInLocalCurrency, impressions, clicks, externalWebsiteConversions. Stored with `source='linkedin'`.

## Acceptance
Same pattern as SPEC-BE-063, with mocked HTTP:
1. The version header is sent on every call.
2. Draft-then-activate order.
3. Rollback deletes the drafts.
4. Token refresh.
5. Results import.
