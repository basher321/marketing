/**
 * Dashboard API (SPEC-FE-005/006/007): only the endpoints no other page uses.
 * Shared metrics reuse their owning module's function AND query key, so one
 * value is fetched once and cached once:
 *   Orders / Orders (24h)          -> analytics.fetchOrderMetrics  (analyticsKeys.orderMetrics)
 *   Active campaigns               -> marketing.fetchCampaignMetrics (marketingKeys.campaignMetrics)
 *   Scheduled posts                -> marketing.fetchScheduledPostCount
 *   Open Conversations / threads   -> conversations.fetchConversations (conversationKeys.list)
 *   Active workflows               -> workflows.fetchWorkflows (workflowKeys)
 */
import type {
  ActivityFeed,
  AdSpend24h,
  CsMetrics,
  LowStockRow,
  PendingCounts,
  Revenue24h,
} from "../types/dashboard";
import { apiFetch } from "./client";

export const dashboardKeys = {
  revenue24h: ["dashboard", "revenue-24h"] as const,
  adSpend24h: ["dashboard", "ad-spend-24h"] as const,
  lowStock: ["dashboard", "low-stock"] as const,
  pendingCounts: ["dashboard", "pending-counts"] as const,
  csMetrics: ["dashboard", "cs-metrics"] as const,
  activity: ["dashboard", "activity"] as const,
};

export function fetchRevenueSummary(): Promise<Revenue24h> {
  return apiFetch<Revenue24h>("/api/v1/orders/revenue-24h");
}

export function fetchAdSpendSummary(): Promise<AdSpend24h> {
  return apiFetch<AdSpend24h>("/api/v1/campaigns/ad-spend-24h");
}

export function fetchLowStock(): Promise<LowStockRow[]> {
  return apiFetch<LowStockRow[]>("/api/v1/inventory/low-stock");
}

export function fetchPendingCounts(): Promise<PendingCounts> {
  return apiFetch<PendingCounts>("/api/v1/approvals/pending-counts");
}

export function fetchCsMetrics(): Promise<CsMetrics> {
  return apiFetch<CsMetrics>("/api/v1/conversations/cs-metrics");
}

export function fetchRecentActivity(): Promise<ActivityFeed> {
  return apiFetch<ActivityFeed>("/api/v1/analytics/activity");
}
