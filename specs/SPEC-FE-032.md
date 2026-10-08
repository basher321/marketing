# SPEC-FE-032: Marketing — Pause / Resume Campaigns

Status: IMPLEMENTED (2026-09-30), plan approved by the user; verified E2E (pause/resume on the new campaign and on "Ramadan Sale 2026", restored to running with its audit rows removed). Depends on SPEC-BE-047. Amends SPEC-FE-012 (Active Campaigns table).

Implementation note: rule 3 already existed (the table header has had a "+ New Campaign" link to /campaigns since SPEC-BE-038), and no type change was needed, so only components/marketing/campaigns-table.tsx and lib/api/marketing.ts changed.

## Purpose
Complete the lifecycle where campaigns are managed: the Marketing page's "Active Campaigns" table gets a Pause/Resume action per row, and a "+ New campaign" link to `/campaigns`.

## Functional rules
1. **Row action:** `running`/`scheduled` → "Pause". `paused` → "Resume". It calls the SPEC-BE-047 endpoint, then refetches the campaigns list and the dashboard campaign metrics.
2. Errors show inline (409 "campaign has ended", and 403 → "Only managers and above can pause or resume campaigns.").
3. "+ New campaign" (`.btn .btn-sm`) goes to `/campaigns`.

## Acceptance criteria (verified E2E)
1. Pausing a running dev-shop campaign → the DB status is `paused` and the badge updates. Resume puts it back. The original status is restored afterwards and the audit rows are removed.

## Target files
- components/marketing/campaigns-table.tsx
- lib/api/marketing.ts
- lib/types/marketing.ts
