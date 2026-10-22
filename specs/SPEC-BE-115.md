# SPEC-BE-115: API keys and developer apps are set by the Super admin only (backend)

Status: IMPLEMENTED (2026-10-22). Verified on the local DB in rolled-back transactions with a real owner, a manager
and a Super admin: 22/22 checks (every acceptance criterion below), nothing persisted. Frontend part: SPEC-FE-080.

## Request (user, 2026-10-22)

The user's first draft asked to hide Paid/Organic Marketing from regular users. After clarification the
user decided (2026-10-22):

> "User can do everything but not any API and app integration. All API and social media developer app
> integration will be done by the Super admin." Users still connect their social media, messaging and
> advertising-manager accounts themselves.

So:
- **Company users** (every user except PilotSonic's Super admin, owners included) keep every feature: Paid
  and Organic Marketing, Command Chat, analytics, inbox. They also keep every **Connect / sign-in** flow:
  social accounts, Meta/Zernio/TikTok… ad accounts, WhatsApp Embedded Signup, SocialAPI accounts.
- **Only the Super admin** enters API keys, tokens, client IDs/secrets and developer-app settings.

## Current state (checked 2026-10-22)

Already Super admin only (SPEC-BE-101/102/103):
- AI keys, the SocialAPI master key and Zernio;
- the Meta / TikTok / LinkedIn sign-in apps;
- each company's SMS number.

Pasting tokens for social and ad platforms is already refused (`CONNECT_ONLY`, 409).

**Still typed by company managers** (`PUT /integrations/{provider}`), the remaining gap:

| Provider | Fields |
|---|---|
| whatsapp | phone_number_id, access_token |
| smtp | host, port, username, password, from_email |
| sendgrid | api_key, from_email |
| shopify | shop_domain, admin_token, client_id, client_secret |
| woocommerce | site_url, consumer_key, consumer_secret |
| hubspot | private_app_token |
| zoho | client_id, client_secret, refresh_token, dc |
| salesforce | instance_url, client_id, client_secret, refresh_token |

## Requirements

1. **Key providers:** `integration_service.KEY_PROVIDERS` = every catalog provider that is not in
   `CONNECT_ONLY` (the eight above). `GET /integrations/catalog` marks each with `admin_keys: true`.
2. **Company routes** (`api/v1/integrations.py`): for a key provider, `PUT /integrations/{provider}` and
   `DELETE /integrations/{provider}` answer **403** `"API keys are set by PilotSonic's Super admin. Contact
   PilotSonic to connect or change this integration."`, unless the caller is the Super admin (their own
   workspace keeps working). `POST /integrations/{provider}/test` stays manager+ (it sends no key).
   Connect-only providers, WhatsApp Embedded Signup and the Meta sign-in are unchanged.
3. **Super admin routes** (`api/v1/platform.py`, `require_super_admin`, so everyone else gets 404):
   - `GET /platform/companies/{tenant_id}/integrations`: the company's statuses for the key providers
     (masked values only, as the company route returns).
   - `PUT /platform/companies/{tenant_id}/integrations/{provider}`: save and test, with the same body and
     result as the company route.
   - `POST /platform/companies/{tenant_id}/integrations/{provider}/test`.
   - `DELETE /platform/companies/{tenant_id}/integrations/{provider}`.

   They reuse `integration_service.save_credentials / test_connection / disconnect` with the company's
   `tenant_id`. The actor is the Super admin, so the company's audit log shows who changed it. An unknown
   company is 404; a provider that isn't a key provider is 422.
4. **Unchanged:** stored credentials and how they're used (store sync, shipping, email, CRM, WhatsApp).
   Existing connections keep working. Encryption, masking, the SSRF guard, every Connect flow, and
   Paid/Organic Marketing.
5. No DDL, no new settings.

## Acceptance criteria (live DB, rolled back, real Super admin + real company owner)

- A company owner gets 403 on `PUT /integrations/shopify` and `DELETE /integrations/smtp`.
  `POST /integrations/{p}/test` still works. `PUT /integrations/facebook` is still 409.
  `GET /integrations/catalog` shows `admin_keys` true for exactly the eight key providers.
- The Super admin can save (and then test and delete) a key provider for that company through
  `/platform/companies/{id}/integrations/...`. The company's `GET /integrations` then shows it with masked
  values only. The audit row is in the company's log with the Super admin as actor.
- A company owner calling `/platform/companies/...` gets 404. An unknown tenant id gets 404, and a
  connect-only provider gets 422.
- The Super admin's own `PUT /integrations/{key provider}` still works.

## Files

`app/services/integration_service.py`, `app/schemas/integration.py`, `app/api/v1/integrations.py`,
`app/api/v1/platform.py`.
