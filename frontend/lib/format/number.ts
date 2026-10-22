/**
 * Number display rule for the whole app: a whole number shows no decimals
 * ("1,850", "0"), and any number with a fraction shows exactly two digits
 * after the point ("3.80", "12.35", "0.05"). Comma-grouped with "en" like
 * money (lib/format/money.ts). A value that rounds to a whole number at two
 * places ("2.999") shows as whole ("3").
 */
export function formatNumber(value: number): string {
  const rounded = Math.round(value * 100) / 100;
  const whole = Number.isInteger(rounded);
  return rounded.toLocaleString("en-US", {
    minimumFractionDigits: whole ? 0 : 2,
    maximumFractionDigits: whole ? 0 : 2,
  });
}

/** formatNumber + "%" ("12.50%", "3%"). */
export function formatPercent(value: number): string {
  return `${formatNumber(value)}%`;
}
