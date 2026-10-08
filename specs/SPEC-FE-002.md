# SPEC-FE-002: App Shell, Routing Stubs, and Frontend Conventions

## Purpose
Build the persistent application shell (sidebar navigation + topbar) and Next.js App Router routing for all 10 nav pages as inert, static stubs — reproducing the mockup's sidebar/topbar exactly — and author the frontend CLAUDE.md conventions doc that every subsequent SPEC-FE-XXX spec will target, the same way the backend's CLAUDE.md governs backend specs.

## Scope
In scope:
- A persistent shell layout containing the sidebar (brand block, 3 nav sections with the exact items/icons/order below) and topbar (search input placeholder, 2 icon buttons, avatar).
- Client-side active-nav-item highlighting based on the current route, mirroring the mockup's .nav-item.active treatment.
- 10 route pages, each rendering only its exact page title and, where the mockup shows a fixed page subtitle, that exact subtitle. The Campaigns page is the one exception: the mockup's subtitle there ("Step 3 of 6 — Creative") is a specific wizard step, not a fixed page subtitle, so this spec renders only the title "Campaign Wizard" with no subtitle.
- A CLAUDE.md file at the frontend repo root documenting the folder/file conventions subsequent specs rely on.

Explicitly NOT being built by this spec:
- Any card/table/chart/panel content inside any of the 10 pages
- The search input's actual search behavior
- The notification/settings icon buttons' actual behavior
- The avatar's real user identity/menu
- Light/dark theme toggle control (the CSS variables already support both modes per SPEC-FE-001; no UI toggles it yet)
- Authentication/login (assume an already-authenticated user for now)
- The Campaign Wizard's real step content/subtitle behavior

## Contract
Not an HTTP contract. Deliverable: all 10 routes render, the shell wraps them consistently, and CLAUDE.md exists documenting conventions.

## Functional rules
1. Sidebar: brand block with the literal "AI" logo mark and "Orchestrator" wordmark. Three nav sections in this exact order:
   - "Main": Dashboard → /dashboard (icon ◉), Command Chat → /chat (icon ◈)
   - "Engines": E-Commerce → /ecommerce (icon ▤), Marketing → /marketing (icon ◍), Customer Service → /customer (icon ◐)
   - "Configuration": Knowledge Base → /kb (icon ▦), Campaigns → /campaigns (icon ◆), Workflows → /workflows (icon ◇), Analytics → /analytics (icon ▨), Integrations → /integrations (icon ◎)
   Reproduce the exact icon glyphs and labels — copy the literal Unicode characters from the reference HTML; do not substitute an icon font or SVG set in this spec.
2. Each nav item is a Next.js <Link> to its route. The item matching the current pathname gets the active treatment (sidebar-active background, white text, using the tokens from SPEC-FE-001).
3. Topbar: one search <input> with placeholder "Search products, orders, campaigns..." (non-functional); two icon buttons with the literal glyphs ◔ (title "Notifications") and ◈ (title "Settings"), both non-functional (no click handler, no dropdown); an avatar element showing the literal initials "RB" — a static placeholder, not derived from any real user data source yet.
4. Route structure: one shared layout (app/(app)/layout.tsx) rendering the sidebar + topbar around {children}; ten page files beneath it, each rendering only an <h1> with its exact title and, where specified below, its exact fixed subtitle:
   - Dashboard: "What's happening across your business, right now."
   - Command Chat: "Talk to your business. Direct all three engines in plain language."
   - E-Commerce Automation: "Catalog, orders, inventory, pricing — all in one place."
   - Marketing Automation: "Content, scheduling, ads — coordinated across every channel."
   - Customer Service: "Unified inbox — WhatsApp, Messenger, IG DM, email."
   - Business Knowledge Base: "Everything the AI needs to know to speak for your business."
   - Campaign Wizard: title only, no subtitle (see Scope)
   - Workflow Builder: "Compose triggers, conditions, and actions visually."
   - Analytics: "Real-time performance across sales, ads, engagement, and service."
   - Integrations: "Connect the platforms your business runs on."
5. Visiting "/" redirects to "/dashboard".
6. Create CLAUDE.md at the frontend repo root documenting: the page-route folder convention just established (app/(app)/<page>/page.tsx); where shared UI primitives will live (components/ui/); where domain-specific components will live (components/<domain>/, one folder per nav page, created only when a spec needs it); where API client functions will live (lib/api/<domain>.ts, one file per backend domain); where shared TypeScript types will live (lib/types/<domain>.ts); where TanStack Query hooks will live (hooks/use-<domain>.ts); and that every subsequent SPEC-FE-XXX spec touching an existing page targets exactly its already-created page.tsx plus at most 3 new/existing files across components/<domain>/, lib/api/<domain>.ts, lib/types/<domain>.ts, and hooks/use-<domain>.ts — mirroring the backend's 4-file-per-spec discipline.

## Edge cases
- Any route outside the 10 pages plus "/": render Next.js's default 404 — no custom 404 page in this spec.
- No responsive/mobile layout is specced; the mockup itself defines none — carry over its fixed 240px-sidebar grid layout as-is.

## Non-functional rules
- No data fetching, no TanStack Query usage, no API calls anywhere in this spec — every page is fully static.
- Reuse the CSS variables/Tailwind tokens from SPEC-FE-001; introduce no new color values.
- No new dependency beyond what SPEC-FE-001 already installed.
- Only components/shell/sidebar.tsx and components/shell/topbar.tsx are created under components/ in this spec — no domain component folders yet.

## Acceptance criteria
1. Visiting "/" redirects to "/dashboard".
2. Each of the 10 routes renders its exact title (and subtitle where specified) and nothing else.
3. The sidebar shows all 10 nav items grouped into the exact 3 sections, in the exact order, each with its exact icon glyph and label.
4. Navigating between pages updates which nav item shows the active treatment to match the current route.
5. The topbar's search input and two icon buttons render with their exact placeholder/title text and produce no visible behavior when interacted with.
6. CLAUDE.md exists at the frontend repo root and documents every convention in Functional Rule 6.
7. No API call, fetch, or TanStack Query hook exists anywhere in the code added by this spec.

## Assumptions
- The "RB" avatar initials and all topbar icon behavior are placeholders; real auth/user-identity wiring is a later spec.
- The Campaign Wizard's real subtitle/step behavior is deferred to its own feature spec.
- No responsive/mobile layout is being specced.

## Target files
This spec creates the shell/routing structure — an authorized exception like SPEC-FE-001, since these files don't exist yet:
- app/(app)/layout.tsx
- app/(app)/dashboard/page.tsx
- app/(app)/chat/page.tsx
- app/(app)/ecommerce/page.tsx
- app/(app)/marketing/page.tsx
- app/(app)/customer/page.tsx
- app/(app)/kb/page.tsx
- app/(app)/campaigns/page.tsx
- app/(app)/workflows/page.tsx
- app/(app)/analytics/page.tsx
- app/(app)/integrations/page.tsx
- app/page.tsx (replacing SPEC-FE-001's placeholder with the redirect to /dashboard)
- components/shell/sidebar.tsx
- components/shell/topbar.tsx
- CLAUDE.md
