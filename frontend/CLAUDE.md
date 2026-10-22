# CLAUDE.md (frontend)

Guidance for work inside `frontend/`. The repo-root `CLAUDE.md` covers the
backend; its old "Frontend (React/Vite/Zustand)" sections describe an earlier
plan and do not apply — this file is authoritative for the frontend.

## What this is

The AI Orchestrator dashboard: **Next.js 15 (App Router) + React 19 +
TypeScript (strict)**, Tailwind CSS 3, TanStack Query/Table, recharts, Radix
primitives. It talks to the FastAPI backend in `../backend`. The static mockup
`../ai_orchestrator_frontend(1).html` is the visual source of truth — every
label, glyph, and CSS value is copied from it, never retyped from memory.

```bash
npm install
npm run dev        # http://localhost:3000 (backend CORS_ORIGINS allows :3000 and :5173)
npm run build
npx tsc --noEmit   # strict type check
```

`NEXT_PUBLIC_API_BASE_URL` (see `.env.local.example`) is required for any API
call; `apiFetch` throws immediately if it is unset. There is no fallback host.

## Working rule: real app, verified end to end

The frontend is a real application, not a copy of the HTML. A frontend spec is
done only when its screen loads real data from the running backend, which
reads/writes the real Postgres DB, and that round trip was verified (backend +
frontend running together; DB checked inside a rolled-back transaction). Never
fake data or stub a call to make a screen "work"; if the backend endpoint is
missing or broken, stop and report it.

## Folder conventions

- **Page routes:** `app/(app)/<page>/page.tsx`. The `(app)` route group adds no
  URL segment; `app/(app)/layout.tsx` wraps every page in the shell (sidebar +
  topbar). `app/page.tsx` is the public PilotSonic website (SPEC-FE-072). Routes
  outside the group (including 404) render without the shell.
- **Shell:** `components/shell/` (`sidebar.tsx`, `topbar.tsx`).
- **Shared UI primitives:** `components/ui/`.
- **Domain components:** `components/<domain>/`, one folder per nav page,
  created only when a spec needs it.
- **API client functions:** `lib/api/<domain>.ts`, one file per backend domain,
  all calling `apiFetch` from `lib/api/client.ts` (never `fetch` directly).
- **Shared TypeScript types:** `lib/types/<domain>.ts`, mirroring the backend
  Pydantic schemas field for field. `ApiError` lives in `lib/types/common.ts`.
- **TanStack Query hooks:** `hooks/use-<domain>.ts`.
- **Auth tokens:** `lib/auth/token.ts` stores the access and refresh tokens in
  localStorage (SPEC-FE-004, SPEC-FE-024). `apiFetch` silently refreshes once on a
  401 (one shared in-flight refresh) and retries. **One login per tab (SPEC-FE-070):**
  - **Where tokens live:** pairs are stored per user (`ai-orchestrator.session.<sub>`), and sessionStorage
    `ai-orchestrator.tab_user` pins the tab's user. A new tab starts as `ai-orchestrator.last_user`.
  - **Signing in and out:** a sign-in switches only that tab, and a sign-out clears only that user.
  - **Refresh:** it runs under a Web Lock per user, so same-user tabs refresh once.

  The route guard and the 401 → `/login` handler live in `app/(app)/providers.tsx`;
  `/login` is `app/login/page.tsx`, outside the shell.

## Per-spec file discipline

Every SPEC-FE-XXX touching an existing page targets exactly that page's
`page.tsx` plus at most 3 new/existing files across `components/<domain>/`,
`lib/api/<domain>.ts`, `lib/types/<domain>.ts`, and `hooks/use-<domain>.ts` —
mirroring the backend's 4-files-per-spec discipline. No new dependency unless a
spec justifies it.

## Styling

- Colors come only from the SPEC-FE-001 CSS variables / Tailwind tokens
  (`bg`, `panel`, `border`, `text`, `muted`, `accent`, `accent-soft`,
  `success`, `warn`, `danger`, `sidebar-*`, `chart-1..5`) — no new hex values.
  Dark mode works through the `data-theme` / `prefers-color-scheme` variable
  overrides. Where the mockup hardcodes a non-token color, use the Tailwind
  default color with the exact same value (e.g. `white`, `slate-500`,
  `indigo-500`).
- `app/globals.css` holds: the three variable blocks + body rule
  (SPEC-FE-001), then `@tailwind base`, then mockup component classes copied
  verbatim (.card, .btn, .engine-*, .timeline-*, .chat-*, .msg, .approval-*,
  ...), then `@tailwind components/utilities`. Component classes go AFTER
  `@tailwind base` so Tailwind's preflight (e.g. `[type='submit']
  { background-color: transparent }`) cannot override them. Check a class
  isn't already ported before adding it.
- Tailwind scans `app/**` and `components/**`.
- Undefined interactions in the mockup (topbar icons, search, "⋮" menus,
  "View") render as static, non-functional elements with a comment, never a
  fabricated modal/menu.

## Current state

- SPEC-FE-001: scaffold + tokens. SPEC-FE-002: shell. SPEC-FE-003: `apiFetch`,
  `ApiError`, QueryClient provider (`app/(app)/providers.tsx`).
- **All 10 pages are built** and verified in a real browser against the live
  backend with the `dev-shop` demo data (2026-09-29):
  Dashboard (FE-005/006/007), Command Chat (FE-008/009/010), E-Commerce
  (FE-011), Marketing (FE-012 + campaigns table/calendar via SPEC-BE-038),
  Customer Service (FE-013/014), Knowledge Base (FE-015), Campaign Wizard
  (FE-016), Workflows (FE-017/018), Analytics (FE-019/020), Integrations (FE-021).
- Shared cache keys: a metric used on several pages uses its owning module's
  key (e.g. `conversationKeys.list`, `analyticsKeys.orderMetrics`,
  `marketingKeys.*`, `workflowKeys.list`); approvals share `approvalKeys`
  (+ the `approvalKeys.decisions` map in `components/chat/decisions.ts`).
- AI-dependent features (chat plans, creative generation) need a real
  `LLM_PROVIDER`/`LLM_API_KEY` in `backend/.env`; with the default mock they
  show the backend's own "unavailable"/"No LLM provider" message. Since
  SPEC-FE-041 every AI message carries `kind`/`plan_id`, so plan cards (live
  step status, approve/edit/retry, workflow preview) also render after a reload.
- Orchestrator v2 screens (2026-10-01), **built and `next build`-clean, but
  end-to-end verification against the DB is pending**:
  - `/marketing/paid` (was `/campaigns`; SPEC-FE-049 moved it and
    `next.config.mjs` redirects the old URLs): the list plus the Ads
    Manager-style builder at `/marketing/paid/new` and
    `/marketing/paid/[id]/edit` (`components/campaigns/builder/*`, stepper and
    Review step in `components/campaigns/review-step.tsx`). A legacy wizard
    draft still opens at `/marketing/paid?draft=`.
  - `/integrations`: "Connect with Facebook" and the
    `/integrations/meta/callback` picker.
  - Shipping tab: status bar and guided setup wizard.
  - Analytics and Marketing: real Meta CTR/ROAS, or "—".
  - Deep links: `/workflows?open=<id>`, `/ecommerce?tab=shipping`.
- E-Commerce Orders / Inventory / Pricing Rules / Shipping tabs (SPEC-FE-026
  to 029, 2026-09-30) have no mockup content; their layouts follow common
  e-commerce admin practice (Shopify/WooCommerce), as the user chose. Inventory
  Adjust, pricing rule create/toggle, and shipping zone/rate create/toggle show to
  every role (no current-user role on the client); the backend enforces manager+
  and a 403 shows a plain-language message. Verified E2E on dev-shop, with test
  writes reverted.
- Campaign Wizard (SPEC-FE-030/031, 2026-09-30) is the full 6-step flow in
  `components/campaigns/wizard.tsx`, with step 3 in `creative-variants.tsx`.
  The draft id lives in `?draft=`, so the page wraps the wizard in `<Suspense>`
  for `useSearchParams`. Every Continue PATCHes the draft. Step 4 autosaves so
  the daily amount and approval note are the backend's own numbers. Creative
  step: "Write your own" and Edit work without an LLM; "Generate with AI" shows
  a setup notice on 503. Marketing › Active Campaigns has Pause/Resume
  (SPEC-FE-032). Launch publishes nothing to ad platforms, and the Review step
  says so.
- Analytics Ads / Engagement / Customer Service tabs (SPEC-FE-035, 2026-10-01)
  share a 7/30/90-day selector; the shared `Tile`/`BarChart` live in
  `components/analytics/ads-report.tsx`. Metrics without source data (CTR,
  ROAS, likes, reach…) show "—" with the backend's reason, never an estimate.
  KB tabs (FE-033), Workflow New/Version History (FE-034) and Integrations
  (FE-037) are built too, per their specs. Inert by design:
  topbar search/icons, "⋮", "View", "Explain this".
- SPEC-FE-004: login page, client-side route guard, avatar logout, 401 →
  `/login`. SPEC-FE-024: silent token refresh, so users stay signed in (7-day
  refresh token). SPEC-FE-025 (inside `specs/SPEC-BE-040.md`, no own file):
  `/forgot-password`, `/reset-password?token=…`,
  and the show/hide eye (`components/auth/password-input.tsx`) on every password
  field. All verified in a real browser.
- Money (SPEC-FE-048): always `formatMoney(amount, currency)` from `lib/format/money.ts`
  (the currency's own symbol and decimals: "৳1,850", "$12.50", "¥1,500"); never a literal
  "৳". When a response has no currency, use `useCompanyCurrency()` (`hooks/use-tenant.ts`).
  Settings → Company lists every country/currency/language/timezone from
  `GET /tenants/locale-options`.
- `.env.local` must exist (copy of `.env.local.example`); without it every
  `apiFetch` call throws before any request is sent.
- Marketing restructure (SPEC-FE-049/050, 2026-10-03; **`tsc` and `next build`
  are clean, but E2E against the live DB is still pending**):
  - **Sidebar:** Marketing is a collapsible group with Paid Marketing and
    Organic Marketing (open groups remembered in `localStorage`, guarded).
  - **Organic Marketing:** pages are under `app/(app)/marketing/organic/`
    (dashboard, create, content/[id], photo, video, calendar, history,
    accounts, analytics). Components are in `components/organic/`: the
    `OrganicHeader` tab bar, `errorText`, timezone helpers, media picker,
    platform preview, content editor, generation studio. APIs are
    `lib/api/{organic,media,generation,social}.ts`.
  - **Media** is shown through the backend's signed URLs (`<img>`/`<video
    src>`; no bearer header needed).
  - **Roles:** as elsewhere, buttons show to every role and a 403 shows
    "Your role can't do this…".
  - **AI Models** has a video model picker (OpenAI/Gemini) and a "Videos"
    creative kind.
- SPEC-FE-051/052 (2026-10-03; **`tsc` and `next build` are clean; E2E against the live DB is pending**):
  - **Paid Marketing tabs** (`?tab=`): Campaigns, Ad Sets, Ads, Drafts, Analytics (`AdsReport`), AI runs. The Ad Sets/Ads tables live in `components/campaigns/paid-lists.tsx` (`lib/api/paid.ts`), with `?campaign=` / `?ad_set=` scoping.
  - **Social sign-in:** "Connect with Facebook/TikTok/LinkedIn" on Organic › Accounts sends the browser to the backend's `login_url`. The platform returns to `/marketing/organic/accounts/callback/[flow]`, which posts the code to the backend. Tokens never reach the browser.
  - **"What's working"** card (`components/organic/insights-card.tsx`) on the Organic dashboard and Organic Analytics.
- SocialAPI.ai (SPEC-FE-054, 2026-10-07; **`tsc` and `next build` are clean; browser E2E pending**):
  - **Organic › SocialAPI** (`/marketing/organic/socialapi`, last tab): key card, accounts + Connect, composer (media library picker, Pinterest board), posts list, and account analytics. Code is in `components/socialapi/publishing.tsx`.
  - **Other entry points:** the same key card is on Integrations (under AI Models), and the sidebar has Marketing › SocialAPI.
  - **Sign-in return:** `/marketing/organic/socialapi/callback` (handles the Page/location picker).
  - **Customer Service › SocialAPI inbox** (`/customer/socialapi`, linked from the Customer Service header): Messages / Comments / Reviews with "Draft with AI". Code is in `components/socialapi/inbox.tsx`.
  - **APIs:** `lib/api/socialapi.ts`, `lib/types/socialapi.ts`.
  - **Separation:** this is separate from the direct connections and from the Customer Service inbox, both unchanged.
  - **Production builds:** while the dev server runs, build with `NEXT_BUILD_DIR` so its `.next` is left alone.
- Zernio paid ads (SPEC-FE-055, 2026-10-08; **`tsc` and `next build` are clean; browser E2E pending**):
  - **Entry points:** Ad Manager has a third mode tab, "Zernio (all platforms)", which opens `/marketing/paid/zernio/new`. Paid Marketing has a "Zernio" tab (`?tab=zernio`).
  - **Wizard** (`components/zernio/wizard.tsx`): Platform → Account → Goal → Budget & schedule → Audience → Ad → Review, or "Boost an existing post".
    - Every option comes from `GET /zernio/platforms`.
    - Connect opens a new tab, which reports back on the `zernio-accounts` BroadcastChannel and closes itself.
  - **Zernio tab** (`components/zernio/campaigns.tsx`): campaign → ad sets → ads, with pause/resume at each level, Edit, Delete and Results. Results has the daily chart and, on Meta, breakdowns.
  - **APIs:** `lib/api/zernio.ts`, `lib/types/zernio.ts`. The sign-in return page is `/marketing/paid/zernio/callback`.
- New tabs (SPEC-FE-058, 2026-10-09): one new tab per new thing.
  - **Entry buttons** ("+ New campaign", "Create post", "Create with AI") are `target="_blank"` links to
    `newTabHref(path)`.
  - **After a create,** call `useCreatedItemTab()` (`hooks/use-new-tab.ts`): `begin()` in the click
    handler, `open(path)` in onSuccess, `cancel()` in onError. The editor opens in a new tab, or replaces
    the form when this tab was itself opened for the new thing (`nt=1`, a per-tab `sessionStorage` mark
    set in `providers.tsx`).
  - **Command Chat** "Open" links use `target="_blank"`. In-page "+ Add/New" forms stay inline.
- 403 messages (SPEC-FE-059, 2026-10-09): use `isRoleDenied(err)` (`lib/types/common.ts`), never
  `status === 403`, before showing a "your role can't…" message. Only the backend's role check
  ("Insufficient permissions…") is a role problem. Other 403s (SocialAPI/Zernio refusals, "Only the owner
  can …", an expired media link) show the backend's own text.
- Sound for AI videos (SPEC-FE-060, 2026-10-10): the card is in Integrations › AI Models (`VideoAudioSection` in
  `components/integrations/ai-models.tsx`).
  - **Controls:** the voiceover switch and voice, a music upload / pick / remove with an `<audio>` preview, and
    the volume.
  - **Media type:** `MediaKind` includes "audio", which only appears with `fetchMedia("audio")`.
- Command Chat redesign + voice (SPEC-FE-061/062, 2026-10-10; **verified by a headless-Chrome E2E with a fake microphone, 18/18**):
  - **Microphone:** `next.config.mjs` sends `Permissions-Policy: microphone=(self)`. It was `microphone=()`, which
    blocked recording; restart the dev server after changing headers.
  - **Results:** a finished plan's summary is fetched live by `plan-card.tsx`; it was only seen after a reload before.
  - **Generative UI:** the backend's structured output picks the component (`kind`, `waiting_for`, plan, `results[].data`
    shape → cards / chart / table, media). Code is in `components/chat/chat-panel.tsx`, with the plan timeline in
    `plan-card.tsx`. Styles are the `.cc-*` classes in `globals.css` (tokens + `color-mix`); the mockup's `.chat-*` classes
    are kept.
  - **Voice:** `components/chat/voice.tsx` holds the MediaRecorder recorder + waveform, the transcript into the composer
    with a language chip, the reply player (a queue: reply then summary; Listen interrupts; autoplay-blocked → "Tap to hear"), and the "Voice replies"
    switch (`localStorage` `cc-voice-replies`, guarded).
  - **Idle composer (SPEC-FE-061 Amendment A):** with no messages the composer is centred under the greeting, then moves
    to the bottom on the first send. `.cc-header`/`.cc-composer-wrap` must not shrink, or the textarea is squeezed to
    one line.
- Responsive shell (SPEC-FE-063, 2026-10-10) was replaced by the PilotSonic design (SPEC-FE-072, 2026-10-19..21):
  floating sidebar + glass top bar (`components/shell/`), command palette (Ctrl/⌘ K), Preferences (`prefs.ts`, key
  `pilotsonic.prefs`, applied before first paint by the boot script in `app/layout.tsx`), and below 900 px a bottom tab
  bar with a More sheet instead of the drawer.
- Files → job lists (SPEC-FE-064/065, 2026-10-10; **browser E2E with real AI: 21/22, the 22nd the deliberate .exe 422**):
  - **Attachments** (`components/chat/attachments.tsx`): 📎, drag-and-drop over the chat and paste; chips with upload
    progress → "Reading…" → the backend's summary. Send waits for uploads and posts `file_ids`; sent bubbles show file
    cards. Uploads use XHR for progress (`uploadChatFile`).
  - **Job board** (`components/chat/job-board.tsx`, forms in `job-editor.tsx`): `plan.job_list` plans render as the board
    (from `plan-card.tsx`): item groups, filters, edit / remove / duplicate / add, item edit, the run settings (in order,
    several at once, schedule), the submit sheet, then live progress with pause / resume / cancel / retry / approve. Run
    times are shown and typed in the company timezone. Progress messages (`kind: "progress"`) are compact lines and
    aren't spoken.
- Chat history + Projects (SPEC-FE-066, 2026-10-10; **browser E2E with real AI passed twice**):
  - **Layout:** the right column's top is `components/chat/chat-sidebar.tsx` (Chats | Projects); Pending Approvals folds
    below it (`ApprovalsPanel collapsible`). Below 900 px the history is a drawer opened by "🕘 Chats" in the chat header.
  - **URL state:** the open chat is `?c=<id>` and an open project `?p=<id>` (`app/(app)/chat/page.tsx`, inside
    `<Suspense>`). Opening another chat or "+ New chat" remounts `ChatPanel` (a `key` bump); a chat created by sending
    keeps it mounted.
  - **Chats:** search (title or message text), groups (Pinned, Today, …), and a ⋯ menu with Rename / Pin / Move to project /
    Archive / Delete. Deleting the open chat closes it at once and drops its cache, so nothing refetches it.
  - **Cache keys:** messages are `orchestratorKeys.chatMessages(chatId)` under the `messages` prefix; `plan-card.tsx` reads
    every chat's cache for live summaries.
  - **Projects:** emoji, name, description, instructions, files (uploaded with `uploadChatFile`, then linked) and
    "+ New chat in this project". A chat in a project shows its chip in the header.
  - **Opening (SPEC-FE-067):** plain `/chat` opens the latest chat (the sidebar's list cache, pinned first); a new, empty
    chat is `?new=1`.
- Step outcomes (SPEC-FE-067, 2026-10-10; **browser E2E 9/9**): a failed step shows its error, `FixLine` ("How to fix:" +
  the backend's link, from `job-board.tsx`) on the board, the plan card and the summary. `fixable()` steps (failed
  read/draft, or queued read/draft in a submitted list) have Edit; for a failed one the form's button is "Save & retry"
  (edit, then retry).
- Orders, Customers, P&L, business type, Inbox, Branding (SPEC-FE-073…078, 2026-10-22; **browser E2E with dev fakes: 41 checks, 40 by the script + 1 confirmed by screenshot**):
  - **Pages:** `/orders`, `/orders/[id]` (stage tracker, `allowed_next` actions, SMS card), `/customers`, `/customers/[id]`,
    `/branding`; Analytics › Profit & Loss (`components/analytics/profit-loss.tsx`, `?tab=profit-loss`); Settings › Store / SMS.
  - **Shared:** order badges in `components/orders/status.tsx`; the right sheet `components/ui/side-sheet.tsx`.
  - **E-Commerce** tabs come from `GET /ecommerce/config` (`components/ecommerce/catalog-extras.tsx`, `product-form.tsx`).
  - **Command Chat** has Command | Inbox tabs (`?tab=inbox`, open conversation `?conv=<key>`; `?c=` stays the chat id).
    Inbox: `components/inbox/inbox.tsx`. WhatsApp Embedded Signup is in `components/integrations/messaging-channels.tsx`
    (the production CSP allows connect.facebook.net / *.facebook.com for it).
  - **Nav** items may carry `minRole` (`forRole()` in `components/shell/nav.ts`, role from `GET /users/me`).
  - **App branding** (`components/branding/app-branding.tsx`): sidebar, sign-in shell, title and favicon.
- Dashboard stat-card spacing (SPEC-FE-079, 2026-10-22): `SummaryCards` and `BusinessCards` sit in one `.dash-stats`
  grid whose `--dash-gap` (16 px; 10 px compact or ≤ 480 px) is also the gap of both card grids, so row and column
  gaps match. Don't add margins to individual dashboard cards or grids.
