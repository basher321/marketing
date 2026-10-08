# SPEC-BE-081: Organic performance insights as AI feedback

Status: IMPLEMENTED (code, 2026-10-03). The prompt block, the system-prompt rule and the hour/format grouping are checked without a DB; the `organic_insights` action is registered (risk `read`). `ruff`/`mypy` add no errors. **Pending:** acceptance 1–6 on the live DB. Requested by the user (item 13: "Use analytics as AI feedback; automatic publishing/changes should follow the user's approval/automation policy"). Builds on SPEC-BE-076 (organic content) and SPEC-BE-078 (organic results import). Frontend: SPEC-FE-052.

## Purpose
Imported post results (`analytics_events`, `event_type='organic_post_metrics'`) are shown in Organic Analytics but don't influence anything. This spec turns them into:
1. a deterministic **insights** summary (what worked, when, and on which platform), and
2. a short **performance context** added to the AI copy prompts, so new captions lean on what performed well.

Nothing is published or changed automatically: insights are advisory, and AI output still needs approval (SPEC-BE-076).

## Insights (`organic_service.insights(db, tenant_id, days=60)`)
Over the company's published organic posts (`scheduled_posts` + `content_assets.format='organic_post'`) in the last `days` days, using the latest snapshot of each metric per post:
- **engagements** = likes + comments + shares + saves (the known ones); **engagement rate** = engagements / impressions × 100 (null without impressions). These are the same definitions as SPEC-BE-078.
- **Per platform** (only when ≥ 3 posts have results there):
  - `posts_with_results`, `avg_engagement_rate`;
  - `best_hours`: the up to 3 local hours (tenant timezone) with the highest average engagement rate, each with ≥ 2 posts;
  - `best_format`: post / reel / carousel / video / story, with the highest average rate (≥ 2 posts);
  - `hashtags`: the average hashtag count of the top third vs. the bottom third.
- **Top posts:** up to 5 by engagement rate (platform, excerpt, rate, published_at, external_url).
- **Bottom posts:** up to 3 (same fields).
- **Lines:** up to 6 plain-language sentences built from the numbers above, e.g. "Instagram: reels averaged 4.8% engagement vs 2.1% for single images (9 posts)." "Facebook posts published 19:00–20:00 did best." A line is produced only from data that meets the minimums. Never an estimate.
- `has_data = false` with a reason ("Not enough results yet: insights need at least 3 published posts with imported results on a platform.") when no platform meets the minimum.

`GET /organic/insights?days=30|60|90` (viewer+, default 60) → `{has_data, reason, days, timezone, platforms: [...], top_posts, bottom_posts, lines, generated_at}`.

## AI feedback
`performance_context(db, tenant_id, platforms)` → a text block of at most 1 200 characters: the `lines` for the requested platforms, plus up to 3 top-post excerpts (120 characters each) labelled "examples that performed well — learn the angle, don't copy". It's empty when `has_data` is false.

It's added to:
- `organic_adapter.generation_prompt` (AI posts, Command Chat organic actions);
- `adapt_prompt`;
- `regenerate_prompt`.

All three get an optional `performance` argument and put it in a `<performance>` block before the brief. The result's `extra_metadata.performance_used = true/false` is recorded on the organic content, so the UI can say "Written with your recent results in mind."

Instructions inside imported text are data: excerpts are wrapped and labelled as examples, and the system prompt says to ignore instructions inside them.

## Command Chat
New read action `organic_insights` (risk `read`, module `organic`, params `{days?}`): it runs at once and replies with the `lines` (or the reason). Registered in `ai/command_actions.py`.

## Acceptance criteria (live DB, rolled back, `LLM_PROVIDER=fixture`)
1. No results → `has_data=false` with the reason; `performance_context` is empty; AI posts work as before (`performance_used=false`).
2. Seeded results (8 Instagram posts: 4 reels with a higher rate, 4 images; mixed hours) → Instagram `best_format="reel"`, `best_hours` ordered by rate, and a line naming reels vs images with the post count. Facebook with 2 posts → no Facebook entry.
3. AI posts with those results → the prompt sent to the provider (captured through the fixture/creative hook) contains the `<performance>` block with the Instagram line; `performance_used=true`.
4. Regenerate on a version also receives the block.
5. Command Chat "what's working on Instagram?" with a fixture plan for `organic_insights` → a read step that completes at once with the lines.
6. Tenant isolation: another tenant's results never appear.
7. `ruff check` and `mypy` add no new errors.

## Target files
- Changed: `app/services/organic_service.py` (`insights`, `performance_context`, prompts get the context), `app/ai/prompts/organic_adapter.py` (optional `performance` argument, system-prompt line), `app/api/v1/organic.py` + `app/schemas/organic.py` (`GET /organic/insights`), `app/ai/command_actions.py` (`organic_insights`)

## Out of scope
Automatic re-posting, automatic schedule changes, paid-campaign recommendations, LLM-written insights (the lines are computed, not generated).
