# SPEC-FE-030: Campaign Wizard — All 6 Steps (Objective → Launch)

Status: IMPLEMENTED (2026-09-30), plan approved by the user; verified E2E in headless Edge against the running backend + live Postgres as the dev-shop owner (test campaign, audience, creative and audit rows removed afterwards). Depends on SPEC-BE-044, 045 and 047. Amends SPEC-FE-016, whose "only step 3; Back/Continue inert" rule no longer applies.

Implementation notes: Step 4 autosaves (600 ms debounce) once budget, start and end are filled in, so the "≈ ৳X/day" line and the approval note always show the backend's own numbers. The manager "Sent for owner approval" path was verified at the API level (SPEC-BE-047), since dev-shop has only an owner login; the UI renders it from the same response (`status = draft` + `pending_approval_id`).

## Purpose
Turn `/campaigns` into a working 6-step Campaign Wizard: **1 Objective → 2 Audience → 3 Creative → 4 Budget & Schedule → 5 Channels → 6 Review & Launch**. The mockup's header ("Campaign Wizard", "Step N of 6 — {step}"), 6-segment progress bar, card and "← Back" / "Continue to {next} →" buttons are kept, now driven by real state. Step 3 keeps the mockup's creative card (SPEC-FE-031).

## Functional rules
1. **Start or resume:** the page first shows "Your drafts" (`GET /campaigns/drafts`), each with its name, objective, first missing step and a "Continue" button, plus "+ New campaign". Opening a draft jumps to its first missing step. The draft id is kept in the URL (`/campaigns?draft=<id>`), so a reload resumes the same draft.
2. **Progress bar:** N of 6 segments filled for the current step. The subtitle reads "Step N of 6 — {Objective | Audience | Creative | Budget & Schedule | Channels | Review & Launch}".
3. **Continue saves the step** with `PATCH /campaigns/{id}`, or `POST /campaigns` on step 1. Backend 422/409 messages show inline and the user stays on the step. "← Back" never discards saved data. On step 1, Back returns to the drafts list.
4. **Step 1 Objective:** campaign name, objective (the 6 live values with plain labels, e.g. "Conversions — get purchases"), and an optional description.
5. **Step 2 Audience:** pick a saved audience (`GET /audiences`), or "+ New audience" with an inline form: name, countries (default BD), regions, age range, gender (All/Male/Female), interests and languages (comma-separated). Estimated size shows "—", because there is no platform data to estimate from.
6. **Step 4 Budget & Schedule:** total budget (tenant currency, ৳), start and end date-time. It shows the backend-computed "≈ ৳X/day over N days". When the backend's `approval.required` is true, a warn note says "Launch needs owner approval: daily spend ৳X exceeds your ৳Y/day cap."
7. **Step 5 Channels:** checkboxes for the live channel values. Facebook and Instagram are pre-checked on a fresh draft. At least one is required.
8. **Step 6 Review & Launch:** a summary of every step, each with "Edit" jumping to that step. There's a "Launch campaign" button (disabled while `missing` isn't empty) and a note: *"This records the campaign as live in AI Orchestrator. Publishing to Facebook/Instagram/TikTok ad accounts isn't connected yet."*
   - Result: live → "Campaign launched", with a link to Marketing.
   - Pending → "Sent for owner approval". The item appears in Command Chat's Approvals panel.
9. **Roles:** there's no client-side role, so the backend's 403 shows "Only managers and above can create or launch campaigns."

## Acceptance criteria (verified E2E: backend + next dev + live Postgres)
1. A full pass creates a draft and saves each step (DB checked after each Continue). Reload resumes it.
2. Launching as owner → the campaign is `running`/`scheduled` with an ad group and ad in the DB, and it appears in Marketing › Active Campaigns.
3. The over-cap warning matches the backend rule. Back/Continue/Edit navigation keeps data.
4. Test campaigns, audiences, creatives and audit rows are removed afterwards.

## Target files
- app/(app)/campaigns/page.tsx
- components/campaigns/wizard.tsx (new: stepper, drafts list, steps 1, 2, 4, 5, 6)
- lib/api/campaigns.ts (new)
- lib/types/campaigns.ts (new)

## Amendment A (2026-10-01): explain a disabled Continue
Status: IMPLEMENTED (2026-10-01), approved by the user. Verified E2E in headless Edge on dev-shop on a throwaway draft, audience and creative, plus their 6 audit rows, all deleted afterwards; the user's draft was untouched. 11/11 checks passed: the form auto-opens, the hint shows while Continue is disabled, Save selects the new audience, Continue reaches Creative, and the Budget and Channels hints appear. No console errors.

**Problem (confirmed 2026-10-01, no code changed):** on draft `7b8e2686…` (dev-shop), Step 2's "Continue to Creative →" does nothing. The tenant has **0 saved audiences**, so none can be selected, and Continue is disabled until one is, by design. The page gives no reason. The backend works: in a rolled-back transaction, `POST /audiences` with the form's defaults returned 201, and `PATCH /campaigns/{id}` with that `audience_id` returned 200. Budget & Schedule and Channels have the same silent disabled button.

**Rules:**
1. Step 2: when the tenant has no saved audiences, the "+ New audience" form opens automatically. After "Save audience", the new audience is selected (existing behavior), so Continue enables.
2. Whenever Continue is disabled, a muted line next to it says why:
   - Audience: "Select an audience to continue" (or "Save the new audience to continue" while the form is open).
   - Budget & Schedule: "Enter a total budget and both dates to continue".
   - Channels: "Pick at least one channel to continue".
3. Nothing else changes: the same backend calls and the same validation.

**Target file:** components/campaigns/wizard.tsx (`StepNav` gets an optional `hint`; `StepAudience`, `StepBudget` and `StepChannels` pass one).

**Verification:** E2E in headless Edge on dev-shop. Use a throwaway draft and audience, removed afterwards, not the user's draft. Check that the form opens with no audiences, Save selects the new audience, Continue reaches Creative, and each hint appears while its Continue is disabled.

## Amendment B (2026-10-01): make a disabled button look disabled
Status: IMPLEMENTED (2026-10-01), approved by the user. Verified in headless Edge on the user's draft, read-only:
- Disabled Continue and Save audience: opacity 0.5, cursor `not-allowed`.
- Enabled Back and Cancel: unchanged (opacity 1, pointer).
- No other component styled disabled `.btn` itself; the login page's `.neu-btn` is a separate class.

**Problem (confirmed while testing Amendment A):** `app/globals.css` has no `:disabled` rule for `.btn`. A disabled Continue renders exactly like an enabled one (solid accent, pointer cursor), so it looks broken when clicked. This affects every disabled `.btn` in the app, not just the wizard.

**Rule:** add `.btn:disabled { opacity: .5; cursor: not-allowed; }` next to the ported `.btn` rules.

**Target file:** frontend/app/globals.css.

## Amendment C (2026-10-01): issues found in a full check of the wizard
Status: IMPLEMENTED (2026-10-01), approved by the user (issues 1–4; issue 5 stays a note). Verified E2E in headless Edge on a throwaway tenant, deleted afterwards. 8/8 checks passed, no console errors:
- The new audience is attached at once and is still selected after Back.
- The Creative hint shows, then hides once a variant is selected.
- "✓ Selected": opacity 1, default cursor. "Select" is unchanged.
- "8 calendar days" appears on steps 4 and 6.

**How it was checked:** a full E2E run in headless Edge against the running backend and live Postgres, on a throwaway sign-up tenant (owner, manager and operator users, one product, ad cap 50 USD/day), deleted afterwards (39 rows). The user's draft `7b8e2686…` was only opened read-only.

**Works (35 checks, every failure traced to a wrong test expectation, not the app):**
- Drafts list: empty state, Continue, and the "Awaiting owner approval" badge.
- Step 1: the required name blocks submit; values persist after Back.
- Step 2: the form auto-opens, the audience is saved with the right summary and auto-selected.
- Step 3:
  - "Generate with AI" lists products and is disabled until a product and brief are given. With `LLM_PROVIDER=mock`, it shows the setup notice and switches to "Write your own".
  - Write: variant 1 is pre-selected. Edit variant and Select variant both work.
- Step 4: the backend's daily estimate and the over-cap approval note appear.
- Step 5: Facebook and Instagram are pre-checked; adding TikTok works.
- Step 6:
  - Every choice is shown; Edit returns to its step; a reload resumes at step 6.
  - An owner's launch over the cap launches it (status `scheduled`, since the start is in the future; 1 ad group and 1 ad created).
  - A manager's launch over the cap → "Sent for owner approval", and Launch is then disabled. The owner's approval → `scheduled`.
- An operator sees "Only managers and above can create or launch campaigns."
- No console errors. The only non-2xx responses were the expected 503 (no LLM) and 403 (operator).

**Issues → proposed rule:**
1. **"✓ Selected" looks faded** (side effect of Amendment B: the selected variant's button is disabled, so it is dimmed). Rule: a selected-variant button keeps full opacity. Add `aria-pressed="true"` to it, plus `.btn[aria-pressed="true"]:disabled { opacity: 1; cursor: default; }`.
2. **The Creative step's disabled Continue has no reason** (missed by Amendment A). Hint: "Add variants to continue" before any exist, and "Select a variant to continue" when none is selected.
3. **Back on step 2 drops a just-saved audience:** the choice is only stored on Continue, so after Back → Continue nothing is selected. Rule: saving a new audience also attaches it to the draft (`PATCH audience_id`) right away.
4. **"(8 days)" for Oct 2 10:00 → Oct 9 10:00:** the backend counts calendar days in the tenant timezone, inclusive (SPEC-BE-044, by design), so the label looks off by one. Rule: show "8 calendar days" on step 4 and step 6.
5. **Not fixed (note only):** the creative is tagged with the draft's first channel or "instagram", because channels are chosen at step 5, after the creative. There is no effect today, since nothing publishes. Revisit when publishing exists.

**Target files:** components/campaigns/wizard.tsx, components/campaigns/creative-variants.tsx, app/globals.css.

## Amendment D (2026-10-01): a start time that slips into the past blocks Continue
Status: PROPOSED, awaiting approval. No code changed yet.

**Problem (confirmed 2026-10-01, no code changed):**
- On draft `425b0afb…` (dev-shop), "Continue to Channels" does nothing. Its audit trail has no successful budget save at all, not even the autosave.
- Reproduced in headless Edge on a throwaway tenant set up like dev-shop (BDT, Asia/Dhaka, cap 50/day), deleted afterwards. The user's draft was not touched.
- Results by start time:
  - Now: works.
  - 3 minutes ago: 422 "The start can't be in the past."
  - Today 00:00: 422, same message.
  - End before start: 422 "The end must be after the start."
  - Tomorrow: works.
- The backend rule (SPEC-BE-044: a start more than 1 minute in the past is rejected) is correct. The UI is the problem:
  - A start of "now" turns into a past time while the user fills in the other fields.
  - The picker allows past times.
  - The error is a small line above the buttons, while Continue stays enabled and fails again on every click.

**Rules (frontend only, no backend change):**
1. **"Start as soon as it's launched" checkbox:** ticked by default on a draft with no saved start. While ticked, the Start field is hidden, and every save sends `starts_at` = the moment of that save, so it can't be in the past. Unticking shows the Start field.
2. **Picker limits:** Start has `min` = now (rounded up to the next minute), and End has `min` = Start (or now). The picker greys out past times.
3. **Errors:**
   - When the backend rejects the schedule (422), its message appears in red under the field it concerns.
   - Continue is disabled, with that message as the hint (Amendment A style), until the inputs change.
4. Nothing else changes: the same PATCH body, and the daily estimate and approval note as today.

**Target file:** components/campaigns/wizard.tsx (`StepBudget`).

**Verification:** E2E in headless Edge on a throwaway tenant (deleted afterwards):
- With the box ticked, waiting more than 1 minute and then pressing Continue reaches Channels.
- Unticked with a past time: the picker blocks it, and a forced past value shows the red message under Start with Continue disabled.
- An end before the start: the message under End.
- A future start still works, with the estimate and cap note shown.
