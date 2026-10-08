/** Paid Marketing lists across campaigns (SPEC-BE-079), mirroring app/schemas/paid.py. */
import type { RangeKey } from "./analytics";

export type PaidPlatform = "meta" | "tiktok" | "google" | "youtube" | "linkedin" | "x" | "snapchat" | "pinterest" | "wizard";

export interface PaidResults {
  spend: number | null;
  impressions: number | null;
  clicks: number | null;
  ctr: number | null;
  /** "ad": Meta per-ad results; "campaign": the platform reports per campaign only; null: wizard rows. */
  results_level: "ad" | "campaign" | null;
}

export interface AdSetItem extends PaidResults {
  id: string;
  name: string;
  campaign_id: string;
  campaign_name: string;
  platform: PaidPlatform;
  status: string;
  effective_status: string | null;
  last_error: string | null;
  budget: number | null;
  budget_type: "daily" | "lifetime" | "campaign" | null;
  currency: string;
  starts_at: string | null;
  ends_at: string | null;
  performance_goal: string | null;
  ads_count: number;
}

export interface AdItem extends PaidResults {
  id: string;
  name: string;
  ad_set_id: string;
  ad_set_name: string;
  campaign_id: string;
  campaign_name: string;
  platform: PaidPlatform;
  status: string;
  effective_status: string | null;
  review_feedback: string | null;
  last_error: string | null;
  headline: string | null;
  text: string | null;
  call_to_action: string | null;
  destination_url: string | null;
  thumbnail_url: string | null;
  external_id: string | null;
  currency: string;
}

export interface PaidList<T> {
  count: number;
  items: T[];
}

export interface PaidStatusResult {
  id: string;
  name: string;
  level: string;
  status: string;
}

export interface PaidListQuery {
  platform?: string;
  status?: string;
  campaign_id?: string;
  ad_set_id?: string;
  q?: string;
  range: RangeKey;
  page: number;
  page_size: number;
}

export const PAID_PLATFORM_LABEL: Record<PaidPlatform, string> = {
  meta: "Meta",
  tiktok: "TikTok",
  google: "Google Ads",
  youtube: "YouTube",
  linkedin: "LinkedIn",
  x: "X",
  snapchat: "Snapchat",
  pinterest: "Pinterest",
  wizard: "Wizard (internal)",
};
