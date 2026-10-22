/**
 * Analytics Sales-tab API (SPEC-FE-019). The four cards and the Revenue by Day
 * chart come from GET /api/v1/analytics/sales (SPEC-BE-015), except the Orders
 * (7d) card, whose comparison value exists only on GET /api/v1/orders/metrics
 * (SPEC-BE-006). No chart-narration ("Explain this") endpoint exists.
 */
import type {
  AdsReport,
  EngagementReport,
  OrderMetrics,
  PLRange,
  ProfitLoss,
  RangeKey,
  SalesSummary,
  ServiceReport,
  TopProduct,
} from "../types/analytics";
import { apiFetch } from "./client";

export const analyticsKeys = {
  all: ["analytics"] as const,
  sales: ["analytics", "sales"] as const,
  orderMetrics: ["analytics", "order-metrics"] as const,
  topProducts: ["analytics", "top-products"] as const,
  // One cache entry per range, so switching the range fetches that range.
  ads: (range: RangeKey) => ["analytics", "ads", range] as const,
  engagement: (range: RangeKey) => ["analytics", "engagement", range] as const,
  service: (range: RangeKey) => ["analytics", "customer-service", range] as const,
};

// Top Products table (SPEC-FE-020, backed by SPEC-BE-016).
export function fetchTopProducts(): Promise<TopProduct[]> {
  return apiFetch<TopProduct[]>("/api/v1/analytics/top-products");
}

export function fetchSalesSummary(): Promise<SalesSummary> {
  return apiFetch<SalesSummary>("/api/v1/analytics/sales");
}

export function fetchOrderMetrics(): Promise<OrderMetrics> {
  return apiFetch<OrderMetrics>("/api/v1/orders/metrics");
}

// Ads / Engagement / Customer Service tabs (SPEC-FE-035, backend SPEC-BE-050).
export function fetchAdsReport(range: RangeKey): Promise<AdsReport> {
  return apiFetch<AdsReport>(`/api/v1/analytics/ads?range=${range}`);
}

export function fetchEngagementReport(range: RangeKey): Promise<EngagementReport> {
  return apiFetch<EngagementReport>(`/api/v1/analytics/engagement?range=${range}`);
}

export function fetchServiceReport(range: RangeKey): Promise<ServiceReport> {
  return apiFetch<ServiceReport>(`/api/v1/analytics/customer-service?range=${range}`);
}

/** The P&L period: a preset range or a custom from–to (company days, inclusive). */
export type PLQuery = { range: PLRange } | { from: string; to: string };

function plSearch(q: PLQuery): string {
  return "range" in q ? `range=${q.range}` : `from=${q.from}&to=${q.to}`;
}

export const profitLossKey = (q: PLQuery) => ["analytics", "profit-loss", q] as const;

/** GET /analytics/profit-loss (SPEC-BE-110 FR2). */
export function fetchProfitLoss(q: PLQuery): Promise<ProfitLoss> {
  return apiFetch<ProfitLoss>(`/api/v1/analytics/profit-loss?${plSearch(q)}`);
}

/** GET /analytics/profit-loss.csv (FR3), as text for a client-side download. */
export function fetchProfitLossCsv(q: PLQuery): Promise<string> {
  return apiFetch<string>(`/api/v1/analytics/profit-loss.csv?${plSearch(q)}`);
}
