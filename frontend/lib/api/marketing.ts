/**
 * Marketing summary-card API (SPEC-FE-012). The four cards come from three
 * real endpoints: Active Campaigns and Avg. ROAS share one response
 * (SPEC-BE-009 returns both numbers from a single computation), Scheduled Posts
 * and CTR (7d) each have their own.
 *
 * The Active Campaigns table and Content Calendar are backed by SPEC-BE-038
 * (fetchCampaigns / fetchContentCalendar below).
 */
import type {
  AdCtr7d,
  CampaignListItem,
  CampaignMetrics,
  ContentCalendar,
  ScheduledPostCount,
} from "../types/marketing";
import { apiFetch } from "./client";

export const marketingKeys = {
  all: ["marketing"] as const,
  campaignMetrics: ["marketing", "campaign-metrics"] as const,
  scheduledPostCount: ["marketing", "scheduled-post-count"] as const,
  ctr7d: ["marketing", "ctr-7d"] as const,
};

export function fetchCampaignMetrics(): Promise<CampaignMetrics> {
  return apiFetch<CampaignMetrics>("/api/v1/campaigns/metrics");
}

export function fetchScheduledPostCount(): Promise<ScheduledPostCount> {
  return apiFetch<ScheduledPostCount>("/api/v1/scheduled-posts/count");
}

export function fetchCtr7d(): Promise<AdCtr7d> {
  return apiFetch<AdCtr7d>("/api/v1/ads/ctr-7d");
}

// Active Campaigns table + Content Calendar (backend SPEC-BE-038).
export const marketingListKeys = {
  campaigns: ["marketing", "campaigns"] as const,
  calendar: ["marketing", "calendar"] as const,
};

export function fetchCampaigns(): Promise<CampaignListItem[]> {
  return apiFetch<CampaignListItem[]>("/api/v1/campaigns");
}

export function fetchContentCalendar(): Promise<ContentCalendar> {
  return apiFetch<ContentCalendar>("/api/v1/scheduled-posts/calendar");
}

// Pause / resume (backend SPEC-BE-047, SPEC-FE-032): manager+ (403 otherwise);
// 409 when the status doesn't allow it (e.g. "campaign has ended").
export function setCampaignRunning(id: string, action: "pause" | "resume"): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(`/api/v1/campaigns/${encodeURIComponent(id)}/${action}`, { method: "POST" });
}
