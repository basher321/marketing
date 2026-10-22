/**
 * Analytics Sales-tab types (SPEC-FE-019), mirroring the backend Pydantic
 * schemas field for field. Money values are floats in major units; the
 * backend returns no currency with them.
 */

/** One day of backend DailyRevenue (app/schemas/analytics.py). */
export interface DailyRevenue {
  /** ISO date "YYYY-MM-DD" — a UTC calendar day. */
  date: string;
  revenue: number;
}

/** GET /api/v1/analytics/sales — backend SalesSummary (SPEC-BE-015). */
export interface SalesSummary {
  revenue_7d: number;
  /** % change vs the previous 7 days. */
  revenue_7d_delta_pct: number;
  orders_7d: number;
  /** revenue_7d / orders_7d; 0 when there are no orders. No comparison value exists. */
  aov_7d: number;
  refund_rate_7d_pct: number;
  /** Change vs the previous 7 days, in percentage points. */
  refund_rate_7d_delta_pp: number;
  /** Exactly 7 entries: today (UTC) and the 6 days before it, oldest -> newest, zero-filled. */
  revenue_by_day: DailyRevenue[];
}

/**
 * One row of GET /api/v1/analytics/top-products — backend TopProduct
 * (SPEC-BE-016). The backend returns at most 10 rows, ordered by 7-day revenue
 * desc (then units, title, id); only products with a sale in the last 7 days.
 */
export interface TopProduct {
  product_id: string;
  /** products.title */
  product: string;
  /** Units sold in the last 7 days (qualifying order statuses only). */
  units_sold: number;
  /** 7-day revenue in major units; no currency is returned. */
  revenue: number;
  /**
   * Signed % change of 7-day revenue vs the previous 7 days, 1 decimal; the
   * sign is the direction. No revenue in the previous week -> 100.0; none in
   * either -> 0.0.
   */
  trend_pct: number;
}

/**
 * GET /api/v1/orders/metrics — backend OrderMetrics (SPEC-BE-006). Used for the
 * Orders (7d) card because it is the only response carrying that card's
 * comparison value; SalesSummary.orders_7d is computed by the same function.
 */
export interface OrderMetrics {
  total: number;
  last_24h: number;
  last_7d: number;
  /** % change vs the previous 7 days. */
  last_7d_delta_pct: number;
}

// ---- Ads / Engagement / Customer Service tabs (SPEC-FE-035, backend SPEC-BE-050).
// A null metric has no source data yet; the UI shows "—" with missing_reason.
// Never estimated. Dates are "YYYY-MM-DD" calendar days in the tenant timezone,
// oldest -> newest, every day present (zero-filled).

export type RangeKey = "7d" | "30d" | "90d";

export interface AdsTotals {
  /** Spend in the window (major units), every campaign incl. completed ones. */
  spend: number;
  /** Campaigns with status "running". */
  active_campaigns: number;
  /** Sum of the listed campaigns' budgets. */
  budget_total: number;
  /** Lifetime spend of the listed campaigns / budget_total, %. Null without budget. */
  budget_used_pct: number | null;
  impressions: number | null;
  clicks: number | null;
  ctr: number | null;
  roas: number | null;
  /** Imported Meta results (SPEC-BE-056); null when Meta reported none. */
  reach?: number | null;
  conversions?: number | null;
  missing_reason: string;
  /** "meta" when imported Meta results exist in the window. */
  source?: string | null;
}

export interface DailySpend {
  date: string;
  spend: number;
  impressions?: number | null;
  clicks?: number | null;
  ctr?: number | null;
  roas?: number | null;
}

export interface AdsCampaignRow {
  id: string;
  name: string;
  status: string;
  channels: string[];
  budget: number;
  /** Spend in the window. */
  spend: number;
  /** Lifetime spend / (budget x elapsed share of the schedule), %. Null without dates/budget. */
  pacing_pct: number | null;
  starts_at: string | null;
  ends_at: string | null;
}

/** GET /api/v1/analytics/ads?range= */
export interface AdsReport {
  currency: string;
  range: RangeKey;
  totals: AdsTotals;
  spend_by_day: DailySpend[];
  /** Running, scheduled and paused campaigns only. */
  campaigns: AdsCampaignRow[];
}

export interface PostCounts {
  /** Published in the window. */
  published: number;
  /** Current pipeline (any date). */
  scheduled: number;
  pending: number;
  /** Failed in the window. */
  failed: number;
}

export interface PostsByChannel {
  channel: string;
  published: number;
  /** Scheduled + pending. */
  scheduled: number;
}

export interface PostsByDay {
  date: string;
  published: number;
  scheduled: number;
}

export interface ContentPipeline {
  draft: number;
  pending_approval: number;
  approved: number;
  published: number;
}

/** GET /api/v1/analytics/engagement?range= */
export interface EngagementReport {
  range: RangeKey;
  posts: PostCounts;
  posts_by_channel: PostsByChannel[];
  /** The window plus the next 7 days (today is the 8th entry from the end). */
  posts_by_day: PostsByDay[];
  content: ContentPipeline;
  likes: number | null;
  comments: number | null;
  shares: number | null;
  reach: number | null;
  missing_reason: string;
}

export interface ConversationCounts {
  total: number;
  open: number;
  pending: number;
  resolved: number;
  /** Handed off to a human (metadata.handed_off_at set). */
  escalated: number;
}

export interface ConversationsByChannel {
  channel: string;
  total: number;
  resolved: number;
}

export interface ConversationsByDay {
  date: string;
  new: number;
  resolved: number;
}

export interface ReplyCounts {
  ai: number;
  agent: number;
  ai_share_pct: number | null;
}

/** GET /api/v1/analytics/customer-service?range= */
export interface ServiceReport {
  range: RangeKey;
  conversations: ConversationCounts;
  by_channel: ConversationsByChannel[];
  by_day: ConversationsByDay[];
  first_response_minutes_avg: number | null;
  resolution_hours_avg: number | null;
  csat_avg: number | null;
  csat_responses: number;
  replies: ReplyCounts;
  deflection_pct: number | null;
}

// ---- Profit & loss (SPEC-FE-074 / SPEC-BE-110) --------------------------------
export type PLRange = "7d" | "30d" | "90d" | "mtd" | "ytd";

export interface ProfitLoss {
  currency: string;
  period: { from: string; to: string };
  previous_period: { from: string; to: string };
  revenue: { sales: number; shipping_charged: number; net: number; order_count: number };
  not_sales: Record<string, { count: number; value: number }>;
  costs: {
    product: number;
    ad_spend: {
      total: number;
      by_platform: { platform: string; amount: number }[];
      unavailable: { platform: string; reason: string }[];
      excluded_currency: { platform: string; currency: string; amount: number }[];
    };
    shipping: number;
    operating: number;
    other: number;
    total: number;
  };
  profit: number;
  /** Percent; null when there is no revenue. */
  margin: number | null;
  /** False when some order lines have no product cost, or some ad spend is unavailable. */
  complete: boolean;
  missing_cost: { lines: number; revenue: number };
  previous: { net_revenue: number; costs_total: number; profit: number };
  /** Change vs the previous period in percent; null when there is nothing to compare with. */
  delta_pct: { revenue: number | null; profit: number | null };
  by_day: { date: string; net_revenue: number; costs: number; profit: number }[];
  by_product: { sku: string | null; title: string | null; units: number; revenue: number; cost: number | null }[];
  rules: string[];
}
