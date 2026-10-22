# SPEC-FE-080: API keys and developer apps are set by the Super admin only (frontend)

Status: IMPLEMENTED (2026-10-22). Browser E2E against the local backend with a company owner and a temporary
Super admin: 18/18 (owner read-only panels, Connect still offered, menus, Marketing pages open; Super admin
menu item → /admin#platforms, Companies › Keys saves HubSpot, owner then sees it masked). `tsc` clean.
The page scrolls to #platforms itself once the section has loaded. Backend part and the user's decision:
SPEC-BE-115.

## Requirements

"Super admin" = `GET /platform/me` → `super_admin`, which the shell already reads.

1. **Company Integrations page.** For the eight key providers (catalog `admin_keys`), company users get:
   - **Card:** the existing status badge and line. The button reads **View** when connected and
     **Request setup** when not.
   - **Panel:** the masked saved values (read-only) and "Managed by PilotSonic: API keys are set by
     PilotSonic's Super admin. Contact PilotSonic to connect or change this integration."
   - **Test again** stays. There are no input fields, no Save & test and no Disconnect.

   Connect-only providers, WhatsApp Embedded Signup, AI Models and the SocialAPI card are unchanged. The
   Super admin's own Integrations page is unchanged.
2. **Super admin › Companies (`/admin`):** each company row gets a **Keys** button. It opens a side panel
   listing that company's eight key providers, each with the existing connect form: the catalog's fields,
   secrets masked, Save & test, Test again, Disconnect. All of them call the new
   `/platform/companies/{id}/integrations/*` routes. `ConnectPanel` takes an optional set of operations,
   so the same form serves both pages.
3. **Social API Configuration:** a Marketing sub-menu item, **Social API Configuration**, visible to the
   Super admin only. It opens `/admin#platforms`, the existing "Platforms and sign-in apps" section
   (SocialAPI master key, Zernio, Meta / TikTok / LinkedIn developer apps), which gets that anchor.
   - `NavChild` gains `superAdmin?: boolean`.
   - `navSections(superAdmin)` in `nav.ts` returns the sections for the sidebar, the More sheet / palette
     and the top bar title, replacing the three `super_admin ? [...] : [...]` expressions.
4. **Unchanged:** Paid Marketing, Organic Marketing, the SocialAPI page, Social Accounts, the dashboard,
   Analytics and every other page, for every user.

## Acceptance criteria (browser, local and live, Super admin + company owner)

- **Company owner, Integrations:** Shopify, SMTP, WhatsApp (keys) and the CRMs show View / Request setup. The
  panel has no inputs, no Save and no Disconnect. Facebook and the ad platforms still show their Connect
  buttons.
- **Company owner, menus:** no "Social API Configuration" under Marketing. Paid Marketing, Organic Marketing,
  SocialAPI and Social Accounts are still there and open.
- **Super admin:**
  - "Social API Configuration" opens `/admin` at "Platforms and sign-in apps".
  - Companies › Keys for a company saves a key provider (dev fakes locally).
  - The company's Integrations page then shows it connected, masked.
- `npx tsc --noEmit` and `next build` pass. No console errors.

## Files

`components/integrations/connect-panel.tsx`, `components/integrations/integrations-grid.tsx`,
`app/(app)/admin/page.tsx`, `components/shell/nav.ts` (+ the three callers: `sidebar.tsx`, `overlays.tsx`,
`topbar.tsx`), `lib/api/platform.ts`, `lib/types/integrations.ts`.
