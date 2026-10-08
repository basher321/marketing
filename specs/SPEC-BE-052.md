# SPEC-BE-052: Integrations — connect, manage, test, disconnect (keys entered in the app)

Status: IMPLEMENTED (2026-09-30), plan approved by the user; verified on live Postgres (rolled-back txn) with every provider HTTP call answered by httpx.MockTransport (no real third-party call).

Implementation notes:
- The live `credentials_ref` is varchar(255) NOT NULL, too short for the encrypted blob. The blob is stored in `settings.secrets_enc`, and `credentials_ref` holds the reference "app:settings.secrets_enc" ("" once disconnected).
- User-supplied hosts (Shopify domain, WooCommerce site, Salesforce instance, SMTP host) must be public: https only, no localhost or private/loopback/link-local IPs (server-side request forgery guard). The Zoho data-center value is allow-listed.

## Purpose
Make every integration card work from the UI (SPEC-FE-037). Users paste their own credentials in the app, never in `.env`. This follows the standard "API key / access token" connection pattern (Zapier, Make, n8n). A full OAuth "Login with Facebook" redirect needs a registered developer app per platform (app id and secret, review, redirect URL), so it is out of scope. Pasted tokens (e.g. a Meta System-User token) are the supported path.

## Provider catalog (backend-served, drives the forms)
`GET /api/v1/integrations/catalog` returns `[{provider, label, category, fields:[{key,label,secret,required,help}], test: bool, docs_url}]` for the live `integration_provider` values:

| Category | Provider → fields (secret fields marked *) | Test call |
|---|---|---|
| Ads | meta_ads: access_token*, ad_account_id | GET graph.facebook.com/me + /act_{id} |
| | tiktok_ads: access_token*, advertiser_id | TikTok Business API advertiser/info |
| | google_ads: developer_token*, client_id, client_secret*, refresh_token*, customer_id | OAuth token refresh (validates the credentials) |
| Social | facebook / instagram: page or IG account id, access_token* | Graph GET /{id} |
| | tiktok: access_token* | user/info |
| Messaging | whatsapp: phone_number_id, access_token* | Graph GET /{phone_number_id} |
| Email | smtp: host, port, username, password*, from_email, use_tls | SMTP connect + login |
| | sendgrid: api_key*, from_email | GET /v3/scopes |
| Commerce | shopify: shop_domain, admin_token* | GET /admin/api/2024-07/shop.json |
| | woocommerce: site_url, consumer_key*, consumer_secret* | GET /wp-json/wc/v3/system_status |
| CRM | hubspot: private_app_token* | GET /crm/v3/objects/contacts?limit=1 |
| | zoho: client_id, client_secret*, refresh_token*, dc | OAuth token refresh |
| | salesforce: instance_url, client_id, client_secret*, refresh_token* | OAuth token refresh |

## Contract
- `GET /api/v1/integrations`: existing fields, plus `{configured_fields: [key], masked: {key: "••••1a2b"}, last_error, verified_at}`. **Secrets are never returned.**
- `PUT /api/v1/integrations/{provider}` (manager+): `{account_name?, fields:{...}}` saves the credentials encrypted and then runs the test. Response `{status, last_error, verified_at}`. `connected` if the test passes, `error` with the provider's message if it fails. A secret field sent empty keeps the stored value.
- `POST /api/v1/integrations/{provider}/test` (manager+) re-runs the test.
- `DELETE /api/v1/integrations/{provider}` (manager+): status `disconnected`, credentials wiped, and the row kept for history.

## Functional rules
1. Credentials are stored as a Fernet-encrypted JSON blob (`utils/crypto.encrypt_secret`, keyed by `ENCRYPTION_KEY`) in `integrations.credentials_ref`. Non-secret fields are stored in `settings`.
2. Test calls use `httpx` (already installed), with a 10-second timeout, and never log secrets. The provider's error text is shortened to 300 characters.
3. One row per (tenant, provider). Everything is tenant-scoped and audited (`integration.connect`/`test`/`disconnect`, with no secrets in the metadata).
4. **Honest limit:** saving and verifying credentials does not yet make campaigns publish to those platforms. The publishing adapters remain a later spec, and the UI says so.

## Acceptance criteria
1. Save → the credentials are encrypted in the DB (no plaintext), masked in GET, and the status is set from the test result (a bad token → `error` with a message).
2. Disconnect wipes the credentials. Viewer gets 403. Another tenant is isolated.
3. Tests run against a local stub HTTP server (never real third-party APIs), plus one real-network sanity check only if you supply a test key.

## Target files
- backend/app/models/integration.py, schemas/integration.py, services/integration_service.py, api/v1/integrations.py
- backend/app/integrations/verify.py (new: per-provider test calls)
