// Shared Dashboard formatting helpers (SPEC-FE-005/006/007).

import { formatMoney } from "@/lib/format/money";

/** "৳48,320" (mockup): the company currency's symbol, comma-grouped, no decimals (SPEC-FE-048). */
export function money(value: number, currency: string | null): string {
  return formatMoney(value, currency, { whole: true });
}

/** One decimal without padding ("3.8", "0", "12.4"). */
export function oneDecimal(value: number): string {
  return String(Number(value.toFixed(1)));
}

/** ▲/▼ + the .up/.down class for a signed change; flat (0) gets no arrow. */
export function trend(delta: number): { arrow: string; className: string } {
  if (delta > 0) return { arrow: "▲ ", className: "card-delta up" };
  if (delta < 0) return { arrow: "▼ ", className: "card-delta down" };
  return { arrow: "", className: "card-delta" };
}
