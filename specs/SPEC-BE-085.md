# SPEC-BE-085: AI agents do exactly what the user asked (Command Chat + Create with AI)

Status: IMPLEMENTED and verified on the live Postgres in rolled-back transactions (2026-10-09).
- **Golden set:** stub mode passes 31 of 31 cases, and no temporary company is left behind.
- **Other checks:** 18 of 18 pass (FR6/AC7 with `httpx.MockTransport`; AC6, FR1, FR2, FR7, FR9 and
  AC9 on the live DB or as pure functions).
- **Lint and types:** `ruff check app` is at its baseline (1 error) and `mypy app` at its
  baseline (7 errors in 5 files). The new files add none.
- **Not measured:** live mode against a real AI model (it spends a company's AI credits;
  run `python evals/run_command_eval.py --live --ai-from <slug>`). See "Implementation notes".

Requested by the user: "user will give prompt and then AI will do exactly that work no any other
things … I need accurate agents". Approved by the user without a separate plan review ("write
spec and execute no need permission … do not change anything in the entire software except
these").

## Context

Command Chat (SPEC-BE-059/078) turns one message into a plan with one LLM call. The plan is
validated in code for its *shape* only (strict Pydantic params, role, known action types). The
prompt asks the model not to invent values or add steps, but nothing in code checks it. Create
with AI (SPEC-BE-069/070) checks platforms, objectives, formats, budget split, forbidden words
and "% off" claims in code, but not the targeting the user typed, nor prices other than "% off".

Gaps found on 2026-10-09 (all in code read that day):
1. A value the user never gave (budget, price, threshold, countries, URL, date, time …) passes
   when the model fills it in.
2. A step the user never asked for (publish, enable, schedule …) passes when the model adds it.
3. The planner sees only the first 60 products / 30 campaigns / 30 workflows.
4. No temperature is set for planning (provider default randomness).
5. `today` in the planner context is the server's date, not the company's.
6. A malformed plan is not retried.
7. Create with AI doesn't check stated ages / gender / countries, or price and free-shipping
   claims in the copy.
8. There is no way to measure accuracy.

## Functional requirements

### Command Chat (`services/orchestrator_service.py`, `ai/command_actions.py`, new `ai/command_guard.py`)

**FR1 Evidence.** The "evidence" of a plan is the text the user typed: the current message, plus
the user messages of the open clarification chain when the model says the message continues it
(`new_request: false`). It is stored as `parsed_intent.evidence` on clarification replies.
AI-written text and context data are never evidence.

**FR2 Value provenance (before validation).** For each step, these top-level params are checked
when the model supplied them (never defaults, never `$n.field` references):

| Kind | Params | Accepted when |
|---|---|---|
| Number | `budget`, `value`, `threshold`, `rate`, `free_over`, `new_on_hand`, `count`, `duration_days`, `duration_s`, `age_min`, `age_max`, `sla_days_min`, `sla_days_max` | the number appears in the evidence (digits, Bengali digits, `1,500`, `1.5k`, `2 lakh`, number words one–twenty/thirty/forty/fifty/hundred). `duration_days` also accepts weeks ×7, a fortnight = 14, a month = 28–31 (N months = 30·N). `rate = 0` is accepted when the evidence says "free". `new_on_hand` also accepts the SKU's current stock ± a number in the evidence. `count = 1` is always accepted. |
| Countries | `countries`, `country_codes` | every code is written in capitals in the evidence, or its English country name (CLDR, `utils/locale_data`) or a listed alias (USA, UK, UAE, বাংলাদেশ …) appears |
| URL | `destination_url`, `landing_url`, `url`, `link_url` | the same URL (scheme, `www.` and trailing `/` ignored) appears in the evidence |
| Date | `start_date`, `end_date`, `date` | an ISO / numeric / month-name date, today / tomorrow / day after tomorrow, a weekday, "in N days", or "next N days" (= tomorrow) in the evidence resolves to it, in the company's timezone; `end_date` also accepts a resolved start + (N−1 or N) days for a duration N in the evidence |
| Time | `time_local` | a written time resolves to it (`8 PM`, `20:00`, `8.30pm`, noon, midnight; a bare hour 1–12 = either half of the day; Bengali "৮টা") |
| Gender | `genders` ≠ `all` | a matching word (women / female / ladies …, men / male …) appears |
| Timezone | `timezone` | the zone name or its city appears (`UTC`/`GMT` by those words) |
| Workflow | `trigger_config.threshold` | N or N+1 is in the evidence ("below 10" = threshold 9) |
| Ids | any 36-character id, at any depth of a top-level param | it appears in the planner context sent to the model or in the evidence |
| SKUs | `sku`, `skus`, `product_skus` | every SKU exists for the tenant (case-insensitive; rewritten to the stored spelling) |

A value that fails is removed from the step. A removed **required** param becomes the existing
fixed-template question (`question_for`). A removed **optional** param falls back to its default,
and the reply lists it: "I left out the {field} of “{step}” because you didn't give it."
The stored clarification draft keeps the removed values out, so the next turn can't reuse them.

**FR3 Scope.** Every non-read action type has a list of request words (English, plus a few
Bengali). A step whose words don't appear in the evidence is left out with a new drop reason
`not_requested` ("I left out “{step}” because your message didn't ask for it. Ask for it directly
if you want it."). Read (`inspect_*`, `validate_meta_campaign`, `organic_insights`) steps are not
checked.

**FR4 Dependents.** A step that depends on (or references) a left-out step is left out too:
reason `depends_on_dropped` ("“{step}” needed a step that was left out, so it was left out too.").

**FR5 Context retrieval.** Products, campaigns and workflows the evidence names (SKU, or words of
the title / name) are listed first, then the rest, within the same 60 / 30 / 30 limits.

**FR6 Deterministic planning.** The planner call passes `temperature=0`. `providers.call` and
the `.env` SDK path send it, and when a provider answers HTTP 400 naming `temperature`, the call is
repeated once without it. Other callers are unchanged (no temperature sent).

**FR7 Company date.** The planner context's `today` is the company-local date.

**FR8 One retry.** When the model's answer can't be parsed, or a step is dropped as
`unknown_action_type` / `invalid_action` / `bad_reference`, the planner is called once more with
those problems listed. Token counts of both calls are added.

**FR9 Traceability.** Plan and clarification replies store `dropped` (reasons) and `left_out`
(`[{index, field}]`) in `parsed_intent`, and the plan audit row keeps its `dropped` list.

### Create with AI (`ai/prompts/ad_planner.py`, `services/ai_campaign_service.py`)

**FR10 Stated targeting.** From the brief and the answers to earlier questions:
- an explicit age range ("aged 25-40", "25 to 40 years old") requires every group of a platform
  with demographics to have exactly that `age_min`/`age_max`;
- an explicit gender target ("target women", "women only", "female audience", "women aged …")
  requires `genders` = exactly that one;
- when the brief names countries, no plan location may name a different country.

Violations are `check_plan` errors, so they go through the existing 3-attempt repair loop.

**FR11 Price claims.** In the safety stage, a money amount in the copy (currency symbol or code
next to a number) must equal a featured product's price or compare-at price, or a number in the
brief. Otherwise: an `error` (`price_claim`), or a `warning` when no product is featured. Copy
that promises free shipping / delivery when the brief doesn't mention it gets a `warning`
(`free_shipping_claim`).

### Evaluation (new `backend/evals/`)

**FR12 Golden set.** `backend/evals/command_chat_cases.json`: commands with the expected plan
(action types in order, key param values), the expected questions, and expected left-out steps.
A case may carry a recorded `model_output`. It is a starter set and grows with real user
commands.

**FR13 Runner.** `backend/evals/run_command_eval.py` runs every case through
`send_message_and_plan` on the live Postgres inside one rolled-back transaction (seeded
temporary company, nothing persisted, no step executed). It reports per case pass/fail and the
totals: exact plans, invented values, extra steps, questions asked.
- Default mode: the model is a stub that returns each case's `model_output`, so the code guards
  are tested with no AI cost.
- `--live --ai-from <company slug>`: the real AI models saved for that company answer (this costs
  that company's AI credits). This measures the real accuracy.

## Non-functional

- No DDL, no new dependency, no new setting.
- Nothing outside the files listed below changes. The approval policy, the action registry and
  the Create with AI stages stay as they are.
- A check that fails costs a question or a dropped step, never a wrong action.

## Out of scope (follow-ups)

- RAGAS scoring of AI customer-service replies (`ai/retrieval.py` + `reply_drafter`). It needs
  `ragas` added to `requirements.txt` and an AI judge model, which spends AI credits. A separate
  spec.
- Growing the golden set to 150–300 real commands, and running `--live` on a schedule.
- Checking free-text names, briefs and captions for meaning. They are the model's wording by
  design.

## Target files

- `backend/app/ai/command_guard.py` (new)
- `backend/app/ai/command_actions.py` (drop reasons, dependents)
- `backend/app/services/orchestrator_service.py`
- `backend/app/ai/llm_client.py`, `backend/app/ai/providers.py` (temperature)
- `backend/app/ai/prompts/ad_planner.py`, `backend/app/services/ai_campaign_service.py`
- `backend/evals/command_chat_cases.json`, `backend/evals/run_command_eval.py` (new)

## Acceptance criteria

1. A model output with a budget / countries / URL the user didn't type turns them into
   questions. With the values typed, the plan keeps them.
2. An invented optional value (for example `start_date`, `age_min`) is removed and listed.
3. An unrequested publish / enable / schedule step is left out (`not_requested`), and so are its
   dependents (`depends_on_dropped`). When it is requested, it stays.
4. An unknown id or SKU becomes a question. A SKU written in the wrong case is normalized.
5. "Below 10" → threshold 9 passes. "Tomorrow at 8 PM" → company-local tomorrow `20:00` passes.
6. A product beyond the first 60 that the user names is in the planner context.
7. The planner sends `temperature: 0`, and a 400 naming temperature is retried without it.
8. An unparseable first answer is retried once.
9. Create with AI: a plan breaking a stated age range / gender / country fails `check_plan`
   with a named error; an unsupported price in the copy is an error; free shipping not in the
   brief is a warning.
10. The eval runner passes every case in stub mode, and nothing persists.
11. `ruff check app` and `mypy app` stay at their baselines, and the new files add no errors.

## Implementation notes (2026-10-09)

- **Files:** only the target files above changed. `CLAUDE.md` was not updated (the user asked
  for no other changes).
- **Approach:** the guard (`ai/command_guard.py`) runs on the model's raw actions before
  `validate_actions`. A removed required value therefore reaches the user through the existing
  fixed-template question. `validate_actions` gained an optional `pre_dropped` argument and drops
  dependents of any dropped step.
- **Known limits (by design, see Out of scope):**
  - These are not checked: `name`, `brief`, `caption`, `prompt`, `objective`, `rule_type`,
    `platforms`, and workflow action params other than `trigger_config.threshold`.
  - A city alone ("Dhaka") does not support a country code, so Meta drafts ask for the country.
  - A computed value ("half of 3000") is asked again, since only written numbers count.
  - The request words for each action are English plus a few Bengali words. A request written
    another way gets "I left out … ask for it directly".
  - FR4 drops a step that needs a left-out step, even when it only used that step's output as an
    optional input (e.g. a post using an unrequested photo).
  - Clarification drafts stored before this change have no `evidence`. Their next answer is
    judged on its own words.
- **Eval harness:** `orchestrator_messages.created_at` defaults to `now()`, which is the same
  instant for every row of one transaction. The runner stamps each turn with `clock_timestamp()`
  so "the latest message" works inside its single rolled-back transaction. Seeded campaigns are
  `running`, because the planner context lists only running / scheduled / paused campaigns.

- **Live run on Claude (2026-10-09, `--live --ai-from pilotsonic`, claude-sonnet-5-5):** 13/29
  cases pass. Most failures are cases written for the stub's invented values: Claude doesn't
  invent them, so there is nothing for the guard to drop (e.g. no unrequested publish, schedule or
  enable step; the real "Summer Sale" id from the context instead of a made-up one). Those
  outcomes are correct, but the case expectations only fit the stub. Two real bugs surfaced and
  are fixed:
  - **Wrong question:** the model's own `ask` keys were looked up in the global
    `FIELD_QUESTIONS` table without the action, so a low-stock workflow's `threshold` was asked
    as "At what order amount should shipping become free?" next to the right question.
  - **Duplicate question:** "Create an AI campaign" asked for the link twice (the model's
    `destination_url` plus the missing `landing_url`, which had only the generic template).
  - **Fix:** `orchestrator_service._relevant_ask` keeps an `ask` key only when it is a param of a
    drafted action and no missing field already covers it (all keys count when no action is
    recognised); `FIELD_QUESTIONS` gained `landing_url`. Stub mode still passes 31/31, and both
    cases pass live.
  - **Left as is:** "Turn on free shipping in the Bangladesh zone" became a free rate of 0 (a
    valid reading, no threshold asked); a read question may add a second read step; with 5
    unknown values only 4 questions are asked per turn, by design.
