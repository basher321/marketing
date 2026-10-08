# SPEC-BE-083: SocialAPI.ai as another way to post and answer on social media

Status: IMPLEMENTED and verified (2026-10-07). On the live Postgres, inside rolled-back
transactions with `dev_fakes.install()` and real register/login tokens, 66 of 66 checks
pass across three runs, covering acceptance 1–9. Nothing persisted (the temporary
company was gone after rollback). Acceptance 10 passes: `ruff check app` shows the
unchanged baseline of 1 error, and `mypy app` shows the baseline of 7 errors in 5 files.
Nothing has been tried against the real api.social-api.ai yet; that needs the user's own
`sapi_key_…`. Requested by the user, who chose "Organic + inbox" after being told that
SocialAPI has no paid-ads features. Frontend: SPEC-FE-054. Everything else in the
software is unchanged, as the user asked.

## Context

https://social-api.ai/ is a third-party API that works across 13 platforms.

**What it offers:**
- **Publishing:** organic publishing and scheduling on Instagram, Facebook, Threads,
  TikTok, LinkedIn, YouTube, X, Bluesky, Pinterest, Google Business Profile, Telegram,
  WhatsApp and Zalo.
- **Media and analytics:** media upload, post metrics and daily account analytics.
- **Unified inbox:** comments, DMs and reviews.

**What it does not offer:** campaigns, budgets, targeting or boosting. It holds the
platform tokens itself (managed OAuth); we only hold the company's SocialAPI key
(`Authorization: Bearer sapi_key_…`). API reference: https://docs.social-api.ai/llms.txt

**Design (approved):** the integration is self-contained, next to the direct
integrations (SPEC-BE-075/080).
- Posts made here live in SocialAPI, not in `organic_contents` / `scheduled_posts`.
- The inbox is read live from SocialAPI, not copied into `conversations`.
- `organic_service`, `conversation_service`, the scheduler and the enums are untouched.

## Functional requirements

1. **Key.** `GET/PUT/DELETE /socialapi/key` and `POST /socialapi/key/test`.
   - **Storage:** `tenants.settings.socialapi = {key_enc, brand_id, last_ok_at,
     last_error}`. The key is Fernet-encrypted, and only `••••` plus the last 4
     characters is returned. **No DDL.**
   - **Save:** PUT tests the key first with `GET /accounts`. A key SocialAPI rejects
     (401) is not saved and returns 422. If SocialAPI is down, the key is saved with
     `last_error`.
   - **Revoked key:** a key rejected on any later call is recorded on the key card
     (`status: error`).
   - **Delete:** forgets the key. The accounts stay connected in SocialAPI.
2. **Accounts.**
   - **List:** `GET /socialapi/accounts` returns every account the key can reach, plus
     `connectable` (9 OAuth platforms).
   - **Connect:** `POST /socialapi/accounts/connect {platform}` connects into the
     company's SocialAPI brand. The brand is found by company name or created, then
     stored. It returns `auth_url`, with `redirect_uri` =
     `FRONTEND_BASE_URL/marketing/organic/socialapi/callback` and a signed `state` (JWT,
     30 min, bound to the tenant and user).
   - **Callback:** `POST /socialapi/accounts/callback` checks the state and handles the
     three outcomes:
     - `success`: the account is connected;
     - `error`: returns 422 with the platform's reason;
     - `selection_required` (Facebook Pages / Google locations): lists the choices.
   - **Select:** `POST /socialapi/accounts/select` assigns the chosen Page or location
     to the brand.
   - **Disconnect:** `DELETE /socialapi/accounts/{id}`.
   - **Pinterest boards:** `GET /socialapi/accounts/{id}/boards`.
3. **Posts.** `POST /socialapi/posts`:
   - **Fields:** `{text, title?, targets[{account_id, board_id?}], media_ids[],
     first_comment?, mode: now|schedule|draft, scheduled_at?}`.
   - **Validation:**
     - `scheduled_at` must be timezone-aware and in the future;
     - each account may appear once;
     - targets must be connected accounts;
     - every Pinterest target needs a board.
   - **Media:** `media_ids` are our media library ids (`/api/v1/media`). Their bytes are
     uploaded to SocialAPI (`POST /media/upload`, 50 MB max) and sent as `source_type:
     media_id`.
   - **Results:** a 207 partial success is an answer, not an error; each target carries
     its own error.
   - **Other routes:**
     - list: `GET /socialapi/posts?status&platform&q&cursor`;
     - read: `GET /socialapi/posts/{id}`, which adds fresh metrics for published and
       partial posts;
     - `POST …/{id}/publish`;
     - `POST …/{id}/retry`;
     - `DELETE …/{id}` returns the per-account outcome: deleted, not_supported or
       failed;
     - `GET /socialapi/constraints` returns the text, carousel, video and scheduling
       limits for each platform.
4. **Analytics.** `GET /socialapi/accounts/{id}/analytics?range=7d|30d|90d`. A point
   SocialAPI didn't report stays null; it is never estimated.
5. **Inbox, read live.**
   - **Messages:** `GET /socialapi/inbox/conversations` (+ `/{id}/messages`, oldest
     first) and `POST …/{id}/messages {account_id, text}`.
   - **Comments:** `GET /socialapi/inbox/comments` (posts with comments) and `GET
     …/comments/{platform_post_id}?account_id`.
     - Reply: `POST …/{post_id}/reply {account_id, comment_id, text}`.
     - Moderate: `POST …/{post_id}/{comment_id}/moderate {account_id, action:
       hide|unhide|delete}`.
   - **Reviews:** `GET /socialapi/inbox/reviews/{account_id}` and `POST
     …/reviews/{id}/reply`. Google holds replies as PENDING until it approves them, and
     the response says so.
6. **AI draft.** `POST /socialapi/inbox/draft-reply {history[{role, text}]}` reuses the
   Customer Service drafter (`reply_drafter.generate_reply_draft`): brand voice, grounded
   in KB/FAQs/policies, and moderated. It is never sent automatically.
7. **Roles.**
   - viewer+: reads;
   - agent+: sends DMs, replies to comments and reviews, moderates, and drafts;
   - manager+: key, accounts and posts.
8. **Errors.** SocialAPI's `error.message` is shown as is.
   - 401 → 422 (key rejected);
   - 400/409/413/422 → 422;
   - 402/403 → 403;
   - 404 → 404;
   - 429 → 429;
   - 5xx/network → 502/504.
   - No key → 409 "Add your SocialAPI key first…".
9. **Audit.** Every write adds an `audit_log` row: `socialapi.*`, `resource_type` =
   tenant, SocialAPI ids in the metadata. The key and any message, caption or review text
   never go into the audit log or the logs.

## Acceptance criteria (all pass, 2026-10-07)

1. Key: not configured → 409 on reads; a bad key gets 422 and isn't saved; a good key is
   connected, masked, and encrypted at rest; test; delete, then delete again → 404; a
   revoked key shows on the key card.
2. Connect: auth_url → our callback; success → connected; Facebook selection → 2 choices
   → select; the brand is created once and reused; forged state → 400; denied → 422 with
   the reason.
3. Posts: unknown account, Pinterest without a board, schedule without a time or in the
   past → 422; publish now with a library image → published with permalinks; schedule;
   list; metrics; publish now; delete → per-account outcome; then 404.
4. Inbox: conversations, messages, send, then the reply appears in the thread; commented
   posts, comments, reply, hide; reviews with the average, and reply → pending message.
5. AI draft returns the no-grounding fallback (or 503 with no AI model).
6. Analytics 7/30 days; a bad range → 422; constraints.
7. Disconnect; unknown → 404; SocialAPI's own error text is surfaced.
8. Viewer: reads are OK; post, reply, key and connect → 403. Unauthenticated → 401.
9. Audit rows exist, with no key, caption or DM text. The rollback leaves nothing
   behind.
10. Lint/type baseline unchanged.

## Files

- New:
  - `backend/app/integrations/socialapi.py` (client)
  - `backend/app/services/socialapi_service.py`
  - `backend/app/schemas/socialapi.py`
  - `backend/app/api/v1/socialapi.py`
- Changed:
  - `backend/app/api/router.py` (one router line)
  - `backend/app/integrations/dev_fakes.py` (an `api.social-api.ai` fixture host; the
    key `sapi_key_bad` answers 401; `FAIL["socialapi"]` injects an error)

## Known limits

- **No paid ads:** SocialAPI has none.
- **DMs:** Instagram/Facebook only (24-hour window). LinkedIn and TikTok DMs aren't
  available.
- **Reviews:** Google Business Profile only.
- **X/Twitter:** listed by SocialAPI as "coming soon"; its own error shows if refused.
- **Direct-auth platforms:** Bluesky and Telegram need credentials in `metadata` and
  aren't offered in the connect list yet.
- **Not in our dashboards:** SocialAPI posts don't appear in the Organic calendar,
  history or analytics, and the AI Command Chat has no SocialAPI actions.
- **Media uploads:** each post re-uploads its media.
- **Dev fakes:** with `META_FAKE_TRANSPORT=true`, SocialAPI calls are answered from
  fixtures too.
