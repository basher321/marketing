/**
 * Dashboard types (SPEC-FE-005/006/007), mirroring the backend schemas field
 * for field. Metrics the Dashboard shares with other pages keep their own
 * types (OrderMetrics in types/analytics, CampaignMetrics/ScheduledPostCount in
 * types/marketing, InboxList in types/conversations, WorkflowListItem in
 * types/workflows).
 */

/** GET /api/v1/orders/revenue-24h — backend SPEC-BE-018. */
export interface Revenue24h {
  /** Major units, every order status. */
  revenue_24h: number;
  /** % change vs the previous 24h. */
  revenue_24h_delta_pct: number;
}

/** GET /api/v1/campaigns/ad-spend-24h — backend AdSpend24h (SPEC-BE-019). */
export interface AdSpend24h {
  ad_spend_24h: number;
  currency: string;
  /** The same value as /campaigns/metrics' avg_roas: imported Meta ROAS, null without data (SPEC-BE-056). */
  avg_roas: number | null;
}

/** One GET /api/v1/inventory/low-stock row — backend InventoryRead (SPEC-BE-005). */
export interface LowStockRow {
  id: string;
  variant_id: string;
  location_id: string;
  on_hand: number;
  available: number;
  reorder_point: number;
}

/** GET /api/v1/approvals/pending-counts — per-engine pending approvals (SPEC-BE-020). */
export interface PendingCounts {
  ecommerce: number;
  marketing: number;
}

/** GET /api/v1/conversations/cs-metrics — backend CsMetrics (SPEC-BE-021); null = no data. */
export interface CsMetrics {
  avg_response_seconds: number | null;
  deflection_rate_pct: number | null;
  csat_7d: number | null;
}

/** One GET /api/v1/analytics/activity item — backend ActivityItem (SPEC-BE-022). */
export interface ActivityItem {
  id: string;
  /** ISO 8601 UTC. */
  occurred_at: string;
  kind: "success" | "warning" | "info";
  /** Plain text: the backend carries no emphasis markers. */
  message: string;
}

/** GET /api/v1/analytics/activity — last 24h, most recent first. */
export interface ActivityFeed {
  items: ActivityItem[];
}
