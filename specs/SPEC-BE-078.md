# SPEC-BE-078: Organic analytics and Command Chat control of Organic and Paid Marketing

Status: IMPLEMENTED (code, 2026-10-03; approved by the user). Plan validation for all four example commands passes without a DB (15 checks). **Pending:** acceptance 1–8 end to end on the live DB with `LLM_PROVIDER=fixture` (Postgres unreachable). Depends on SPEC-BE-075/076/077.

## Part A: Organic analytics
**Import:**
- A job `organic_metrics` runs every 6 h, plus on demand (`POST /analytics/organic/import`, manager+, 5-minute throttle as in SPEC-BE-056).
- For each post published in the last 30 days, it calls the adapter's `metrics()` (SPEC-BE-075) and writes daily snapshot rows to `analytics_events`:
  - `event_type = 'organic_post_metrics'`, `entity_type = 'scheduled_post'`, `entity_id = <post id>`;
  - `source = 'organic_<platform>'`, so the ad-results queries that read `AD_RESULT_SOURCES` never pick these up;
  - `metric` ∈ impressions, reach, likes, comments, shares, saves, video_views, clicks;
  - `dimensions = {platform, integration_id}`.
- Re-importing replaces that day's snapshot (delete + insert in one transaction).

**Rules:**
- Metric names per platform are confirmed against each API at implementation time; for example, Meta retired several Page/post insights metrics in 2025.
- A metric a platform doesn't give is **null, never estimated**; this is the same rule as SPEC-BE-050.
- TikTok metrics need the `video.list` scope; without it they are null, with the reason.

**Report:** `GET /analytics/organic?range=7d|30d|90d` (viewer+). It is bucketed by tenant-local day and zero-fills posts-published counts, while metrics stay null where no data exists. It returns:
- `totals` per metric (null when no source data);
- `by_platform`: posts published, impressions, engagements, engagement rate = engagements ÷ impressions (null if impressions are null or 0);
- `daily` series;
- `top_posts` (by engagements, max 10, with platform, caption excerpt, external_url, published_at).

## Part B: Command Chat
New actions in `ai/command_actions.py`, module `organic`. The existing approval policy applies unchanged:
- **read** runs at once;
- **draft** runs at once for manager+;
- **change** needs a manager+ approval other than the requester (the owner's own command auto-approves);
- **spend** needs an explicit owner approval.

| Action | Risk | Params (strict) | Does |
|---|---|---|---|
| `inspect_organic` | read | `{status?, platform?, days?}` | scheduled/published/failed posts |
| `inspect_organic_analytics` | read | `{range?}` | Part A report summary |
| `create_organic_posts` | draft | `{count 1–30, brief, product_skus?, platforms[], media: none\|product_photos\|generate_photo\|generate_video, tone?}` | N AI contents (SPEC-BE-076 AI mode), each adapted per platform; returns `content_ids` |
| `generate_photo` | draft | SPEC-BE-077 photo request | starts the job and **waits for it** (the plan runs in the background) → `media_id`, `generation_id` |
| `generate_video` | draft | SPEC-BE-077 video request | same; the reply states the effective duration |
| `create_organic_post` | draft | `{caption?, brief?, media_id? \| $n.media_id, platforms[]}` | one content, using a generated or given media item |
| `regenerate_organic_copy` | draft | `{content_id? \| version_id?, parts[], instruction?, keep_media: true}` | SPEC-BE-076 regenerate; the media is never touched |
| `schedule_organic_posts` | change | `{content_ids \| $n.content_ids, start_date?, time_local, timezone?, spread: "one_per_day"\|"all_at_once", platforms?}` | approves the AI content and schedules it |
| `publish_organic_now` | change | `{content_id \| version_id}` | publish now |
| `cancel_organic_post` / `reschedule_organic_post` | change | `{post_id, scheduled_at_local?, timezone?}` | |

- The `schedule_post` "unavailable" stub is removed (replaced by `schedule_organic_posts`, with an alias `schedule_post`).
- The existing Meta and campaign actions are **unchanged**. Their module labels show as "Paid Marketing" in plan cards, and their descriptions say "paid".

**Context resolution** ("this", "the caption", "that image"): the plan builder gets the IDs of organic contents, versions, generations and media created in the **same conversation** (from earlier plans' step outputs in `orchestrator_plans.actions`) as context. "The caption" means the most recent content. If it is ambiguous, the fixed question "Which post do you mean?" is asked with the candidates. IDs are never guessed.

**Time words:** "tomorrow at 8 PM" and "over the next 7 days" are resolved by the LLM into `start_date`/`time_local`, using the tenant's timezone and today's tenant-local date, which go into the prompt. The plan card shows the resolved local times for the user to check before approving.

## Acceptance criteria (live DB, rolled back, `LLM_PROVIDER=fixture`, dev_fakes, `INLINE_JOBS`)
1. "Create 7 organic posts for my new product and schedule them for Facebook and Instagram over the next 7 days." → plan: `create_organic_posts` (count 7, platforms fb+ig) → `schedule_organic_posts` (one_per_day). Drafts are created at once.
   - Manager requester: scheduling waits for another manager's approval.
   - Owner requester: it auto-approves, and 14 `scheduled` posts exist on 7 consecutive tenant-local days.
2. "Generate a 15-second product video using this prompt: …" → `generate_video` → job succeeded; the reply states the effective duration; a media item exists.
3. "Create a product photo, write the caption and schedule tomorrow at 8 PM." → `generate_photo` → `create_organic_post` (`$1.media_id`) → `schedule_organic_posts` at tomorrow 20:00 tenant-local (shown in the plan card).
4. "Regenerate the caption but keep the image unchanged." (same conversation) → `regenerate_organic_copy` on the post from criterion 3; the caption changed and `media_ids` are identical.
5. Same request in a new conversation with two candidate posts → the "Which post do you mean?" question.
6. "Show my organic results for the last 30 days" → `inspect_organic_analytics`; metrics with no data are reported as "no data yet", not 0.
7. Paid: "Pause my Meta campaign X" still works through `pause_meta` (regression).
8. Organic metrics import with fake platform data → rows with `source='organic_facebook'` etc.; `GET /analytics/ads` totals are unchanged (no leak into ad results).

## Target files
- Changed: `ai/command_actions.py`, `ai/prompts/` (planner prompt: organic examples, tenant-local date), `services/orchestrator_service.py` (conversation context IDs), `services/analytics_service.py` + `api/v1/analytics.py` + schema (organic report and import), `workers/schedules.py` + `workers/tasks/analytics_tasks.py` (organic import; the stub body becomes real for this job only).
- `CLAUDE.md`: an Organic Marketing section once implemented.

## Out of scope
Competitor analytics, follower growth history (needs per-account daily snapshots; follow-up), and auto-reposting top posts as ads.

## Implementation notes (2026-10-03)
- **"Same conversation" (deviation):** Command Chat is one thread per company; there are no separate conversations. "The caption" / "that image" resolve from `recent_organic` / `recent_media`: organic items this company's chat created in the last 24 hours (from `orchestrator_plans.actions[].result`), newest first. Criterion 5 becomes "several candidate posts from the latest step → the fixed question 'Which post do you mean?'" (`content_id` is required; when the planner omits it, the question comes from `FIELD_QUESTIONS`).
- **Planner context:** it also gets `today_local` / `now_local` (company timezone) and `social_accounts`, plus rules that keep Paid and Organic separate and handle "over the next N days" / "tomorrow at 8 PM".
- **Scheduling semantics:** `schedule_organic_posts` approves AI content as part of the step. It's a `change` action, so it only runs after the plan's approval, or at once on the owner's own command. With no `start_date` and today's slot already past, it starts tomorrow.
- **Refs:** `resolve_refs` now passes list outputs through (e.g. `$1.content_ids`).
- **Alias:** `schedule_post` resolves to `schedule_organic_posts`. A workflow-queued `schedule_post` approval (workflow_engine) had no executor before; on approval it now fails parameter validation with a message instead of "can't be executed". Real workflow → organic scheduling is not built.
- **`create_organic_posts`:** `media: product_photos` copies the products' https photos into the media library (`source='catalog'`).
- **Plan cards:** the module label is "Organic Marketing" for organic actions and "Paid Marketing" / "Paid Marketing · Meta" for campaign actions.
- **Analytics:**
  - import every 6 h (`organic_metrics` job) or on demand `POST /analytics/organic/import` (manager+, 5-minute throttle on the last import);
  - `GET /analytics/organic?range=`;
  - each post's latest snapshot is attributed to its publish day;
  - engagements = likes + comments + shares + saves (null when none were reported);
  - rate = engagements ÷ impressions.
- **No-DB checks (pass):**
  - the four example plans validate, with risks: drafts auto; scheduling needs approval for a manager and auto for the owner;
  - `$1.content_ids` list and `$2.content_id` refs resolve;
  - a missing time → "At what time…"; a missing `content_id` → "Which post do you mean?";
  - viewers can read but not draft; bad time format refused; `pause_meta` (paid) still registered.
- **Pending (live DB):** acceptance 1–8 end to end.
