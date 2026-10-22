# SPEC-FE-078: Navigation and dashboard cards open their pages

Status: IMPLEMENTED (2026-10-22). Browser E2E: new nav items, quick cards open pages with 'Ask the agent' kept, business cards; no horizontal scroll at 390 px on the new pages. Items with a minimum role: Integrations, Workflows, Settings (manager+).

## Requirements

- **Navigation (`components/shell/nav.ts`)**, by permission:
  - Main: Dashboard, Command Chat.
  - Engines: E-Commerce, **Orders**, **Customers**, Marketing (Paid, Organic, SocialAPI), Customer Service.
  - Configuration: **Social Accounts** (`/marketing/organic/accounts`), Integrations, **Branding**, Knowledge
    Base, Workflows, Analytics, Settings.
  - PilotSonic (Super admin only, unchanged).
  - Items carry a minimum role; viewers don't see write-only pages. Hiding is convenience only; the backend
    enforces every permission.
- **Dashboard quick cards open pages** (they used to open Command Chat with a prompt):
  - Create posts → `/marketing/organic/create`
  - Review ads → `/marketing/paid`
  - Check stock → `/ecommerce?tab=inventory`
  - Reply to customers → `/chat?tab=inbox`
  - Each card keeps a small "Ask the agent" link that opens the old prompt.
- **New dashboard cards** (each links to its page): Connected accounts (count + any needing attention →
  Social Accounts), Scheduled posts (→ Organic calendar), Orders waiting for confirmation (→ `/orders?status=
  awaiting_confirmation`), Pending orders, Messages unanswered (→ inbox), and this month's Revenue / Costs /
  Profit-or-loss (→ Analytics P&L; "—" with a reason when costs are incomplete).
- Mobile tab bar and the command palette include the new pages.

## Files

`components/shell/nav.ts`, `components/shell/sidebar.tsx`, `components/dashboard/hero.tsx`,
`app/(app)/dashboard/page.tsx`, `lib/api/dashboard.ts` (or the existing per-domain APIs).
