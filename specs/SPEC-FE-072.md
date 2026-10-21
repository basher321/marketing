# SPEC-FE-072: PilotSonic design — public website, sign-in gate, app shell and dashboard head

Status: IMPLEMENTED (code, 2026-10-19..21; written after the fact). `next build` is clean and the build is live at
https://pilotsonic.com (SPEC-BE-105). Browser E2E of every page in both themes and on a phone is pending.
- **Design sources:** `pilotsonic-website.html` (the website) and the PilotSonic dashboard design (shell, gate,
  Preferences, palette, tab bar). Neither file is in the repo; `ai_orchestrator_frontend(1).html` is the older
  mockup the page content follows.
- No backend change. Every page keeps its data, fields and logic; this is the look, the navigation and the website.

## Requirements

### R1 — Public website at `/`
- `app/page.tsx` renders `components/landing/landing-page.tsx` (+ `landing.module.css`). It sits outside the `(app)`
  group: no shell, no sign-in guard.
- Sections from the design: hero (headline, live-looking preview cards), `#features`, `#lab`, `#how`, `#pricing`
  (Starter $29/mo, Growth $79/mo, …), `#faq`, a closing call to action; a theme toggle; reveal-on-scroll and
  count-up numbers (off with reduced motion).
- The design's simulated Google gate is replaced by the real pages: "Sign in" → `/login`, "Start free" → `/signup`,
  and "Open dashboard" when a session already exists.

### R2 — Sign-in gate
- `components/auth/auth-shell.tsx` restyles `/login`, `/signup`, `/forgot-password`, `/reset-password`: always dark,
  an aurora background, the PilotSonic brand and pitch on the left, a glass card on the right.
- The forms, fields and logic (SPEC-FE-004/024/038, SPEC-BE-040) are unchanged; their `.neu-*` classes are restyled.
  No Google button: the backend has no Google sign-in.

### R3 — App shell
- `app/(app)/layout.tsx`: a floating sidebar panel + a main column (glass top bar, only `.content` scrolls) filling
  the viewport (`components/shell/frame.tsx`), inside the Query provider (SPEC-FE-003) and the route guard
  (SPEC-FE-004).
- **Navigation** (`components/shell/nav.ts`, one list for the sidebar, the tab bar, the palette and the top bar
  title): sections Main / Engines / Configuration; Marketing keeps its sub-pages (SPEC-FE-049/054); Settings stays
  (SPEC-FE-036); Admin only for the super admin (SPEC-FE-068).
- **Sidebar** (`sidebar.tsx`): logo tile (the company logo from SPEC-FE-036 replaces the PilotSonic mark when
  uploaded), line icons (`icons.tsx`), accent pill on the active page, groups opened by hand remembered per browser,
  a compact icon-only mode, and an "Autopilot" card with the real number of enabled workflows linking to Workflows
  (there is no global autopilot switch in the backend).
- **Top bar** (`topbar.tsx`): page title from `nav.ts`, the collapse/expand-sidebar button, a search pill that opens
  the palette, a notification bell listing pending approvals (the backend has no notifications feed; same query and
  cache as Command Chat's Pending Approvals), Preferences, and the account menu.
- **Overlays** (`overlays.tsx`):
  - command palette (Ctrl/⌘ K; type to filter pages, ↑/↓, Enter);
  - Preferences sheet;
  - below 900 px, a bottom tab bar with a More sheet (replaces the SPEC-FE-063 drawer).
- **Page entrance:** `app/(app)/template.tsx` remounts per navigation and applies `.page-in` (rise-in), off when
  motion is off.

### R4 — Preferences (per browser)
- `components/shell/prefs.ts`, key `pilotsonic.prefs` in localStorage, every access in try/catch (private mode,
  blocked storage) with defaults: theme `auto` (light / dark / auto), accent `#4f46e5` (Indigo, Violet `#7c3aed`,
  Teal `#0d9488`, Rose `#e11d48`, Orange `#ea580c`), density comfortable / compact, motion full / off, card spotlight
  on, sidebar not collapsed.
- Applied as attributes and CSS variables on `<html>`. A boot script in `app/layout.tsx` applies the same key and rules
  before first paint, so the theme and accent never flash. Colors stay CSS tokens (`globals.css`), with dark values.

### R5 — Dashboard head
- `components/dashboard/hero.tsx`: a greeting by the browser's hour (Working late < 5, Good morning < 12, Good
  afternoon < 17, Good evening < 21, Good night), read after mount so server and client markup agree; the signed-in
  user's first name; a live Autopilot pill (enabled workflows).
- Four quick actions; each opens a **new** Command Chat with its request in the composer, ready to send (not sent):
  "Create 7 organic posts and schedule them", "How are my ads doing?", "What is low on stock?", "Any customers waiting
  for a reply?".

### R6 — Brand assets
- `public/brand/favicon.png`, `mark.png`, `wordmark.png`; the favicon is set in `app/layout.tsx`.

## Acceptance criteria
1. `/` shows the website signed out; with a session, its button reads "Open dashboard" and opens `/dashboard`.
2. `/login` and `/signup` sign in and register exactly as before (SPEC-FE-038), in the dark gate.
3. Every sidebar entry opens its page; Ctrl/⌘ K finds any page by name and opens it with Enter.
4. Preferences changes (theme, accent, density, motion, spotlight, compact sidebar) apply at once, survive a reload
   without a flash, and the app still works with storage blocked.
5. Below 900 px: no sidebar, a bottom tab bar, More opens the rest; no horizontal scroll.
6. A dashboard quick action opens a new chat with the request typed in and nothing sent.
7. `npx tsc --noEmit` and `next build` are clean.

## Files
- `app/page.tsx`, `components/landing/landing-page.tsx`, `components/landing/landing.module.css`
- `components/auth/auth-shell.tsx`, `app/login/page.tsx`, `app/signup/page.tsx`
- `app/layout.tsx`, `app/(app)/layout.tsx`, `app/(app)/template.tsx`, `app/globals.css`
- `components/shell/{frame.tsx,nav.ts,icons.tsx,overlays.tsx,prefs.ts,sidebar.tsx,topbar.tsx}`
- `components/dashboard/hero.tsx`, `app/(app)/dashboard/page.tsx`, and the restyled pages under `app/(app)/`
- `public/brand/*`, `next.config.mjs`, `tsconfig.json`
