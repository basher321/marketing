# SPEC-FE-076: Command Chat gets two tabs — Command and Inbox

Status: IMPLEMENTED (2026-10-22). Browser E2E: Inbox tab lists the SMS thread, thread + customer panel, a reply goes out (✓), Command tab unchanged. Deviation: no `/integrations/whatsapp/callback` page; Embedded Signup is a popup, so the Integrations card posts the result itself. The production CSP now allows connect.facebook.net and *.facebook.com for it. The inbox deep link is `?conv=` (`?c=` is the Command chat id). Backend SPEC-BE-112, SPEC-BE-114.

## Requirements

- `/chat` gets tabs **Command** (everything that exists today, unchanged) and **Inbox**; `?tab=inbox` opens the
  inbox. The chat history sidebar shows only on Command.
- **Inbox layout** (three panes on desktop, stacked on mobile with back buttons):
  - **Channel selector** from `GET /inbox/channels` ("All channels" + one entry per connected account, with the
    platform icon and account name). No channels → a setup card linking to Integrations / Organic › SocialAPI.
  - **Conversation list:** search, status filter, Unread only, Assigned to me; rows with avatar, name, channel
    icon, preview, time, unread dot, a **Sample** tag when `is_sample`. Infinite scroll by cursor.
  - **Thread:** messages with timestamps and delivery ticks (sent / delivered / read / failed + the error),
    attachments, the AI draft (approve / edit / send, as Customer Service does today), composer with media
    picker only when `can_send_media`; WhatsApp's 24-hour message shown as returned.
  - **Customer panel:** SPEC-BE-109 summary (orders with badges, link to the record) or, for a SocialAPI thread,
    the participant with "Link to customer". Status and assignee controls for local conversations.
- Polls the list every 20 s and the open thread every 10 s while the tab is visible.
- `/customer` (Customer Service) keeps its metrics and links "Open inbox" → `/chat?tab=inbox`.
- **Integrations:** a WhatsApp card (Connect with Facebook via Embedded Signup, status, reconnect, disconnect;
  "Not set up by PilotSonic yet" when the Super admin hasn't configured it) and an SMS card (read-only status and
  number; "Ask PilotSonic for a number").

## Files

`app/(app)/chat/page.tsx`, new `components/inbox/*`, new `lib/api/inbox.ts`, `lib/types/inbox.ts`,
`app/(app)/customer/page.tsx`, `app/(app)/integrations/page.tsx`, new
`app/(app)/integrations/whatsapp/callback/page.tsx`.
