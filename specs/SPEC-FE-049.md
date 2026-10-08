# SPEC-FE-049: Marketing navigation — Paid Marketing and Organic Marketing

Status: IMPLEMENTED (code, 2026-10-03; approved by the user). `npx tsc --noEmit` and `next build` are clean. **E2E acceptance (criteria 1, 2, 4, 5) is pending:** the live Postgres DB was unreachable, so the running app couldn't be exercised. See "Implementation notes". Part of the Marketing restructure (SPEC-FE-049/050, SPEC-BE-074…078).

## Purpose
"Campaigns" stops being its own top-level item. Marketing gets two areas:

```
Marketing
├── Paid Marketing     (everything that is /campaigns today)
└── Organic Marketing  (new, SPEC-FE-050)
```

## Findings
| # | Finding |
|---|---|
| F1 | `components/shell/sidebar.tsx` lists "Campaigns" (`/campaigns`) under Configuration and "Marketing" (`/marketing`) under Engines. The sidebar has no nested items. |
| F2 | Six pages live under `app/(app)/campaigns/`: the list, `ad-manager`, `new`, `[id]/edit`, `ai/new`, `ai/[runId]`. About 30 hard-coded `/campaigns…` links point at them, in those pages, `components/campaigns/wizard.tsx` and `components/marketing/campaigns-table.tsx`. |
| F3 | The Meta builder already has the Ads Manager hierarchy and fields (see the audit below). It has Validate and Preview in a sticky footer, but no **Review** step that shows the whole campaign before publishing. |
| F4 | Backend-generated links (notifications, Command Chat replies, approval items) may contain `/campaigns/…` paths. These are checked at plan time with a grep of `backend/app`. |

## Changes
1. **Sidebar:**
   - Remove "Campaigns" from Configuration.
   - "Marketing" becomes a group with two children, indented under it: **Paid Marketing** (`/marketing/paid`) and **Organic Marketing** (`/marketing/organic`).
   - The group expands automatically when the current route is under `/marketing`, and the user can also toggle it. The open/closed state is kept in `localStorage`, wrapped in try/catch.
   - Active-state rules are unchanged (prefix match).
2. **`/marketing`** stays the overview: summary cards, Active Campaigns table and Content Calendar. Two cards are added at the top linking to Paid and Organic.
3. **Route move:** `app/(app)/campaigns/**` moves to `app/(app)/marketing/paid/**` with the same sub-paths. Every internal link is updated.
   - `next.config` gets permanent `redirects()` from `/campaigns` and `/campaigns/:path*` to `/marketing/paid` and `/marketing/paid/:path*`, so bookmarks and older backend links keep working.
   - Any backend link found under F4 is updated to the new path (a separate BE edit, listed in the plan).
4. **Paid Marketing page title:** "Paid Marketing". The subtitle reads "Campaign → Ad set → Ad, published to the connected ad platforms." The tabs stay the same (Campaigns, AI runs).
5. **Ads Manager-style stepper** on `/marketing/paid/[id]/edit` (Meta) and on the multi-platform builder:
   - The steps are **Campaign → Ad set → Ad → Review**. The left-hand tree stays; the stepper sits above the form and shows which level is being edited.
   - **Review** is a new read-only step. It summarizes every level with the fields listed below, shows the validation results (`POST …/validate`) and the existing preview panel, and has these actions:
     - **Save draft** (autosave already exists; the button confirms it);
     - **Schedule** (enabled when the ad set start time is in the future);
     - **Publish now**;
     - **Publish paused**.
   - **Pause/Resume** stay on the list rows and on the tree nodes.
   - Nothing is simulated: every action calls the existing backend endpoint. A failed call shows the backend's error, and no state is set on the client.
6. **Objectives** are shown only where the selected platform supports them, using the existing platform registry (`GET /ads/platforms` for the other six; Meta's six objectives for Meta). This is already true, so it gets a check only.
7. Rename the label "Optimization goal" to **"Performance goal"**, Meta's current term. The field and API stay the same.

## Field audit (Ads Manager hierarchy vs. what exists)
"✓" means already in the Meta builder. Each row is checked during verification; a row that turns out missing is reported, not silently added.

| Level | Field | State |
|---|---|---|
| Campaign | name, objective (Awareness, Traffic, Engagement, Leads, App promotion, Sales) | ✓ |
| Campaign | buying settings: buying type (AUCTION only), bid strategy, CBO budget | ✓ |
| Campaign | special ad category + countries | ✓ |
| Ad set | budget, schedule (start/end), audience, location, placements, performance goal, conversion location, pixel | ✓ |
| Ad | identity (Page / Instagram account), creative (image/video), primary text, headline, CTA, destination, tracking (URL parameters, pixel) | ✓ |
| Flow | Review step | **new** (change 5) |

## Acceptance (E2E against the running backend + live DB, dev fakes for the ad platforms)
1. The sidebar has no "Campaigns" item. Marketing expands to Paid Marketing and Organic Marketing; both routes render and highlight correctly.
2. `/campaigns`, `/campaigns/ad-manager`, `/campaigns/<id>/edit` and `/campaigns/ai/<runId>` redirect (308) to the `/marketing/paid/…` equivalents.
3. `grep -r '"/campaigns' frontend/app frontend/components` finds no links left (only the redirect config).
4. Meta builder: Campaign → Ad set → Ad → Review. Review shows all levels and the validation results. Publish now, Publish paused and Schedule call the backend (with `META_FAKE_TRANSPORT`), and the list shows the resulting status. Pause/Resume work from the list.
5. Multi-platform builder (e.g. TikTok via dev fakes): same stepper and Review step, and only the platform's supported objectives are offered.
6. `npx tsc --noEmit` is clean.

## Target files
- `frontend/components/shell/sidebar.tsx`
- `frontend/app/(app)/campaigns/**` → `frontend/app/(app)/marketing/paid/**` (moved, links updated)
- `frontend/app/(app)/marketing/page.tsx` (two entry cards)
- `frontend/next.config.*` (redirects)
- `frontend/components/campaigns/**` (link paths, stepper, new `review-step.tsx`)
- `frontend/components/marketing/campaigns-table.tsx` (link paths)
- `frontend/CLAUDE.md` (routes)
- `CLAUDE.md` (Ad Manager flow paths)

## Out of scope
- Any change to the backend campaign APIs.
- Renaming `components/campaigns/` (the folder name stays; only routes move).

## Implementation notes (2026-10-03)
- **Routes:** `app/(app)/campaigns/**` moved to `app/(app)/marketing/paid/**`. 30 route strings were rewritten in those pages, `components/campaigns/wizard.tsx` and `components/marketing/campaigns-table.tsx`. API paths (`/api/v1/campaigns…`) are unchanged. `next.config.mjs` has permanent redirects `/campaigns` → `/marketing/paid` and `/campaigns/:path*` → `/marketing/paid/:path*`.
- **Backend links (F4):** the only backend-generated frontend links were five Command Chat result links in `ai/command_actions.py`. They now point to `/marketing/paid…`.
- **Sidebar:** Marketing is a group. It's open on any `/marketing/*` route, and manually opened groups are remembered in `localStorage` (guarded). "Campaigns" is gone from Configuration.
- **Stepper and Review step:** these are in `components/campaigns/review-step.tsx`, used by both the Meta builder and the multi-platform builder. Review runs the backend validation when it opens (drafts only) and summarizes every level.
  - Publishing stays in the existing sticky footer: Publish now / Schedule (when the ad set start is in the future) / Publish paused. Save draft is the existing autosave. Pause/Resume stay on the nodes and in the list.
  - The multi-platform stepper uses each platform's own level names (e.g. "Ad group").
- **"Performance goal":** the Meta ad set form already used this label, so nothing changed.
- **Pending (needs the DB):** criterion 1 in a browser, criterion 2 (308 redirects on a running server), and criteria 4–5. Criterion 3 passes: no `"/campaigns` route strings are left in `app/` or `components/`. Criterion 6 passes.
