# SPEC-BE-100: Command Chat — every step's outcome, readable errors and how to fix them

Status: IMPLEMENTED and verified (2026-10-10). Approved by the user: "write spec for fix and execute, and also i need
to show status of each step completion if have any error must i have to know and how can i fix it". The UI is
SPEC-FE-067.
- **Verified:** 18/18 rolled-back checks on the live DB (AC1–AC5). Regressions: command eval 31/31, BE-097 43/43,
  BE-098 27/27, BE-099 38/38, BE-096 29/30 (the known encrypted-ZIP test artifact). ruff/mypy at the baseline (1 / 7).
- **Deviations:**
  - `fix_for(action, error, invalid)`: a step whose own values failed validation always gets the "correct this value"
    fix, unless the products rule matches. For a `change`/`spend` step that can't be edited, the fix says to remove the
    job and ask for it again in the chat, since Retry can't help.
  - Planner prompt: "price only from the user" now reads "…from the user, which includes the chat project's files".
    That is a SPEC-BE-099 follow-up: the real model sometimes left out a price that was in the project's file.
  - The user's running list (pilotsonic1) was not changed. Its queued "Create campaign with AI" jobs still have
    products visuals without SKUs: they fail with the readable error and fix unless edited first (FR5 allows it).

## Context

A real job list (pilotsonic1, 20 jobs, one item a day, 2026-10-10 → 10-14) ran, but:

- **Job #4 "Create campaign with AI" failed with "Unexpected error (ValidationError)."**
  - The planner set `visuals: "products"` with no `skus`. The file is about IT services, so there are no products.
  - `AICampaignParams` accepted that. `AICampaignCreate` refused it only at run time ("Pick at least one product to use
    its images."), and `_run_job` hid the reason behind the exception's class name.
  - The same job is queued for each of the next four days.
- **Job #3 "Publish a post now" failed: "Facebook Page isn't connected."** The text is correct, but nothing says where
  to fix it.
- **The chat only reports some outcomes.** A failed job gets its own chat line, but finished jobs are summed up at most
  every 5 minutes, so the user doesn't see each step complete.
- **A failed step can't be corrected.** After a job list is submitted no job can be edited, and in a normal plan only a
  step waiting for approval can be. Retry runs the same broken values again.

## Requirements

- **FR1 (readable errors):** when a step fails because its values are invalid (a Pydantic `ValidationError`), the step's
  error is the validation message itself, with the field: "Visuals: Pick at least one product to use its images." Never
  "Unexpected error (ValidationError)". Other unexpected crashes keep today's text.
- **FR2 (caught before running):** `create_ai_campaign` with `visuals: "products"` and no `skus` is invalid at check
  time, the same rule `AICampaignCreate` applies.
  - In a chat plan, this asks for the products.
  - In a job list, the job is `needs_input`, with the question "Which products should the ads show (SKUs)? Or say
    'AI images' to generate the visuals."
- **FR3 (how to fix):** every failed step carries `fix: {text, href, link_label}`. `href` and `link_label` are null when
  no page fixes it. The rules (`command_actions.fix_for(action_type, error)`), first match wins:

  | Error | Fix |
  |---|---|
  | A social Page/account isn't connected (Facebook Page, Instagram, TikTok, LinkedIn: organic) | Connect it in Marketing › Organic › Accounts, then Retry (`/marketing/organic/accounts`) |
  | An ads platform / Meta / Zernio / store (Shopify, WooCommerce) isn't connected or needs reconnecting | Connect it in Integrations, then Retry (`/integrations`) |
  | No AI model / key, AI unavailable, all providers failed | Add or fix a model in Integrations › AI Models, then Retry (`/integrations`) |
  | Rate limit / quota / 429 | The provider is busy or out of quota: wait a few minutes and Retry, or add another AI model |
  | Products needed for images (FR2) | Edit the job: add product SKUs, or set Visuals to "generate" (AI images), then Retry |
  | Role / permission / "only the owner" | Ask the owner or a manager to run it |
  | Not found | What it uses was deleted or renamed: edit the job to pick another, then Retry |
  | A value is invalid (validation, "must", "isn't valid") | Edit the job to correct it, then Retry |
  | Timeout / unavailable / 5xx | The service didn't answer: Retry in a few minutes |
  | Anything else | Retry; if it fails again, edit the job or remove it |

  "Edit" appears in a fix only where FR5 allows editing. Otherwise the step falls through to the "Retry" wording.
- **FR4 (each step's outcome in the chat):**
  - **Job lists of up to 50 jobs:** a compact chat line for every finished job (kind `progress`, not spoken):
    - "✓ Job #1 Generate a photo for X: done (1 of 20)."
    - "✗ Job #3 … failed: <error>. How to fix: <fix text> (2 of 20)."
    - "– Job #5 … skipped: <reason>."
  - **Bigger lists:** they keep the line for each failure and the 5-minute summary line, so the chat isn't flooded.
  - **Normal plans:** the plan card already shows each step live. The final summary's results carry `fix` for failed
    steps.
- **FR5 (fix and retry):** `PATCH /orchestrator/plans/{id}/actions/{index}` also accepts:
  - a **failed** step of risk `read` or `draft` (any plan);
  - a **queued** (`approved`, not started) step of risk `read` or `draft` in a submitted job list. Its `run_at` can be
    changed too.

  Values are checked exactly as today, and a failed step stays failed until Retry. `change` and `spend` steps are not
  editable after their approval, because the approval covered those values: their fix is outside the plan (connect,
  permissions) and then Retry.
- **FR6 (unchanged):** the planner, guards, approval policy, job list drafting, voice, files, chats and projects, and
  every other route.

## Acceptance criteria (live DB, rolled back)

- **AC1:** a step whose values fail at run time records the validation text, not "Unexpected error (ValidationError)".
- **AC2:** `create_ai_campaign` with visuals products and no SKUs is a clarification in chat, and `needs_input` in a job
  list.
- **AC3:** failed steps carry `fix`. Facebook not connected → `/marketing/organic/accounts`; no AI key → `/integrations`;
  products need SKUs → the edit wording. The summary's results carry it too.
- **AC4:**
  - A finished job of a ≤ 50-job list posts its own line, with the count.
  - A failure line includes "How to fix".
  - A 51-job list keeps the 5-minute summary line.
- **AC5:**
  - Editing a failed draft step and then retrying runs it with the new values.
  - A queued draft job in a submitted list can be edited.
  - A failed `change` step's edit is 409, and a running step's edit is 409.
- **AC6:** the command eval is 31/31; ruff and mypy are at the baseline.

## Target files

`ai/command_actions.py` (the FR2 validator, the visuals question, `fix_for`, `validation_text`),
`services/orchestrator_service.py` (`_run_job` error text and `fix`, `edit_action` rules, the summary `fix`),
`services/job_board_service.py` (`after_job` lines), `schemas/orchestrator.py` (`PlanAction.fix`, `ResultItem.fix`).
No DDL. No new files.
