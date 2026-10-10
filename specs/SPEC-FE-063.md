# SPEC-FE-063: Responsive sidebar (drawer on small screens)

Status: IMPLEMENTED and verified (2026-10-10), asked by the user: "fix the sidebar". Headless Chrome on the running app,
twice: AC1/AC2 pass, at 375 px the chat panel is 343 px wide; `tsc` and `next build` are clean. Found by the SPEC-FE-061 browser E2E: at 375 px the
fixed 240 px sidebar left the page ~100 px of width.

## Requirements

- **FR1 (≥ 1024 px):** unchanged: the sidebar is a sticky 240 px column next to the page.
- **FR2 (< 1024 px):** the sidebar is hidden and the page uses the full width. A ☰ button at the left of the top bar opens
  it as a 260 px drawer from the left over a dimmed backdrop (`--sidebar-bg` at 60 %).
  - It closes on: the ✕ in the drawer, a tap on the backdrop, Escape, or choosing a page.
  - While open, the page behind doesn't scroll. While closed, the drawer is invisible to the keyboard and screen readers.
- **FR3:** the top bar and page padding tighten below 1024 px (16 px instead of 24 px); the search box shrinks to fit.
- **FR4 (unchanged):** the nav items, groups, remembered open groups, logo, active states and every page.

Topbar and sidebar are separate client components inside a server layout, so the ☰ button tells the sidebar with a
window event (`shell:toggle-nav`): no new file or provider.

## Acceptance criteria

- **AC1:** at 375 px, no sidebar is visible, the page is full width, and there is no horizontal scroll. ☰ opens the drawer;
  the backdrop, Escape, ✕ and a nav link each close it.
- **AC2:** at 1360 px, the sidebar looks and works as before.
- **AC3:** `tsc` and `next build` pass.

## Target files

`app/(app)/layout.tsx`, `components/shell/sidebar.tsx`, `components/shell/topbar.tsx`.
