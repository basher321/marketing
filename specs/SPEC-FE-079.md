# SPEC-FE-079: Dashboard stat cards — consistent spacing

Status: IMPLEMENTED (2026-10-22). Verified in headless Chrome against the local backend: every row gap equals
every column gap at 1440 / 1100 / 820 / 390 px and in compact density. Before the fix, 12 of 31 checks failed;
after it, 31 of 31 pass. `tsc` and `next build` are clean.

## Problem (measured 2026-10-22, before the fix)

The dashboard shows ten stat cards in two grids, one after the other:

- `SummaryCards` (`.grid-4`): Revenue (24h), Orders, Ad Spend, Open Conversations.
- `BusinessCards` (`.grid-3 mb-4`): Connected accounts, Scheduled posts, Messages to answer, Waiting for
  confirmation, New orders, Profit (or Loss) this month.

Each grid has its own `gap`, but nothing separates the two grids, so the Revenue row sits directly on the
Connected accounts row. Measured gaps:

| View | Gap between the two grids | Other row gaps | Column gaps |
|---|---|---|---|
| Desktop 1440 / laptop 1100 | **0 px** | 16 | 16 |
| Tablet 820 | **0 px** | 16 | 16 |
| Phone 390 | **0 px** | 10 (`.grid-4`) and 16 (`.grid-3`) | 10 |
| Compact density | **0 px** | 10 | 10 |

`BusinessCards` also carried its own bottom margin (`mb-4`), a per-component margin instead of a parent gap.

## Requirements

1. **One parent grid.** `app/(app)/dashboard/page.tsx` wraps `SummaryCards` and `BusinessCards` in one
   container, `.dash-stats`, a CSS grid whose `gap` separates the two card grids.
2. **One gap value per view, used for both directions.** `.dash-stats` sets `--dash-gap`. The container's own
   gap and the `gap` of its child `.grid-3` / `.grid-4` grids all read it, so the gap between rows, the gap
   between the two groups, and the gap between cards in a row are always the same:
   - 16 px by default (the existing `.grid-*` gap);
   - 10 px in compact density (the existing compact gap);
   - 10 px at ≤ 480 px (the existing phone `.grid-4` gap, now also used by the business cards there).
3. **No per-card or per-grid margins.** Remove `mb-4` from `BusinessCards`. The space before "Automation
   Engines" stays as it was: the heading's own top margin (30 px, or 22 px compact).
4. **Unchanged:** the column counts and breakpoints of `.grid-3` / `.grid-4`, card styles (padding, radius,
   shadow, hover), colours, typography, content, links and every other page using `.grid-3` / `.grid-4`.
   The new rules are scoped to `.dash-stats`.
5. **Alignment:** cards in one row keep one height (the grid's default stretch); nothing overlaps or
   touches, and there is no horizontal scroll at any width.

## Acceptance criteria

- At 1440, 1100, 820 and 390 px, in comfortable and compact density, all ten cards render, and every
  vertical gap between card rows equals every horizontal gap between cards (16 px / 10 px as above).
- No gap is 0; cards in a row have equal heights; no horizontal scroll.
- `npx tsc --noEmit` and `next build` pass.

## Files

`app/(app)/dashboard/page.tsx`, `components/dashboard/business-cards.tsx`, `app/globals.css`.

## Implementation notes

- **Why a variable:** `.grid-4` already drops to a 10 px gap on phones, and compact density sets 10 px on every
  `.grid-*`. A single custom property on `.dash-stats` keeps the dashboard's three gaps in step without
  changing those rules for other pages.
- **Card padding is unchanged:** on phones the Revenue-row cards keep their 14 px padding (an existing
  `.grid-4 > .card` rule), so those cards are a little shorter than the business cards. This is card styling,
  not spacing, so it is out of scope.
