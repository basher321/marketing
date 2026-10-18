# SPEC-BE-102: Command Chat ads through Zernio, and Skip for a job

Status: IMPLEMENTED (2026-10-10; Zernio first, the user's choice). Verified on the live DB with dev fakes (rolled back):
AC1–AC4 pass (eval 32/32 with the new `ai_campaign_not_connected` case). The skip line names only the jobs that
depended on the skipped one. The UI is SPEC-FE-068. It builds on SPEC-BE-101
(companies connect accounts; PilotSonic owns the keys).

## Context

pilotsonic1's job list has a "Create campaign with AI" job each day. That job type, the AI Ad Autopilot (SPEC-BE-069),
only builds in the direct ad builders, which need the company's own Meta Ads connection. The company uses Zernio, so the
job fails every day with "Connect Meta in Integrations first…". Once a list is submitted, the user can't take a single
job out: Cancel stops the whole list.

## Requirements

- **FR1 (ads go through Zernio):**
  - **With a Zernio ads account:** in Command Chat and in job lists, an ad request for a platform the company has
    connected in Zernio becomes `publish_zernio_campaign` (SPEC-BE-090: spend, owner approval, paused unless the user
    says run/launch).
    - The job-list template gets the same rule and the same `zernio_ads` context that the chat planner already has.
    - The ad's image comes from a `generate_photo` step, or from the media library.
  - **Direct builders:** `create_ai_campaign` is planned only for platforms the company connected directly (the
    planner context lists them).
  - **Neither connected:** the reply asks the user to connect their ad account through Zernio, with a link, instead of
    planning a job that can't run.
- **FR2 (fix text):** "Connect … in Integrations first; AI campaigns are built against the real ad account." gets the
  fix "Connect your ad account through Zernio (Paid Marketing › Zernio), then ask the chat again", with the link
  `/marketing/paid/zernio/new`.
- **FR3 (Skip a job):** `POST /orchestrator/plans/{id}/actions/{index}/skip` (manager+) works on a job that is queued
  (`approved`, not started), `pending_approval`, `needs_input` or `failed`, in a submitted job list or a normal plan.
  - The job becomes `skipped` (`skip_reason: "user"`) and its dependents are skipped too.
  - A pending approval is expired.
  - The chat gets "– Job #n … skipped (by you)."
  - The plan finishes, with its summary, when nothing is left to run.
  - Running or finished jobs answer 409. It's audited.
- **FR4 (unchanged):** the approval policy, guards, Zernio's own rules (SPEC-BE-084/090), the direct builders and AI Ad
  Autopilot pages.

## Acceptance criteria (live DB, rolled back, dev fakes)

- **AC1:**
  - With a Zernio Facebook ads account, "make a Facebook awareness ad…" in chat, and an ad job in a job list, plan
    `publish_zernio_campaign`, waiting for the owner.
  - Without Zernio or a direct connection, the reply asks for a Zernio connection and plans no ad job.
- **AC2:** the AI campaign "Connect Meta…" failure carries the Zernio fix and link.
- **AC3:**
  - Skipping a queued job and a failed job works, and their dependents are skipped.
  - Skipping the last remaining job finishes the plan with a summary.
  - Skipping a running or succeeded job is 409.
- **AC4:** the command eval is 31/31; ruff and mypy are at the baseline.

## Target files

`services/orchestrator_service.py` (planner rule + context), `services/job_board_service.py` (template rule + context,
`skip_job`), `ai/command_actions.py` (fix rule), `api/v1/orchestrator.py` (skip route), `schemas/orchestrator.py`
if needed. No DDL.
