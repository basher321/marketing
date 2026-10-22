import { formatNumber } from "@/lib/format/number";

/**
 * Money display for every currency (SPEC-FE-048).
 *
 * `amount` is in major units, as every backend response returns it. The
 * symbol is the currency's narrow symbol from the browser's own CLDR data
 * ("৳", "$", "€", "¥", "₦"), or the ISO code when it has none
 * ("KWD 1,850"). Decimals follow the currency, capped at two (JPY 0, USD 2,
 * KWD 2, the app's number rule in lib/format/number.ts): a whole amount shows
 * none ("৳1,850", "¥1,500"), an amount with a fraction shows exactly two
 * ("$12.50", "KWD 1.25"). `whole` rounds to whole units, for summary cards
 * and charts.
 *
 * Numbers use "en" grouping (1,850) whatever the company's language, like
 * the rest of the app's English UI.
 */
export function formatMoney(
  amount: number,
  currency: string | null | undefined,
  opts: { whole?: boolean } = {},
): string {
  const code = (currency ?? "").trim().toUpperCase();
  const plain = () => (opts.whole ? Math.round(amount).toLocaleString("en-US") : formatNumber(amount));
  if (!code) return plain();
  try {
    const digits = opts.whole ? 0 : Math.min(currencyDigits(code), 2);
    const hasFraction = digits > 0 && Math.round(Math.abs(amount) * 10 ** digits) % 10 ** digits !== 0;
    return new Intl.NumberFormat("en", {
      style: "currency",
      currency: code,
      currencyDisplay: "narrowSymbol",
      minimumFractionDigits: hasFraction ? digits : 0,
      maximumFractionDigits: digits,
    }).format(amount);
  } catch {
    // Not a currency the browser knows: the number and the code as stored.
    return `${plain()} ${code}`;
  }
}

const digitsCache = new Map<string, number>();

/** ISO 4217 minor digits as the browser knows them (JPY 0, USD 2, KWD 3). */
export function currencyDigits(code: string): number {
  const key = code.trim().toUpperCase();
  let digits = digitsCache.get(key);
  if (digits === undefined) {
    digits = new Intl.NumberFormat("en", { style: "currency", currency: key }).resolvedOptions().maximumFractionDigits ?? 2;
    digitsCache.set(key, digits);
  }
  return digits;
}
