# SPEC-BE-072: Worldwide company settings: every country, currency, language and timezone

Status: IMPLEMENTED and verified 2026-10-02 (approved by the user; decisions 1a Babel, 2a sign-up detection, 3a AI language in a separate spec). See the Execution log. Frontend counterpart: SPEC-FE-048.

## Why
The user asked for Settings → Company to work "from anywhere in the world": every currency, every country code and every time zone.

## Findings (current code, 2026-10-02)
| # | Finding |
|---|---|
| W1 | `PATCH /tenants/me` accepts **any** 3 letters as a currency ("ABC") and **any** 2 letters as a country ("ZZ"). Only the timezone is really validated (`zoneinfo`). |
| W2 | There is no list of valid countries, currencies or languages anywhere in the backend. The frontend hardcodes 10 currencies and 5 languages, and the country is a free-text box. |
| W3 | `tzdata` is installed but not in `requirements.txt`. On a fresh Windows install (no system tz database), every timezone, including "Asia/Dhaka", would be refused, and per-day reports would fail. |
| W4 | Backend text that shows money (approval summaries, AI grounding, campaign `_money`) always prints 2 decimals ("1,500.00 JPY"). It should follow the currency: JPY/KRW/VND have 0 decimals. |
| W5 | Sign-up always creates the company with USD + UTC (the database defaults), wherever the user is. |
| W6 | `meta_ads.LANGUAGE_NAMES` knows only 21 languages for Meta's locale search; any other language is searched as typed (by code, which Meta doesn't match). |
| W7 | `default_language` is stored but not used by any backend code (the AI replies don't read it). **Out of scope here**; see open decision 3. |

**Kept as is (documented):** money is stored as `amount × 100` in the `*_cents` columns for **every** currency.
- This already works worldwide: the adapters convert (Meta's offset-1 currencies, micros for Google/X/Snapchat/Pinterest).
- A JPY price of ¥1,500 is stored as 150000.
- The 3-decimal currencies (KWD, BHD, OMR, JOD, TND, LYD, IQD) keep 2-decimal precision (0.01).
- Moving to true ISO minor units would mean migrating every money column and every adapter, for no visible benefit.

## Changes
1. **W1/W2: new reference data, `app/utils/locale_data.py`** (new file). It is built once at import from **Babel** (CLDR data, new dependency `babel`) and `pytz.country_timezones` (pytz is already a dependency).
   - **Countries:** every ISO 3166-1 alpha-2 code with its English name (about 250). Babel's non-country regions ("001", "EU", "ZZ", "QO"…) are excluded.
   - **Currencies:** every currency in current use in at least one country (CLDR territory currencies, today's date), with its English name, symbol and number of decimals (0 for JPY, 3 for KWD…). Historic currencies (DEM, FRF…) are excluded. About 155.
   - **Languages:** ISO 639-1 two-letter codes with English and native names (about 180). A regional tag such as `en-US` is still accepted when its base language is valid.
   - **Timezones:** `zoneinfo.available_timezones()` (IANA, about 600), minus the legacy aliases (`Etc/GMT+5`, `US/Eastern`, `SystemV/…`), with "UTC" kept. Each has its current UTC offset.
   - **Suggestions per country:** a default currency (CLDR) and the country's timezones (pytz).
   - **`format_money(cents, currency)`:** "৳1,850", "$1,850.00", "¥1,500", "KWD 1.850", using the currency's decimals.
2. **`GET /tenants/locale-options`** (any signed-in user, `response_model`, 200) returns `{countries:[{code,name,currency,timezones}], currencies:[{code,name,symbol,decimals}], languages:[{code,name,native_name}], timezones:[{name,offset}]}`.
   - It is static data, so the response is cached in memory, and the route sends `Cache-Control: private, max-age=86400`.
   - Files: `app/api/v1/tenants.py`, `app/schemas/tenant.py`.
3. **W1 validation in `TenantUpdate`** (`app/schemas/tenant.py`):
   - `country_code` must be in the country list ("Unknown country code: ZZ"), and `currency` in the currency list ("Unknown currency: ABC").
   - `default_language` must be a known language, with an optional region.
   - Timezone: as now, plus the legacy aliases are refused with a suggestion ("Use America/New_York instead of US/Eastern").
   - **Existing stored values stay valid when read.** `TenantRead` isn't changed, so a company that already has an unusual value still loads; only new saves are checked.
4. **W3:** `tzdata` is pinned in `requirements.txt` (SPEC-BE-001 note updated).
5. **W4:** `format_money` replaces the hand-written 2-decimal formatting in:
   - `services/campaign_service._money`, `services/meta_builder_service` (`_money`, publish approval summary);
   - `services/ads_builder_service` (publish approval summary);
   - `ai/retrieval._money`.

   **API numbers don't change:** amounts stay `float` in major units, plus `currency`. Only human-readable text changes.
6. **W5 sign-up:** `RegisterRequest` gets optional `timezone` and `country_code`, validated as in item 3.
   - The sign-up page sends the browser's timezone, and its region when known (SPEC-FE-048).
   - With a valid country and no currency chosen, the company's currency is set to that country's currency. Otherwise the database defaults apply as before.
   - Files: `app/schemas/auth.py`, `app/services/auth_service.py`, `app/services/tenant_service.create_tenant`.
7. **W6 `integrations/meta_ads.py`:** the language → English-name lookup for Meta's locale search uses Babel's English names for **all** languages (the 21-entry dict is removed).
8. **Changing the currency doesn't convert anything.** Products, orders and campaigns keep their own `currency` column; only new records use the new company currency. The settings page says so before saving (SPEC-FE-048). The backend doesn't block the change.

## Open decisions (recommendation first)
1. **Data source:**
   - **(a) Babel (recommended):** CLDR is the same data browsers use, so names and decimals match the frontend's `Intl`; about 10 MB, pure Python.
   - **(b) No new dependency:** hand-typed lists in `locale_data.py` (about 600 lines that would have to be kept current by hand).
2. **Sign-up detection (W5):**
   - **(a) Yes (recommended):** timezone and country from the browser, currency derived from the country.
   - **(b) No:** keep USD/UTC and let the user change it in Settings.
3. **AI reply language (W7):**
   - **(a) Separate spec (recommended):** using `default_language` in AI reply drafts and ad copy changes AI behaviour and needs its own review.
   - **(b) Include now.**

## Acceptance (live DB, rolled-back transaction)
1. `GET /tenants/locale-options` returns:
   - ≥ 245 countries (BD, US, JP, DE, BR, NG, AE, AU…), each with a currency and ≥ 1 timezone where the country has one;
   - ≥ 150 currencies, with JPY 0 decimals, USD 2 and KWD 3, and no DEM;
   - ≥ 150 languages, and ≥ 400 timezones, including UTC and excluding `US/Eastern`.
2. `PATCH /tenants/me`:
   - accepts JP/JPY/Asia/Tokyo/ja, US/USD/America/New_York/en-US, NG/NGN/Africa/Lagos/yo, BR/BRL/America/Sao_Paulo/pt-BR and KW/KWD/Asia/Kuwait/ar;
   - refuses ZZ, ABC, DEM, US/Eastern and "xx" with 422 and a clear message.
3. Register with the timezone Europe/Berlin and the country DE creates a company with EUR / Europe/Berlin / DE. Without them it gets USD / UTC as before; with an invalid timezone it returns 422.
4. `format_money`: 185000 BDT → "৳1,850"; 185000 USD → "$1,850.00"; 150000 JPY → "¥1,500"; approval summaries use it.
5. A fresh dry-run install of `requirements.txt` includes tzdata and babel; `pip check` is clean.
6. Meta language lookup: "sw" → "Swahili" and "bn" → "Bengali".
7. ruff/mypy show no new errors; dev-shop is unchanged.

## Files
`app/utils/locale_data.py` (**new**), `app/api/v1/tenants.py`, `app/schemas/tenant.py`, `app/schemas/auth.py`, `app/services/auth_service.py`, `app/services/tenant_service.py`, `app/services/campaign_service.py`, `app/services/meta_builder_service.py`, `app/services/ads_builder_service.py`, `app/ai/retrieval.py`, `app/integrations/meta_ads.py`, `requirements.txt`, `specs/SPEC-BE-001.md`.

## Execution log (2026-10-02)

### Files changed (timestamp scan: nothing else in backend/ changed)
| File | Change |
|---|---|
| `app/utils/locale_data.py` | **New.** Countries (250 = 249 ISO + XK), currencies in use (154, with name, symbol and decimals), ISO 639-1 languages (184, with native names) and 418 country timezones + UTC. Also `locale_options()`, `is_*()`, `language_name()`, `TIMEZONE_ALIASES` + `canonical_timezone()` and `format_money()`. Built on first use (~0.5 s), then cached. |
| `app/schemas/tenant.py` | `TenantUpdate` validates country, currency, language and timezone against those lists; an old zone name gets an exact hint ("US/Eastern … use America/New_York instead"). New `check_country`/`check_timezone` and the `LocaleOptions` response models. The unused `re` import was removed. |
| `app/api/v1/tenants.py` | New `GET /tenants/locale-options` (signed-in, `Cache-Control: private, max-age=86400`). |
| `app/schemas/auth.py`, `services/auth_service.py`, `services/tenant_service.py` | Sign-up accepts optional detected `timezone`/`country_code`; `create_tenant` sets the country, the country's currency and the timezone. |
| `services/campaign_service.py`, `meta_builder_service.py`, `ads_builder_service.py`, `ai/retrieval.py` | Money in text (launch/publish approval summaries, AI grounding prices) uses `format_money`. API numbers are unchanged. |
| `integrations/meta_ads.py`, `services/campaign_service.py` | New `language_label()`: the curated names first, then CLDR's English name for every other language. |
| `requirements.txt`, `specs/SPEC-BE-001.md` | `tzdata==2026.4`, `babel==2.18.0`. |

### Deviations from the approved text
1. **Sign-up never refuses detected values** (instead of 422). Chrome reports old zone names such as `Asia/Calcutta`; a 422 would have blocked every sign-up from India. So:
   - known old names are mapped to the current one (`TIMEZONE_ALIASES`, 28 entries);
   - anything else unusable is dropped, and the defaults (USD/UTC) apply.

   Settings (user input) still returns 422.
2. **`LANGUAGE_NAMES` is kept as overrides** rather than removed. CLDR calls `bn` "Bangla", but Meta's locale search needs "Bengali". CLDR names are used for every other language.
3. **`format_money` always shows the currency's decimals** ("৳1,850.00", "¥1,500", "KWD 1,850.000"). The acceptance example "৳1,850" was wrong, because BDT has 2 decimals. The frontend drops the zeros on whole amounts.
4. **Changed but not listed in the spec's files:** `campaign_service.py` for the language lookup (it already held `_money`).

### Results (live DB, one rolled-back transaction): 33 of 33 pass
- **Acceptance 1:** passes.
  - 250 countries (BD→BDT, JP→JPY, DE→EUR; BD → [Asia/Dhaka]).
  - 154 currencies (JPY 0, USD 2, KWD 3; no DEM), and 184 languages (bn → বাংলা).
  - 418 timezones (UTC included; US/Eastern excluded; Dhaka +06:00).
  - The cache header is set, and the endpoint returns 401 without a token.
- **Acceptance 2:** passes.
  - Accepted: JP/JPY/Asia/Tokyo/ja, US/USD/America/New_York/en-US, NG/NGN/Africa/Lagos/yo, BR/BRL/America/Sao_Paulo/pt-BR, KW/KWD/Asia/Kuwait/ar, CN/CNY/Asia/Shanghai/zh-Hant, MX/MXN/America/Mexico_City/es-419, and the lower-case bd/bdt.
  - Refused with 422 and the message: ZZ, EU, ABC, DEM, US/Eastern (with the hint), Mars/Olympus and xx.
- **Acceptance 3:** passes.
  - DE + Europe/Berlin → EUR/Europe/Berlin/DE; nothing detected → USD/UTC.
  - Unusable values → 201 with the defaults; Asia/Calcutta + "in" → INR/Asia/Kolkata/IN; a timezone alone → USD + Asia/Tokyo.
- **Acceptance 4:** passes. `format_money` gives ৳1,850.00 / $1,850.00 / ¥1,500 / KWD 1,850.000, and `campaign_service._money` and `retrieval._money` use it.
- **Acceptance 5:** passes. A fresh dry-run install includes babel and tzdata, and `pip check` is clean.
- **Acceptance 6:** passes. sw → Swahili, bn → Bengali, yo → Yoruba.
- **Acceptance 7:** passes.
  - ruff 1 and mypy 7, the same baseline. pytz has no type stubs, so its import carries `# type: ignore[import-untyped]`.
  - dev-shop loads and saves its own values, and is unchanged after the rollback.
