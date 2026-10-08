# SPEC-FE-048: Worldwide company settings and money display

Status: IMPLEMENTED and verified 2026-10-02 (approved by the user, with SPEC-BE-072 decisions 1a, 2a, 3a). See the Execution log. Backend: SPEC-BE-072.

## Findings
| # | Finding |
|---|---|
| U1 | `components/settings/company-form.tsx` offers 10 hardcoded currencies and 5 languages. Country is a free-text 2-letter box (anything can be typed). Timezone is a plain text box with a suggestion list. |
| U2 | Money is hardcoded to "৳" (22 places in 12 files) or shown as "1850 USD". A company in Japan, the US or Europe would see "৳" or awkward amounts, and JPY would show ".00". |
| U3 | Sign-up doesn't send the user's timezone or country, so every new company starts on USD/UTC. |

## Changes
1. **U1 `company-form.tsx`**, with options from `GET /tenants/locale-options` (new `lib/api/tenant.ts` function + `lib/types/tenant.ts` types).
   Each field below is a searchable select: type to filter.
   - **Country:** "Bangladesh (BD)"…, every country.
     Picking a new country fills in its currency and, when it has one timezone, that timezone. The user can still change both; a country with several timezones (US, RU, BR, AU…) narrows the timezone list to that country's first, with "Show all" available.
   - **Currency:** "BDT — Bangladeshi Taka (৳)", every currency in use.
   - **Timezone:** "(UTC+06:00) Asia/Dhaka", every IANA zone, sorted by offset.
   - **Default language:** "Bangla — বাংলা (bn)", every language.

   **Currency-change warning:** when the currency changes on a company that already has data, the form shows "Existing products, orders and campaigns keep their current currency; prices aren't converted. New records will use XXX." The save still works.
   The backend's 422 messages show under the form, as now.
2. **U2 one money formatter** in a new `lib/format/money.ts`:
   - `formatMoney(amount, currency, {whole?})` uses `Intl.NumberFormat("en", {style: "currency", currency, currencyDisplay: "narrowSymbol"})`, so the decimals follow the currency: "৳1,850", "$1,850.00", "¥1,500", "€1,850.00", "KWD 1.850".
   - The 12 files that hardcode "৳" use it, keeping their current whole-number or 2-decimal choices:
     - `app/(app)/campaigns/page.tsx`
     - `components/analytics/ads-report.tsx`, `sales-summary.tsx`, `top-products-table.tsx`
     - `components/campaigns/wizard.tsx`
     - `components/dashboard/format.ts`
     - `components/ecommerce/orders-table.tsx`, `pricing-rules.tsx`, `products-table.tsx`, `shipping-zones.tsx`
     - `components/kb/kb-tabs.tsx`
     - `components/marketing/campaigns-table.tsx`
   - Where a response has no currency (sales summary, top products, dashboard cards), the company currency from `GET /tenants/me` is used. That query is already cached.
   - For BDT nothing changes visually: "৳48,320" stays "৳48,320".
3. **U3 sign-up** (`app/signup/page.tsx`): sends `timezone` from `Intl.DateTimeFormat().resolvedOptions().timeZone` and `country_code` from the browser language's region (e.g. "en-GB" → GB), only when present. Nothing new is shown on the form.

## Acceptance (E2E against the live backend; temporary companies deleted afterwards)
1. Settings → Company lists:
   - ≥ 245 countries, ≥ 150 currencies, ≥ 150 languages and ≥ 400 timezones;
   - search "jap" finds Japan, and "yen" finds JPY.
2. Picking Japan fills JPY + Asia/Tokyo. Save → reload shows JP/JPY/Asia/Tokyo; the currency warning appears when the company has products.
3. After switching a test company to JPY, the dashboard, products, orders and campaigns show "¥" with no decimals. dev-shop (BDT) still shows "৳48,320"-style amounts.
4. Sign-up from a browser set to Europe/Berlin + de-DE creates a company with EUR/Europe/Berlin/DE.
5. `npx tsc --noEmit` passes; all pages render with no console errors.

## Files
`components/settings/company-form.tsx`, `lib/api/tenant.ts`, `lib/types/tenant.ts`, `lib/format/money.ts` (**new**), `app/signup/page.tsx`, and the 12 money files listed in item 2.

## Execution log (2026-10-02)

### Files changed
- **`components/settings/company-form.tsx`:** rewritten fields. Each one is a type-to-search box (an input with the browser's `<datalist>` suggestions) over the full list:
  - Country: "Japan (JP)".
  - Currency: "JPY — Japanese Yen (¥)".
  - Timezone: "(UTC+09:00) Asia/Tokyo", sorted by offset, with the chosen country's zones first.
  - Language: "Bangla — বাংলা (bn)". A regional tag such as en-US can be typed.

  Text that isn't an entry shows "Pick an entry from the list." and disables Save. Picking a country fills in its currency, and its timezone when it has one. The currency-change warning appears whenever the currency differs from the saved one.
- **`lib/api/tenant.ts`, `lib/types/tenant.ts`:** `fetchLocaleOptions()` + `tenantKeys.localeOptions` (`staleTime: Infinity`), and the option types.
- **`lib/format/money.ts` (new):** `formatMoney(amount, currency, {whole})` and `currencyDigits()`.
- **`hooks/use-tenant.ts` (new):** `useCompanyCurrency()`. The frontend CLAUDE.md puts Query hooks in `hooks/`, so the hook isn't in `money.ts`.
- **The 12 money files listed in the spec**, plus **`components/dashboard/summary-cards.tsx`**, which had to pass the currency to the renamed `money()` in `format.ts`. No "৳" literal is left outside comments.
- **`app/signup/page.tsx`, `lib/types/auth.ts`:** the sign-up page sends the detected `timezone` and `country_code`.

### Deviations
- **No "Show all" toggle for timezones:** all zones are always listed, with the country's zones first.
- **Currency warning:** shown on any currency change, without checking first whether the company has data.
- **Two new files** (`hooks/use-tenant.ts`) and **one extra changed file** (`summary-cards.tsx`), as explained above.

### Results
1. **Settings:** passes.
   - The lists hold 250 countries, 154 currencies, 184 languages and 418 timezones.
   - The labels include "Japan (JP)", "JPY — Japanese Yen (¥)", "বাংলা" and "(UTC+06:00) Asia/Dhaka", so typing "jap" or "yen" finds them through the browser's suggestion filter.
2. **Picking Japan:** passes.
   - Picking Japan fills JPY + Asia/Tokyo and shows the warning; Save shows "Saved".
   - After a reload the fields show Japan / JPY / Asia/Tokyo / Japanese.
   - "Narnia" is flagged, and Save is disabled.
3. **Money display:** passes.
   - The JPY company's products show "¥1,500" (no ".00"), and the dashboard revenue is in ¥.
   - dev-shop (BDT) still shows ৳ on the dashboard and products. /marketing, /campaigns, /analytics, /kb and /settings render with no console errors.
4. **Sign-up:** passes. A browser set to Europe/Berlin + de-DE created a company with EUR / Europe/Berlin / DE.
5. **Checks:** passes. `npx tsc --noEmit` is clean; there were no console errors on any page tested.

The headless Edge E2E ran against the user's running backend and frontend on the live DB, using temporary companies that were deleted afterwards. dev-shop is unchanged.

## Fix (2026-10-02, after the user's report: "it shows only bangladesh and its content")
- **Cause:** the fields used the browser's `<datalist>`, which only suggests entries matching the text already in the box. A filled field ("Bangladesh (BD)") therefore offered only Bangladesh, BDT and Asia/Dhaka.
- **Change, `components/settings/company-form.tsx` only:** `LookupField` is now a searchable dropdown (`role="combobox"` + `listbox`).
  - Clicking or focusing the field opens the whole list, with the current choice highlighted and scrolled into view.
  - Typing filters by name or code. Click, or ↑/↓ + Enter, picks an entry; Escape closes.
  - Leaving with text that isn't an entry keeps the previous value. A typed exact code or regional language tag (en-GB) is accepted.
  - The "Pick an entry from the list." message and the disabled-Save state are gone, because an invalid value can no longer be left in a field.
- **Verified (headless Edge, user's running servers, temporary companies deleted), 17 of 17 pass:**
  - Clicking a filled field lists all 250 countries, 154 currencies, 418 timezones and 184 languages, with the current choice highlighted.
  - "jap" filters to Japan; clicking it fills JPY and Asia/Tokyo and closes the list.
  - "euro" + Enter picks EUR; garbage gives "No matches" and keeps the old value; Escape keeps the value; en-GB is accepted.
  - Save works, and a reload shows Japan/EUR/Asia/Tokyo/en-GB. No console errors; `tsc` is clean.
- **Observation, not changed:** the audit log shows dev-shop's timezone was saved as America/Nuuk at 16:24 from the owner's browser session, while the old dropdown was live. It was left for the user to correct.
