# SPEC-FE-001: Frontend Project Scaffold (toolchain + design tokens)

## Purpose
Initialize the actual Next.js 15 (App Router) + React 19 + TypeScript frontend project — the toolchain, build configuration, and design-token foundation — matching exactly the CSS custom properties already defined in the static reference mockup (ai_orchestrator_frontend.html / ai_orchestrator_frontend1.html, identical files), so every subsequent SPEC-FE-XXX spec has a real, running project and a consistent token system to build on. This is the frontend equivalent of SPEC-BE-001.

## Scope
In scope: package.json with the exact dependency set in Functional Rule 1; next.config; tsconfig.json (strict mode); tailwind.config extending the theme with the mockup's exact color custom properties; a global stylesheet reproducing the mockup's root CSS-variable blocks and base body rule verbatim; a minimal app/layout.tsx; a minimal app/page.tsx rendering only a placeholder string.

Explicitly NOT being built by this spec:
- The sidebar/topbar shell
- Any of the 10 nav routes/pages (dashboard, chat, ecommerce, marketing, customer, kb, campaigns, workflows, analytics, integrations)
- Any reusable component
- Any API client code
- Any state-management library
- Any charting library wiring
- Any font/icon loading beyond the system font stack the mockup already declares

## Contract
Not an HTTP contract — this is project scaffolding. Deliverable: `npm run build` and `npm run dev` both succeed with zero errors, and the running app shows only a placeholder string at `/`.

## Functional rules
1. package.json dependencies — exactly this set, no additions: next (latest 15.x), react (latest 19.x), react-dom (latest 19.x), typescript, @types/react, @types/react-dom, @types/node, tailwindcss, postcss, autoprefixer, @tanstack/react-query, @tanstack/react-table, recharts, @radix-ui/react-dialog, @radix-ui/react-dropdown-menu, @radix-ui/react-tabs, @radix-ui/react-toast, @radix-ui/react-tooltip. Add a code comment near the top of package.json noting that additional @radix-ui/react-* primitives may be added by later specs as specific components need them — this list is a starting set, not exhaustive.
2. Do not install any state-management library (Zustand, Redux, Jotai, etc.) in this spec — that decision is deferred to whichever later spec builds the app shell/auth store.
3. tsconfig.json: "strict": true, and a "@/*" path alias to the repo root, matching standard Next.js App Router convention.
4. tailwind.config: extend theme.colors so each of the following resolves to its CSS variable (e.g. colors.bg = "var(--bg)"), not a hardcoded hex, so dark mode keeps working through the variable override rather than duplicated Tailwind config: bg, panel, border, text, muted, accent, accent-soft, success, warn, danger, sidebar-bg, sidebar-text, sidebar-hover, sidebar-active, chart-1, chart-2, chart-3, chart-4, chart-5.
5. app/globals.css must reproduce, byte-for-byte identical in property values, these three blocks copied verbatim from the reference mockup (do not re-derive, approximate, or "clean up" any value):
   - the :root { ... } block: --bg:#f7f8fa; --panel:#ffffff; --border:#e5e7eb; --text:#111827; --muted:#6b7280; --accent:#4f46e5; --accent-soft:#eef2ff; --success:#10b981; --warn:#f59e0b; --danger:#ef4444; --sidebar-bg:#0f172a; --sidebar-text:#cbd5e1; --sidebar-hover:#1e293b; --sidebar-active:#4f46e5; --chart-1:#4f46e5; --chart-2:#06b6d4; --chart-3:#10b981; --chart-4:#f59e0b; --chart-5:#ef4444; --shadow: 0 1px 3px rgba(0,0,0,.06), 0 1px 2px rgba(0,0,0,.04);
   - the @media (prefers-color-scheme: dark) block guarded by :root:not([data-theme="light"]) overriding --bg:#0b1220; --panel:#111827; --border:#1f2937; --text:#f9fafb; --muted:#9ca3af; --accent-soft:#1e1b4b;
   - the :root[data-theme="dark"] block with the same overrides as above
   Also carry over the mockup's exact body rule: margin:0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); font-size:14px; line-height:1.5;
   Then add @tailwind base; @tailwind components; @tailwind utilities;. Do not port any other rule from the mockup's <style> block (no .sidebar, .nav-item, .card, .badge, etc.) — those belong to later specs.
6. app/layout.tsx: a server component setting <html lang="en">, importing "./globals.css", and rendering {children} inside <body> — nothing else.
7. app/page.tsx: a single page component rendering only the literal text "AI Orchestrator — frontend scaffold initialized" — no layout, no styling classes, no data fetching.

## Edge cases
Not applicable — this is a scaffold spec with no runtime user input yet.

## Non-functional rules
- TypeScript strict mode on; the project must build with zero type errors.
- Do not hand-author an ESLint/Prettier config; if Next.js's own scaffolding produces a default one, leave it as-is.
- Do not add any dependency not listed in Functional Rule 1.
- Do not create any of the 10 page routes, the sidebar/topbar shell, or any reusable component in this spec — that starts at SPEC-FE-002.

## Acceptance criteria
1. `npm install` succeeds with exactly the dependency set from Functional Rule 1 in package.json (plus whatever peer/dev dependencies Next.js itself requires).
2. `npm run build` and `npm run dev` both succeed with zero TypeScript or build errors.
3. Visiting `/` shows only the literal placeholder text — no sidebar, no nav, no styling beyond the font/background applied via globals.css's body rule.
4. app/globals.css's three CSS-variable blocks are byte-for-byte identical in their property values to the mockup's corresponding blocks (diff them manually against the reference file).
5. No state-management library appears anywhere in package.json.
6. No file exists yet for any of the 10 nav pages, the sidebar, or the topbar.

## Assumptions
- ai_orchestrator_frontend.html (identical to ai_orchestrator_frontend1.html) is the source of truth for every literal value copied into globals.css/tailwind.config in this spec.
- A frontend CLAUDE.md documenting folder/file conventions (where page routes, components, API client functions, and hooks will live) is intentionally deferred to SPEC-FE-002, once the shell/routing it documents actually exists — writing it now, before anything exists to follow it, would risk describing conventions that don't match what gets built.
- Exact Next.js/React patch versions are whatever `next@latest`/`react@latest`/`react-dom@latest` resolve to at implementation time; this spec does not pin exact patch numbers.

## Target files
All newly created — this is the one authorized exception to the usual "target exactly 4 existing files" rule, since no frontend repo exists yet:
- package.json
- tsconfig.json
- tailwind.config.ts
- postcss.config.js
- next.config.mjs
- app/globals.css
- app/layout.tsx
- app/page.tsx
