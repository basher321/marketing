# SPEC-FE-043: Sidebar brand name "PilotSonic"

Status: IMPLEMENTED (2026-10-02), plan approved. Verified in headless Edge on dev-shop, in light and dark mode: the text reads "PilotSonic", "Pilot" is rgb(255,255,255), "Sonic" is rgb(56,189,248), and the 11 nav items are unchanged. `tsc --noEmit` passes. `npm run build` was not run, because it would overwrite `.next` under the running `next dev`.

## Purpose
The top of the left sidebar reads "Pilotsonic". The logo (`D:\marketing software related  material\logo.jpeg`) spells it **PilotSonic**, with "Pilot" in white and "Sonic" in bright blue. The sidebar text should match. The user chose the two-tone look.

## Functional rules
1. The text becomes `PilotSonic`, rendered as two spans: `Pilot` in white (as today) and `Sonic` in blue.
2. Blue: the logo's "Sonic" is a bright sky blue. The `accent` token is indigo (#4f46e5), which doesn't match. Use Tailwind's default `sky-400` (#38bdf8), the closest default color. No new hex value is added.
3. Nothing else in the sidebar changes: the logo square, its fallback, font size and weight, spacing, and the nav items stay the same. The browser tab title and other pages are out of scope.

## Acceptance criteria (E2E, headless Edge, dev-shop)
1. The sidebar shows "PilotSonic", with "Pilot" white and "Sonic" `rgb(56, 189, 248)`, in light and dark mode.
2. The accessible text of the brand block is "PilotSonic", with no space between the two parts.
3. `npx tsc --noEmit` and `npm run build` pass.

## Target files
- frontend/components/shell/sidebar.tsx (one line)
