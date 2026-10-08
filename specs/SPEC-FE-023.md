Deviation from draft: several elements this spec expects are not in the current markup and are left to be audited as "not present" rather than invented — Scope 3's selectable rows do not exist (the Command Chat UI, SPEC-FE-008–010, and the Customer Service table, SPEC-FE-013, are unbuilt; the Workflows table from SPEC-FE-017 has no row selection, since selection is SPEC-FE-018, which is unbuilt; the SPEC-FE-014 reply panel exists in components/customer/reply-draft-panel.tsx but is not mounted on any page); Scope 4's E-Commerce (SPEC-FE-011) and Customer Service (SPEC-FE-013) tables are unbuilt, and Analytics Top Products (SPEC-FE-020) renders no status badges (its Trend column is ▲/▼ plus percentage text), so the only status badges currently rendered are in the Workflows table (SPEC-FE-017) and the Integrations grid (SPEC-FE-021), which Scope 4 does not list; Scope 5's plan card (SPEC-FE-009) and approvals panel (SPEC-FE-010) are unbuilt; Scope 6's Brand Settings form (SPEC-FE-015) is unbuilt; Scope 7 has no subject, since no Radix UI primitive is imported anywhere in app/ or components/ (the packages are only installed).

# SPEC-FE-023: Accessibility Pass (Keyboard Navigation, Screen-Reader Labels, Focus Management)

## Purpose
Every interactive surface built across SPEC-FE-002 through SPEC-FE-021 must be operable via keyboard alone and legible to assistive technology. This is an audit-and-fix pass over existing UI, not new feature or visual work — it adds semantics and keyboard support to elements the mockup already renders, it does not add anything the mockup doesn't show.

## Scope
1. Icon-only topbar buttons (Notifications ◔, Settings ◈ from SPEC-FE-002): confirm each has an accessible name (the mockup's own `title` attribute text — "Notifications" / "Settings" — surfaced as `aria-label`, not invented copy) and is keyboard-focusable/activatable.
2. Sidebar nav items (SPEC-FE-002): confirm the active route is exposed via `aria-current="page"` and the list is a proper nav landmark with keyboard tab order matching visual order.
3. Master-detail row selection (Command Chat's message/approval interactions if applicable, Customer Service's conversation table from SPEC-FE-013/014, Workflows' Saved Workflows table from SPEC-FE-017): confirm each selectable row is keyboard-reachable and activatable (Enter/Space), exposes its selected state (`aria-selected` or equivalent), and that selecting a row moves focus or announces the change sensibly — do not add any behavior beyond making the existing default-select-first-row pattern (already documented in those specs) operable by keyboard.
4. Tables with status badges (E-Commerce products in SPEC-FE-011, Customer Service in SPEC-FE-013, Analytics Top Products in SPEC-FE-020): confirm badge color is never the only signal — each badge's text content (e.g. "Out of Stock", "Active") must already be present as real text (per those specs) and read correctly by a screen reader; do not add new badge states.
5. Command Chat plan card buttons (Approve All / Reject All / Review Each, SPEC-FE-009) and approval panel buttons (View / Approve, SPEC-FE-010): confirm each button has a clear accessible name distinct from any other same-labeled button on the page (e.g. multiple per-row "Approve" buttons need row context in their accessible name, such as `aria-label="Approve: <item title>"`), since the visual label alone is ambiguous out of visual context.
6. Brand Settings form (SPEC-FE-015): confirm every input/slider/select has a programmatically associated `<label>` (matching the mockup's own visible label text, not invented text), and that slider controls expose current value via `aria-valuenow`/`aria-valuetext` if using a custom slider component rather than a native `<input type="range">`.
7. Any Radix UI primitive already in use anywhere in the app: confirm it isn't overriding Radix's built-in accessibility behavior (Radix primitives are accessible by default — this step is a check that nothing added on top, like a custom onKeyDown, broke that default, not a rebuild).
8. Global: confirm there is a working "skip to main content" link before the sidebar, and that focus visibly moves to the correct heading on route change (App Router's default focus behavior, or a minimal explicit fix only if it's currently absent).
9. Write findings to specs/reports/SPEC-FE-023-findings.md: each check, pass/fail, file/line for any fail, and the minimal fix.

## Explicitly NOT being built
- No new visual states, no new interactive flows, no new copy beyond the mockup's own existing text/labels.
- No accessibility feature for content that isn't actually built yet (e.g. nothing here touches Marketing's table/calendar, Campaign Wizard's other steps, or Integrations' OAuth — those remain out of scope per their original specs' own exclusions).
- No introduction of a UI component library or pattern not already established in SPEC-FE-001/003 (Radix + existing custom components only).

## Target files / outputs
- New: specs/reports/SPEC-FE-023-findings.md
- Existing files: touched only to add accessibility attributes (aria-*, label associations, tabIndex/keyboard handlers, focus management) to elements that already exist. No structural or visual redesign. Every touched file must be named in the findings report with a before/after of the specific attribute(s) added.

## Functional Rules
1. Audit first, fix second: write the complete findings report before making any change.
2. Never invent an accessible name from scratch — derive it from the element's own existing visible text/label/title per the mockup, only reformatted for assistive tech (e.g. an icon button's existing `title` becomes its `aria-label`).
3. Prefer native semantic HTML (`<button>`, `<label>`, `<nav>`, native `<input type="range">`) over ARIA-patched divs wherever the current implementation allows a small, safe swap; if swapping would be a larger change than adding ARIA attributes, add the ARIA attributes instead and note the tradeoff in the report.
4. Do not change any element's visual appearance, only its semantics/keyboard behavior — if a fix seems to require a visual change, stop and report it instead of applying it.
5. If a check requires information not available from the current code or the original spec (e.g. what the "correct" focus target on route change should be), stop and report the ambiguity rather than guessing.

## Acceptance Criteria
- specs/reports/SPEC-FE-023-findings.md exists and covers all 9 scope items with pass/fail and fixes for any fail.
- Every interactive element listed in Scope is confirmed keyboard-operable (tab to it, activate with Enter/Space).
- Every icon-only or ambiguous-label button has a correct, non-fabricated accessible name.
- No visual regression: a diff review of any touched file shows only attribute/semantic additions, no style or markup structure changes beyond what's needed for the swap in Rule 3.
- No item outside the 9 scope items above was touched.
