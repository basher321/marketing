# SPEC-FE-023 Findings — Accessibility Pass

Run date: 2026-09-26. This report was written after a full read-only audit and
**before** any code change (Functional Rule 1). The "Fixes applied" section at
the end was added only after the fixes were made and re-verified.

Decisions A–C from the plan were not answered, so the plan's stated defaults
apply: (A) the skip link is recorded as a failing check with no fix; (B) focus
after navigation is recorded as an ambiguity with no fix; (C) the `<nav>`
landmark gets no label.

## Method

- Frontend: the current production build, served with `next start -p 5173`. The backend isn't needed: data components render their error state, and no scope item depends on data.
- Browser: Microsoft Edge 153, headless (`--remote-debugging-port=9222`, window 1400×900). Driven through the Chrome DevTools Protocol from an inline Node 24 script, using Node's built-in `WebSocket`. **No test or a11y dependency was added**, and no script file was saved.
- Per route, for all 10 routes:
  - **Tab walk:** real `Tab` key events via `Input.dispatchKeyEvent`. After each press, the focused element's role and computed accessible name were read with `Accessibility.getPartialAXTree`.
  - **Landmarks and headings:** read from `Accessibility.getFullAXTree`.
  - **Uncaught exceptions:** collected via `Runtime.exceptionThrown`.
- Activation: `Enter` on a sidebar link (checking the navigation, where focus lands, the route announcer and `document.title`), and `Enter` + `Space` on both topbar buttons.
- Geometry: the bounding boxes of the sidebar container, all 10 nav links and both topbar buttons were recorded as the pre-fix baseline, for the no-visual-regression check.

## Summary

| # | Scope item | Built by | Result |
|---|---|---|---|
| 1 | Topbar icon buttons | SPEC-FE-002 | **FAIL**: the accessible names are the glyphs "◔" and "◈", not "Notifications"/"Settings" (fixable: ARIA) |
| 2 | Sidebar nav | SPEC-FE-002 | `aria-current` **PASS**; tab order **PASS**; nav landmark **FAIL**, exposed as `complementary` (fixable: native swap) |
| 3 | Master-detail row selection | SPEC-FE-013/014/017 | **NOT PRESENT**: no selectable row exists |
| 4 | Status badges in listed tables | SPEC-FE-011/013/020 | **NOT PRESENT**: none of the listed tables renders a badge |
| 5 | Plan card / approvals panel buttons | SPEC-FE-009/010 | **NOT PRESENT**: never built |
| 6 | Brand Settings form | SPEC-FE-015 | **NOT PRESENT**: never built |
| 7 | Radix primitives | SPEC-FE-001/003 | **NOT PRESENT**: no Radix import anywhere |
| 8a | Skip-to-main-content link | SPEC-FE-002 shell | **FAIL, not fixed**: absent; a fix needs new copy and a focus-visible style (Rules 2 and 4, decision A) |
| 8b | Focus on route change | SPEC-FE-002 shell | **AMBIGUOUS, not fixed** (Rule 5, decision B); current behaviour recorded |
| 9 | This report | — | Written before any code change |

## Scope 1 — Topbar icon buttons (`components/shell/topbar.tsx`, SPEC-FE-002)

Current markup (lines 13–26): two native `<button type="button">` elements with `title="Notifications"` / `title="Settings"`, whose only content is the glyph `◔` / `◈`. There's no `aria-label`.

| Check | Result | Evidence |
|---|---|---|
| Keyboard focusable | PASS | Tab stops 12 and 13 on every route |
| Activatable with Enter/Space | PASS (inert by design) | `Enter` + `Space` on each: focus stays on the button, the route doesn't change, 0 exceptions. SPEC-FE-002 FR3 defines them as having no click handler. |
| Accessible name | **FAIL** | The AX tree names them `button:"◔"` and `button:"◈"`. The glyph is the button's text content, which takes precedence over `title` in the accessible-name calculation, so a screen reader announces the symbol, not "Notifications"/"Settings". |

**Minimal fix (ARIA, Rule 3):** the elements are already native buttons, so no swap is needed. Surface each existing `title` as `aria-label` (Rule 2: the text is the mockup's own `title`).
- `topbar.tsx` Notifications button: add `aria-label="Notifications"`
- `topbar.tsx` Settings button: add `aria-label="Settings"`

## Scope 2 — Sidebar nav (`components/shell/sidebar.tsx`, SPEC-FE-002; `app/(app)/layout.tsx`)

| Check | Result | Evidence |
|---|---|---|
| Active route exposed via `aria-current="page"` | PASS | `sidebar.tsx:67`; the Tab walk shows `{current}` on exactly the current route's link on all 10 routes |
| Links keyboard-reachable and activatable | PASS | Native `<a>` (Next.js `<Link>`); tab stops 1–10 on every route; `Enter` on the Workflows link navigated to `/workflows` |
| Tab order matches visual order | PASS | Stops 1–10 follow the sidebar top to bottom (Dashboard → Integrations), then the topbar (search, ◔, ◈), then page content; identical on all 10 routes |
| Proper nav landmark | **FAIL** | The container is `<aside>` (`sidebar.tsx:49`). The AX tree on every route lists landmarks `complementary, main`, with no `navigation` landmark |

**Minimal fix (native swap, Rule 3):** change the container tag from `<aside>` to `<nav>` in `sidebar.tsx`, keeping the identical `className` and children. Tradeoff noted:
- Wrapping only the link sections in a new `<nav>` would add an element inside the `flex flex-col gap-1` column. That's a structural change that could alter spacing.
- The tag swap keeps the DOM shape identical. The brand block ("AI Orchestrator") ends up inside the landmark, which is harmless.
- No `aria-label` is added (decision C): one `nav` landmark needs no name, and adding one would be new text.

## Scope 3 — Master-detail row selection

**NOT PRESENT — nothing to audit or fix:**
- Command Chat (SPEC-FE-008–010): `app/(app)/chat/page.tsx` is the SPEC-FE-002 title-only stub, and `components/chat/` doesn't exist.
- Customer Service table (SPEC-FE-013): `app/(app)/customer/page.tsx` is the stub. The SPEC-FE-014 panel (`components/customer/reply-draft-panel.tsx`) exists but isn't mounted on any page, so it can't be reached with a keyboard.
- Workflows table (SPEC-FE-017): `components/workflows/saved-workflows-table.tsx` renders static rows with no selection. Row selection belongs to SPEC-FE-018, which is unbuilt. Its rows aren't tab stops (the `/workflows` Tab walk has no row stops), which is correct for non-interactive rows.

## Scope 4 — Status badges in the listed tables

**NOT PRESENT:**
- E-Commerce products (SPEC-FE-011) and the Customer Service table (SPEC-FE-013) are unbuilt.
- Analytics Top Products (SPEC-FE-020, `components/analytics/top-products-table.tsx`) renders no badges. Its Trend cell is `▲`/`▼` plus the percentage as real text (lines 30–35), so colour isn't the only signal there either.

Outside Scope 4, recorded for information only:
- Badges do render in the Workflows table (`saved-workflows-table.tsx:25–27`: text "Enabled"/"Paused") and the Integrations grid (`integrations-grid.tsx:64`: text "Connected"/"Reconnect"/"Not Connected").
- In both, the status is real text content, not colour alone.
- They couldn't be read from the AX tree in this run, because both components render their error state without backend data.

## Scope 5 — Plan card / approvals panel buttons

**NOT PRESENT.** SPEC-FE-009's plan card and SPEC-FE-010's panel were never built. Only their data layers exist (`lib/api/orchestrator.ts`, `lib/api/approvals.ts`), and those render no buttons.

## Scope 6 — Brand Settings form

**NOT PRESENT.** `app/(app)/kb/page.tsx` is the SPEC-FE-002 stub (the `/kb` Tab walk has no form controls). SPEC-FE-015 is blocked by backend gaps; see the SPEC-FE-022 findings.

## Scope 7 — Radix primitives

**NOT PRESENT.** `@radix-ui/*` packages are installed (`package.json`), but a search of `app/` and `components/` finds no Radix import, so no Radix behaviour exists to be overridden.

## Scope 8 — Skip link and focus on route change (`app/(app)/layout.tsx`, `app/layout.tsx`)

**8a. Skip-to-main-content link: FAIL, not fixed.**
- There's no skip link. The first Tab stop on every route is the first sidebar link, and there is no `a[href^="#"]` anywhere.
- `<main>` (`layout.tsx:18`) has no `id` to target.
- Why no fix was applied:
  - A skip link needs link text, and the mockup has none. Any text ("Skip to main content") would be invented copy (Rule 2).
  - A usable skip link is visually hidden until focused, which is a new visual state (Rule 4).
  - Decision A was left at its default (record, don't fix).
- Minimal fix, if approved later: a first-child `<a href="#main-content">` in `app/(app)/layout.tsx` with approved text, an `sr-only focus:not-sr-only` style, and `id="main-content"` on the content container.

**8b. Focus on route change: AMBIGUOUS, not fixed (Rule 5).** Observed after `Enter` on the Workflows sidebar link:
- The path became `/workflows`.
- `document.activeElement` stayed on the pressed link (`A ◇ Workflows`); focus doesn't move to the page heading.
- Next.js's route announcer (`next-route-announcer`) announced **"Workflow Builder"**, the new page's `<h1>`. It falls back to the `<h1>` because `document.title` is empty: no page sets metadata.

So screen-reader users do hear the new page's title, but keyboard focus doesn't move. SPEC-FE-023 Scope 8 says focus should move "to the correct heading", but no prior spec (SPEC-FE-002 through SPEC-FE-021) defines that target. Some pages have more than one heading (for example `/analytics`: "Analytics", "Revenue by Day …", "Top Products"). So the correct target, and whether the announcer satisfies the requirement, can't be determined from the code or the specs. Not guessed.

## Observed outside the 9 scope items (reported only — not touched)

Scope Acceptance Criterion 5 forbids touching anything outside the 9 items, so these are recorded, not fixed:
1. **Analytics tabs** (`app/(app)/analytics/page.tsx:24–39`, SPEC-FE-019): `div role="tab"`, each with `tabIndex={0}`, plus Enter/Space handlers.
   - They work by keyboard (Tab stops 14–17).
   - They don't follow the WAI-ARIA tabs pattern: every tab is a Tab stop (no roving tabindex), there's no Left/Right arrow handling, and there's no `aria-controls` or tabpanel.
2. **Topbar search input** (`topbar.tsx:9–12`): its accessible name comes only from its placeholder ("Search products, orders, campaigns..."). There's no `<label>` or `aria-label`.
3. **The "Revenue by Day" heading** (`revenue-chart.tsx:64–71`): the "Explain this ⓘ" button sits inside the `<h2>`, as in the mockup, so the heading's accessible name becomes "Revenue by Day Explain this ⓘ".
4. **Inert buttons** ("+ New Workflow", "Version History", "Explain this ⓘ", the Integrations buttons): all native `<button>`s with visible text names, keyboard-reachable. They're inert by their original specs' design.

## Fixes to apply (listed before applying)

| File | Element | Before | After | Scope / spec it serves |
|---|---|---|---|---|
| `components/shell/topbar.tsx` | Notifications button | `title="Notifications"` | `title="Notifications"` + `aria-label="Notifications"` | Scope 1 (element from SPEC-FE-002) |
| `components/shell/topbar.tsx` | Settings button | `title="Settings"` | `title="Settings"` + `aria-label="Settings"` | Scope 1 (SPEC-FE-002) |
| `components/shell/sidebar.tsx` | sidebar container | `<aside className="…">…</aside>` | `<nav className="…">…</nav>` (same className, same children) | Scope 2 (SPEC-FE-002) |

No other fix is planned: Scopes 3–7 have nothing present, and Scope 8 is not fixed (see above).

## Fixes applied (added after the fixes were made and re-verified)

Exactly the three fixes listed above were applied. No other file was changed.

**`frontend/components/shell/topbar.tsx`** (Scope 1):
```diff
         <button
           type="button"
           title="Notifications"
+          aria-label="Notifications"
 ...
         <button
           type="button"
           title="Settings"
+          aria-label="Settings"
```

**`frontend/components/shell/sidebar.tsx`** (Scope 2):
```diff
-    <aside className="flex flex-col gap-1 bg-sidebar-bg px-3 py-5 text-sidebar-text">
+    <nav className="flex flex-col gap-1 bg-sidebar-bg px-3 py-5 text-sidebar-text">
 ...
-    </aside>
+    </nav>
```

### Re-verification (after rebuild, same browser and method)

- `npx tsc --noEmit`: pass. `npm run build`: exit 0.
- **Landmarks (all 10 routes):** `navigation, main` (before: `complementary, main`). Scope 2 landmark: **PASS**.
- **Topbar accessible names (all 10 routes):** `button:"Notifications"`, `button:"Settings"` (before: `"◔"`, `"◈"`). Scope 1: **PASS**.
- **Tab order (all 10 routes):** unchanged. The 10 sidebar links in visual order, then the search input, Notifications, Settings.
- **Keyboard activation:** `Enter` on the Workflows link still navigates to `/workflows`, and the route announcer still reads "Workflow Builder". `Enter` + `Space` on both topbar buttons: 0 exceptions.
- **No visual regression.** Bounding boxes are identical before and after:
  - Sidebar container: `[0,0,240,808]` (tag `ASIDE` → `NAV`).
  - All 10 nav links: identical x/y/w/h, for example `/dashboard [12,133.5,216,38.25]` and `/integrations [12,594.75,216,38.25]`.
  - Notifications `[1226,14.5,34,34]` and Settings `[1272,14.5,34,34]`: identical.
  - Computed sidebar style after the swap: `display:flex; flex-direction:column; gap:4px; background rgb(15,23,42); padding 20px 12px; color rgb(203,213,225); font-size 14px`. These are the same Tailwind classes, and no global CSS targets `aside` or `nav`.

### Still open (not fixed, by rule)

- 8a skip link: needs approved link text and a focus-visible style (Rules 2 and 4).
- 8b focus target on route change: ambiguous (Rule 5).
- Scopes 3–7: the elements don't exist yet. They should be re-audited when SPEC-FE-009/010/011/013/015/018 are built.
- The four outside-scope observations above (Analytics tabs pattern, search input label, heading containing a button, inert buttons) are for a future spec to decide.
