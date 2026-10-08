# SPEC-BE-075: Connected social accounts and organic publishing adapters

Status: IMPLEMENTED (code, 2026-10-03; approved by the user). Acceptance 2–7 pass against `httpx.MockTransport` / dev fakes (31 checks, no DB needed). **Pending:** the `linkedin` enum value (DDL) and criterion 1 on the live DB (Postgres unreachable). Nothing has been tried against the real platforms yet (needs the user's tokens). Part of the Marketing restructure (SPEC-FE-049/050, SPEC-BE-074…078).
Decisions (user, 2026-10-03): D4 = Facebook Page, Instagram, TikTok and LinkedIn company page in v1. X, YouTube Shorts and Pinterest come later.

> **Live DB not inspected yet** (Postgres unreachable 2026-10-03). The enum values come from `models/integration.py`.

## Purpose
Organic posts must go to the company's real social accounts. The integration catalog (`integrations/verify.py`) already has **Facebook Page**, **Instagram** and **TikTok Business** entries with pasted tokens and real connection tests, but the adapters in `integrations/facebook.py`, `instagram.py` and `tiktok.py` are stubs that post nothing. This spec makes them publish and adds LinkedIn company pages.

## Platforms in v1 (decision D4)
| Platform | Integration (`integration_provider`) | Publish API | Media |
|---|---|---|---|
| Facebook Page | `facebook` (page_id, Page access token) | Graph `/{page}/feed`, `/{page}/photos`, `/{page}/videos` | bytes are uploaded; text-only is allowed |
| Instagram (professional) | `instagram` (ig_account_id, token) | `/{ig}/media` → poll the container → `/{ig}/media_publish`; feed image, carousel (2–10), Reels, Stories | **needs a public https URL** (SPEC-BE-074) |
| TikTok | `tiktok` (access token) | Content Posting API: `creator_info/query` → `post/publish/video/init` (FILE_UPLOAD) or `content/init` (photo, PULL_FROM_URL) → `status/fetch` | video, or photos (photos need a verified URL domain) |
| LinkedIn company page | **new** `linkedin` (organization URN, token with `w_organization_social`) | `/rest/posts`, plus `/rest/images` / `/rest/videos` initializeUpload | bytes are uploaded; text-only is allowed |

**Additive DDL:** `ALTER TYPE integration_provider ADD VALUE 'linkedin';`. The catalog gets a "LinkedIn Page" entry (Social).

X, YouTube Shorts and Pinterest organic posting are out of v1. They are listed as follow-ups: X needs a paid API tier, and YouTube needs OAuth upload scopes and quota.

**Known platform limits** (shown to the user, never worked around):
- **TikTok:** until the developer app passes TikTok's audit, API posts are **private (SELF_ONLY)**. The UI must show the creator's privacy options from `creator_info`, and the user must pick one.
- **Instagram:** at most 100 API-published posts per 24h (`content_publishing_limit` is checked before publishing).
- **LinkedIn:** organization posting needs the Community Management API approval.
- **Facebook:** `pages_manage_posts`.

The connection test (`verify.py`) checks these permissions and reports which ones are missing.

## Connected accounts
- `GET /social/accounts` (viewer+) returns one item per connected social integration:
  - `{integration_id, platform, account_name, handle, avatar_url, status (connected|expired|error|missing_permissions), capabilities {text_only, image, carousel, video, story, reel}, limits {caption_max, hashtags_max, video_max_s}, last_error, last_published_at}`.
- Names and avatars are fetched at connect/test time and stored in `integrations.metadata.profile`; they are not fetched on every list.
- **Optional shortcut:** when the Meta Ads connection (SPEC-BE-054) already has a `page_id`/`instagram_id`, the accounts page offers "Use my Meta connection". It derives the Page token with `GET /{page_id}?fields=access_token` and fills the `facebook`/`instagram` integrations. This works only if that token has the publish permissions; otherwise the reason is shown.

## Adapter contract (`integrations/social_base.py`, new)
```python
class SocialAdapter(Protocol):
    platform: str
    def check(self, creds) -> AccountProfile                  # profile + permissions + limits
    def publish(self, creds, post: PostPayload) -> PublishResult  # external_id, external_url
    def status(self, creds, external_ref) -> PublishResult      # for async containers/uploads
    def metrics(self, creds, external_ids: list[str]) -> list[PostMetrics]   # SPEC-BE-078
```
- `PostPayload`: text (caption with hashtags and CTA already composed), link_url, media (list of `{media_id, kind, url, bytes_reader}`), format (`post|carousel|reel|story|video`), platform options (e.g. TikTok privacy, disable_comment).
- All calls go through `base_adapter.http`/`client_factory`, so `httpx.MockTransport` and `dev_fakes` can intercept them.
- **Errors** map to `PlatformError(transient: bool)`:
  - **transient:** HTTP 5xx, 429, network errors, Meta codes 1/2/4/17/341;
  - **auth:** the integration is marked `expired`;
  - **permanent:** anything else, with the platform's message kept.
- **Tokens:** decrypted only inside the adapter call, and never logged.

## dev_fakes
`integrations/dev_fakes.py` answers the four platforms' publish/status/metrics endpoints, with `FAIL`/`FAIL_SKIP` injection as it does for the ad platforms.

## Acceptance criteria (live DB, rolled back, `META_FAKE_TRANSPORT=true` / MockTransport)
1. Saving and testing each of the four integrations with fake answers → `GET /social/accounts` lists them with their profile and capabilities. A missing permission → `missing_permissions`, with its name.
2. Facebook: text, single photo, multi-photo and video payloads produce the right Graph calls (checked on the recorded requests), and the result has `external_id` and `external_url`.
3. Instagram:
   - an image → container → `status_code=FINISHED` poll → `media_publish`;
   - a localhost `PUBLIC_BASE_URL` → 409 before any call;
   - the publishing limit reached → a permanent error with the reason.
4. TikTok: `creator_info` is called first; a privacy level outside its list → 422; a video upload follows the init/upload/status sequence.
5. LinkedIn: image initializeUpload → PUT → `/rest/posts` with the `LinkedIn-Version` header.
6. A 429 → `PlatformError(transient=True)`. An expired token → integration `expired`, `PlatformError(transient=False)`.
7. A grep of the captured logs finds no token.

## Target files
- New: `integrations/social_base.py`, `integrations/linkedin.py`, `api/v1/social.py`, `services/social_account_service.py`, `schemas/social.py`.
- Changed: `integrations/facebook.py`, `instagram.py`, `tiktok.py` (stubs → adapters), `integrations/verify.py` (catalog: LinkedIn Page, permission checks), `integrations/dev_fakes.py`, `models/integration.py` (+`linkedin`), `api/router.py`.

## Out of scope
OAuth connect flows for these platforms (the user pastes tokens, as in SPEC-BE-052), comments and DMs, and X, YouTube and Pinterest organic posting.

## Implementation notes (2026-10-03)
- **Adapters** are modules (`check / publish / poll / metrics`), not classes. The old `FacebookAdapter` / `InstagramAdapter` / `TikTokAdapter` stubs were unused and are replaced.
- **Errors:** `SocialError` extends `PlatformError` with `transient`.
- **Connection test:** `verify.verify()` runs the adapter's `check()` for the four social providers, and the result's `profile` is stored in `integrations.metadata.profile`. The old Facebook/Instagram/TikTok branches of `_check()` were removed; TikTok used `user/info`, it now uses Content Posting's `creator_info`.
- **Permissions:** checked through `GET /me/permissions`. A Page token usually can't list them, so `missing_permissions = null` means "couldn't tell", not "OK".
- **Instagram:** "impressions" for new media was retired in 2025, so `views` is stored as impressions (commented in code).
- **TikTok:** the post's privacy level must be one of `creator_info.privacy_level_options` (422 otherwise). Before scheduling, the profile is refreshed.
- **LinkedIn:** commentary is escaped in "little text"; hashtags become `{hashtag|\#|tag}`.
- **Dev fakes:**
  - Graph organic endpoints, with Instagram containers that answer `IN_PROGRESS` for `IG_VIDEO_POLLS` reads and `IG_QUOTA_USED` for the limit;
  - TikTok Content Posting (`open.tiktokapis.com` / `open-upload…`, `TIKTOK_POLLS`);
  - LinkedIn `organizations` and share statistics;
  - Meta failure injection: `FAIL["meta"]` + `META_FAIL_ERROR`.
- **Checks passed (31):**
  - Facebook text / photo / multi-photo / video call sequences;
  - Instagram image, reel (processing → poll → published), carousel, media required, quota reached → permanent;
  - Meta codes 2 → transient, 190 → auth, 100 → permanent;
  - TikTok `creator_info`, bad privacy 422, init + chunk PUT + status poll, photo;
  - LinkedIn little-text, image, video init/put/finalize, article, bad URN 422;
  - metrics for all four;
  - `verify()` returns the profile.
- **Pending:** criterion 1 needs the DB. Criterion 7 (no token in logs) is designed in (tokens never passed to loggers) and needs a log grep during the live run.
