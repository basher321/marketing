# SPEC-FE-058: New things open in a new browser tab

Status: IMPLEMENTED (2026-10-09), approved by the user. AC5 passes: `npx tsc --noEmit`, and `next build` with
`NEXT_BUILD_DIR`. AC1-AC4 (the tab behaviour) haven't been clicked through in a browser yet. Three `router`
variables became unused and were removed. Request: "we need new tab but this software creates anything
doing it on same tab. please fix this problem, if any new tab need then it will create new tab for any
new thing." The user chose these scopes: created items, Command Chat "Open" links, and "+ New …" buttons.

## Rule: one new tab per new thing

- **Starting something** ("+ New campaign", "Create post", "Create with AI") opens its form in a new tab.
  That tab is marked as belonging to the new thing.
- **After a create:**
  - In a marked tab, the created item's editor replaces the used form in that same tab, and the mark
    is cleared. No second tab opens.
  - Anywhere else (the Organic › Create tab, the Photo/Video studio, a later create in the same tab),
    the created item opens in a new tab, and the current page stays as it was.
- **Command Chat** result links ("Open") open in a new tab, so the chat stays open.
- **Unchanged:**
  - In-page "+ New/Add …" forms (pricing rule, shipping zone/rate, FAQ, policy, user, workflow, audience,
    MCP tool) have no page of their own and stay inline.
  - Navigation inside a flow (Ad Manager platform cards, mode tabs, steppers), the sidebar and every other
    link.

## Requirements

- **FR1 (`hooks/use-new-tab.ts`, new):**
  - `newTabHref(path)` adds `nt=1`.
  - `rememberNewThingTab()` stores a per-tab mark in `sessionStorage` when the page loads with `nt=1`. It
    is called once from `app/(app)/providers.tsx`.
  - `useCreatedItemTab()` returns `{begin, open, cancel}`:
    - `begin()` runs in the click/submit handler (the user gesture, so pop-up blockers allow it). In an
      unmarked tab it opens a blank tab showing "Opening…".
    - `open(path)` sends that tab to the created item. In a marked tab it uses `router.replace(path)` and
      clears the mark.
    - `cancel()` closes the blank tab on an error, so the error shows on the original page.
    - If the browser blocked the pop-up, `open` falls back to the same tab.
  - Every `sessionStorage` access is wrapped in try/catch.
- **FR2 (created items):** the hook is wired into:
  - Photo/Video studio "Approve & open the post editor" (`components/organic/generation-studio.tsx`);
  - Organic Create, manual and AI (`components/organic/create-form.tsx`);
  - Paid New campaign, Meta and the other platforms (`app/(app)/marketing/paid/new/page.tsx`);
  - Paid Create with AI (`app/(app)/marketing/paid/ai/new/page.tsx`).
- **FR3 (entry buttons):** these are `target="_blank"` links to `newTabHref(...)`:
  - Organic dashboard: "Create post", "Create with AI", and the "Write a post" / "Create with AI" cards
    (`app/(app)/marketing/organic/page.tsx`);
  - Paid Marketing: "+ New campaign" and the AI runs "Create with AI" (`app/(app)/marketing/paid/page.tsx`);
  - Marketing › Active Campaigns: "+ New Campaign" (`components/marketing/campaigns-table.tsx`). It now
    goes to `/marketing/paid/ad-manager`, where "+ New campaign" on Paid Marketing goes. It used to point
    at the Paid list.
- **FR4 (chat):** the "Open" link on a Command Chat result (`components/chat/chat-panel.tsx`) and on a
  plan step (`components/chat/plan-card.tsx`) has `target="_blank" rel="noopener"`.

## Acceptance criteria

- **AC1:** on /marketing/organic/photo, "Approve & open the post editor" opens the editor in a new tab,
  and the Photo page stays. On an error the blank tab closes and the error shows.
- **AC2:** Paid › "+ New campaign" opens Ad Manager in a new tab. Creating the campaign there opens the
  builder in that same tab: no third tab.
- **AC3:** Organic › Create (tab bar) → Create opens the editor in a new tab.
- **AC4:** a chat result "Open" opens in a new tab.
- **AC5:** `npx tsc --noEmit` and the production build pass.

## Target files

`hooks/use-new-tab.ts` (new), `app/(app)/providers.tsx`, `components/organic/generation-studio.tsx`,
`components/organic/create-form.tsx`, `app/(app)/marketing/paid/new/page.tsx`,
`app/(app)/marketing/paid/ai/new/page.tsx`, `app/(app)/marketing/organic/page.tsx`,
`app/(app)/marketing/paid/page.tsx`, `components/marketing/campaigns-table.tsx`,
`components/chat/chat-panel.tsx`, `components/chat/plan-card.tsx`.

This goes past the usual "page + 3 files" limit, because the rule is cross-cutting and the user asked for
it everywhere.
