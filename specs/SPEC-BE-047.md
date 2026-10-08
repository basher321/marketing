# SPEC-BE-047: Campaign Wizard — Launch (with owner approval), Pause, Resume

Status: IMPLEMENTED (2026-09-30), plan approved by the user; verified on live Postgres (rolled-back txn).

Implementation notes:
- Only an **owner** can approve a `campaign` approval item (403 "Only the owner can approve a campaign launch." otherwise), because that approval *is* the owner sign-off. Any manager+ can still reject. Other subject types are unchanged.
- The approval_queue row is inserted through a SQLAlchemy Core table, because the ApprovalQueue model (not a target file) does not map the NOT NULL `requested_by_type` or `summary`/`payload`/`requested_by`.
- Group approve/reject (`/approvals/groups/{subject_id}/…`) runs the same campaign hook.

## Purpose
Finish the flow: the wizard's **Review & Launch** step turns a complete draft into a live campaign with its ad set and ad, respecting the spend guardrail the platform already uses for AI plans (SPEC-BE-032: owner approval when daily spend exceeds `tenants.ad_daily_cap_cents`). It also adds pause and resume, the standard lifecycle controls.

**Honest limit:** the third-party ad adapters are stubs (CLAUDE.md), so launching records the campaign as live in this system only. **Nothing is published to Facebook, Instagram or TikTok.** `ads.external_ad_id` stays NULL until an integration spec exists. The UI must say so.

## Scope
In scope:
- Realign `AdGroup`/`Ad` with the live tables.
- Launch, which submits for approval when needed.
- Launch when the approval is approved.
- Pause and resume.

Not in scope: publishing to ad platforms, spend tracking (`spent_cents` stays 0), automatic completion when `ends_at` passes, and editing a live campaign.

## Contract
`POST /api/v1/campaigns/{id}/launch` (manager+) → 200 `CampaignDetail` (SPEC-BE-044)
- The draft must have an empty `missing` list, otherwise 422 naming the missing steps. A non-draft returns 409.
- **Approval rule:** the same as SPEC-BE-032's `_spend_decision`. Approval is needed when `daily_cap_cents > tenants.ad_daily_cap_cents` or the currency differs from the tenant's.
  - If **the actor is the owner**, the launch counts as the owner's approval: it goes live and `owner_approved_at`/`owner_approved_by` are set.
  - If approval is needed and the actor is **not** the owner, an `approval_queue` row is created (`subject_type = campaign`, `subject_id = campaign.id`, a title and summary with budget, daily spend, cap and channels, `requested_by_type = human`). The campaign stays `draft` with `pending_approval_id` set. A second launch while one is pending returns 409.
  - Otherwise it goes live directly.
- **Going live:**
  - One `ad_groups` row is created: name "{campaign} — Ad set", `audience_id`, targeting copied from the audience, the budget, status.
  - One `ads` row is created: `content_asset_id`, a name, status, and `metadata` holding the selected variant's text.
  - The campaign gets `channels`, a status of `scheduled` when `starts_at > now` or `running` otherwise, and `launched_at = now`.
  - The creative's `content_assets.status` becomes `approved`, with `owner_approved_*` set when approved by the owner.
- Audit row: `campaign.launch` or `campaign.submit_for_approval`.

**Approving in the existing Approvals UI:** `approval_service.decide_one`/`decide_group`, when approving an item with `subject_type = campaign` whose campaign is still `draft`, run the same "going live" step, with `owner_approved_by` set to the decider. A rejection leaves the campaign `draft` and clears its pending state. Other subject types are unchanged.

`POST /api/v1/campaigns/{id}/pause` (manager+): `running`/`scheduled` → `paused` (`paused_at`), and its ad groups and ads are paused too. Any other status returns 409.
`POST /api/v1/campaigns/{id}/resume` (manager+): `paused` → `running`, or `scheduled` if it hasn't started yet. If `ends_at` has already passed, it returns 409 ("campaign has ended").
Both write an audit row. Another tenant's campaign returns 404.

## Functional rules
1. Launching happens in one transaction: the ad group, ad, campaign update, creative update and audit row are committed together.
2. The approval check reuses the SPEC-BE-032 rule's logic and the tenant limits from `ai/retrieval.get_tenant_limits`, never a new threshold.
3. After launch, the campaign appears in the Marketing page's "Active Campaigns" (`GET /campaigns`, SPEC-BE-038) with no change to that endpoint.

## Acceptance criteria
1. An owner launching a complete draft → `running` (or `scheduled`), with 1 ad group, 1 ad and an audit row, and the campaign listed on the Marketing page.
2. A manager launching over the cap → a pending approval_queue item and the campaign still `draft`. Approving it launches the campaign. Rejecting it leaves the draft editable.
3. A manager within the cap → launches directly.
4. An incomplete draft → 422, and nothing is written.
5. Pause and resume transitions and their 409s work. Another tenant gets 404. Viewer gets 403.

## Target files
- backend/app/models/campaign.py (AdGroup, Ad realigned: tenant_id, audience_id, targeting, budget_cents, status, content_asset_id, metadata)
- backend/app/services/campaign_service.py
- backend/app/api/v1/campaigns.py
- backend/app/services/approval_service.py (campaign approve/reject hook)
