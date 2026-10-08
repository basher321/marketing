# SPEC-FE-054: SocialAPI screens (Organic › SocialAPI and the SocialAPI inbox)

Status: IMPLEMENTED (code, 2026-10-07). `npx tsc --noEmit` and `next build` are clean, and
the 3 new routes build. The running dev server (:3000) serves `/marketing/organic/socialapi`
and `/customer/socialapi` with 200. **Pending:** the browser E2E of acceptance 1–6 against
a backend with `META_FAKE_TRANSPORT=true`. The backend round trip itself is verified in
SPEC-BE-083. Requested by the user. Backend: SPEC-BE-083.

## Screens

1. **Organic Marketing › SocialAPI** (`/marketing/organic/socialapi`; a new last tab in
   `OrganicHeader`):
   - **Key card:** paste, Save & test, Test, Remove, status, and last error.
   - **Once a key exists:**
     - *Accounts:* platform picker + Connect (browser → SocialAPI sign-in), list with
       status and Disconnect.
     - *Composer:*
       - text with the strictest character limit of the chosen platforms;
       - title and first comment;
       - media from the existing media library picker;
       - accounts (a board picker for Pinterest);
       - now / schedule (browser time) / draft.
     - *Posts list:* status filter, per-account links, metrics and errors, and Publish
       now / Retry / Delete-Cancel.
     - *Account analytics:* 7/30/90 days. A gauge shows its latest value and a counter
       shows its total; "—" when there is no data.
2. **Callback** (`/marketing/organic/socialapi/callback`): reads
   `status/state/platform/account_id/connection_id/error*` and posts them to the backend.
   Success returns to the page. For a Facebook Page or Google location it shows a
   picker, and errors are shown in plain text.
3. **Customer Service › SocialAPI inbox** (`/customer/socialapi`; a "SocialAPI inbox →"
   button on the Customer Service header): Messages / Comments / Reviews tabs.
   - **Messages:** conversation list + thread (`.msg.user` / `.msg.ai`) + reply, with a
     note about the 24-hour window.
   - **Comments:** commented posts → comments, with Reply / Hide-Unhide / Delete.
   - **Reviews:** a location picker, stars, and the existing reply or a reply box.
   - **"✨ Draft with AI":** fills the reply box from the backend drafter; nothing is
     sent until Send.

Without a key, the inbox page links to the Organic SocialAPI page.

## Acceptance (pending browser run)

1. Save a key: the card shows connected, masked, and the account count; a bad key shows
   SocialAPI's error.
2. Connect Instagram: the fake round trip returns to the page with the account listed.
   Facebook shows the Page picker.
3. Publish now to two accounts with an image: the post appears with Open links and
   metrics. Schedule, then Publish now, then Delete.
4. Messages: send a reply and it appears in the thread. Draft with AI fills the box.
5. Comments: reply and hide. Reviews: reply shows the "pending" note.
6. A viewer sees the data; the write buttons answer "Your role can't do this…".

## Files

- New:
  - `app/(app)/marketing/organic/socialapi/page.tsx`
  - `…/socialapi/callback/page.tsx`
  - `app/(app)/customer/socialapi/page.tsx`
  - `components/socialapi/publishing.tsx`
  - `components/socialapi/inbox.tsx`
  - `lib/api/socialapi.ts`
  - `lib/types/socialapi.ts`
- Changed (entry points only):
  - `components/organic/shared.tsx` (one tab entry)
  - `app/(app)/customer/page.tsx` (one header link)
  - `app/(app)/integrations/page.tsx` (2026-10-07: the same key card, under AI Models, with links. The user couldn't find where to enter the key.)
  - `components/shell/sidebar.tsx` (2026-10-07: a "SocialAPI" child under Marketing)

The new routes are more than the usual 3-file limit, because this is a new section; it
was approved in the plan.
