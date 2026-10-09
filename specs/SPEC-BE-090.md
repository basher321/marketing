# SPEC-BE-090: Command Chat publishes Facebook/Instagram ad campaigns through Zernio

Status: IMPLEMENTED and verified (2026-10-09), approved by the user ("approve and check publishes
through zerino").
- Dev fakes, live Postgres, one rolled-back transaction: 12/12 checks (AC1-AC5). AC6: stub suite
  31/31, ruff 1 and mypy 7 (baselines).
- Real run (pilotsonic, Claude claude-sonnet-5-5, real zernio.com, DB rolled back): the message
  "Create a paused Facebook traffic ad campaign on the Grifigo ad account …" planned
  `publish_zernio_campaign` (spend, owner approval, every value from the message, the account name
  mapped to `act_3434063673422474`); after approval Zernio created Meta campaign
  `120251999413840347`, PAUSED. It stays on Meta (the rollback only covers our rows).
- Deviations: the `ad_account_id` pattern is `act_` + letters/digits/underscore (the fakes use
  `act_fake_1`; Zernio's ownership check rejects anything else). The Page is not sent: Zernio uses
  the ad account's default Page, as the Zernio form does when none is picked. A third field question
  was added for `goal`.
Originally DRAFT (2026-10-09). Requested by the user: "why it goes to meta we have another options for
https://zernio.com/ api … meta will be parralel options it will still remain. so fix it and do not
change anything in the entire software except this change. follow spec driven developmnet".
Design choice by the user (2026-10-09): "Chat publishes on Zernio" (the chat creates the campaign on
Zernio itself after the owner approves the plan card), not "chat fills the Zernio form".

## Context

On 2026-10-09 pilotsonic asked Command Chat for a traffic campaign. The chat's only ad action,
`create_meta_campaign_draft`, built a draft in the direct Meta builder (SPEC-BE-055). The user added
an image there and pressed Publish. The direct builder calls Graph with the company's own Meta app,
which is in development mode, so Meta refused the ad: "Ads creative post was created by an app that
is in development mode. It must be in public to create this ad."

Zernio (SPEC-BE-084) publishes through Zernio's own approved Meta app, and pilotsonic has a Zernio
Facebook ads account connected (3 usable ad accounts). Command Chat has no Zernio action, so it never
uses it.

## Requirements

- **FR1 (new action):** `publish_zernio_campaign`, module `marketing`, risk `spend` (so the existing
  policy applies unchanged: always an explicit owner approval). It creates one campaign → ad set → ad
  on Facebook or Instagram through `zernio_service.create_campaign`, the same call the Zernio form
  uses. Params:
  - `platform`: facebook | instagram (default facebook);
  - `ad_account_id`: a Zernio ad account id (`act_…`) from the planner context;
  - `name`;
  - `goal`: awareness | traffic | engagement | video_views | conversions (the Zernio Meta goals that
    need no extra ids; lead forms, app installs and Page goals stay in the Zernio form);
  - `budget` (> 0) and `budget_type` daily | lifetime (default daily);
  - `duration_days` (1..365) and optional `start_date`; the run starts at the start of that day in the
    company timezone (or now when today/omitted) and ends `duration_days` later;
  - `countries` (1..25 two-letter codes), `age_min`/`age_max` (18..65, defaults 18/65), `genders`
    all | male | female;
  - `destination_url` (https), `primary_text`, `headline`, `call_to_action` (one of Zernio's Meta
    buttons, default LEARN_MORE);
  - `media_id`: an image or video from our media library: the newest `recent_media` item or
    `"$n.media_id"` of a `generate_photo` / `generate_video` step in the same plan;
  - `mode`: active | paused (default paused; active only when the user asks to run/publish/launch).
- **FR2 (executor):** picks the company's Zernio ads account for the platform (`metaads`); builds
  `schemas.zernio.CampaignCreate` (Page = Zernio's default Page for that ad account; Instagram also its
  default Instagram account) with `request_id` = plan id + step index, so a retried step never makes
  a second campaign; calls `zernio_service.create_campaign`. Every Zernio rule and error (ownership,
  unusable ad account, goal/CTA/copy limits, 401/422 from Zernio) surfaces as the step's error text,
  exactly as in the Zernio form. The result: summary ("Campaign "X" created on Facebook through
  Zernio, paused/active"), Zernio campaign id, and the link `/marketing/paid?tab=zernio`.
- **FR3 (planner context):** when `ZERNIO_API_KEY` is set and the company's Zernio profile has a
  connected Meta ads account, the context gets
  `zernio_ads: {"connected": true, "ad_accounts": [{id, name, currency}]}` (the usable ones). Any Zernio
  error while building it gives `{"connected": false}` and a log line, never a failed chat message. With
  no key or no profile, no Zernio call is made.
- **FR4 (planner rule):** when `zernio_ads.connected` is true, a Facebook/Instagram ad campaign is
  `publish_zernio_campaign`; `create_meta_campaign_draft` is used only when the user asks for the
  direct Meta builder ("direct Meta", "Meta builder"). When Zernio isn't connected, the chat behaves
  exactly as today.
- **FR5 (asking, SPEC-BE-085 guard):**
  - `ad_account_id` is kept only when the context has exactly one ad account, or the user named the
    account (its name or id appears in what they typed); otherwise it's removed and the chat asks
    "Which ad account should the ads run on?" (the planner then maps the named account to its id).
  - `media_id` missing asks "Which image or video should the ad use? I can generate one: say what it
    should show."
  - Numbers, countries, URL, dates and genders go through the existing provenance checks; text
    (name, primary text, headline) is free text as before. The scope word list for the new action is
    the ad/campaign words.
- **FR6 (unchanged):** the direct Meta builder, its Publish button, `create_meta_campaign_draft`,
  `publish_meta_campaign`, the Zernio tab and form, and every other chat action stay as they are.
  Existing drafts are not converted.

## Decisions

- **D1:** Facebook and Instagram only: that's the failing case and the Zernio Meta rules are known.
  Other Zernio platforms can be added to the same action later.
- **D2:** No local draft: Zernio campaigns live only on Zernio (SPEC-BE-084), so the approval card
  is the review step, and `mode` defaults to paused.
- **D3:** The Zernio lookup for the context costs two Zernio calls per chat message while Zernio is
  connected (accounts, then ad accounts). Acceptable for a chat message; no cache.

## Target files

- `backend/app/ai/command_actions.py`: params model, executor, registry entry, two field questions.
- `backend/app/services/orchestrator_service.py`: `zernio_ads` in `_context`, the FR4 prompt line,
  `ad_account_id`/`media_id` in the planner's `ask` keys.
- `backend/app/ai/command_guard.py`: the FR5 `ad_account_id` rule and the scope words.
- `CLAUDE.md`: one line.

No frontend change (the plan card already renders any action; `marketing` is a known module), no
DDL, no new files.

## Acceptance criteria

Verified on the live DB in rolled-back transactions, Zernio answered by `dev_fakes`, the planner
by `LLM_PROVIDER=fixture` answers:
1. With a Zernio Meta ads account connected, a Facebook campaign request with every field plans
   `publish_zernio_campaign` with risk spend and approval mode owner.
2. After the owner approves, the step calls Zernio once with the mapped body (goal, budget in whole
   units, dates in the company timezone, countries/age/gender, copy, CTA, link, media URL, PAUSED by
   default), succeeds, and returns the Zernio campaign id and link; a retry sends the same
   idempotency key.
3. With 3 ad accounts and none named, the chat asks which ad account; with one named it proceeds
   with that id; an id not in the context is removed.
4. A Zernio error (e.g. 422) fails the step with Zernio's message; nothing is written locally.
5. Without `ZERNIO_API_KEY`, or with no Zernio ads account, the context has no Zernio accounts and a
   campaign request still plans `create_meta_campaign_draft` (unchanged behaviour).
6. `ruff check app` / `mypy app` stay at their baselines; the SPEC-BE-085 stub suite still passes
   31/31.
