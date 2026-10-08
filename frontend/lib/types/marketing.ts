/**
 * Marketing summary-card response types (SPEC-FE-012), mirroring the backend
 * Pydantic schemas field for field.
 */

/** GET /api/v1/campaigns/metrics — backend app/schemas/campaign.py CampaignMetrics (SPEC-BE-009). */
export interface CampaignMetrics {
  /** Campaigns with campaign_status 'running' for the caller's tenant. */
  active_campaigns: number;
  /** Backend placeholder: always 0.0 until ad-metrics ingestion exists (no revenue data). */
  /** Null when no Meta purchase value was imported (SPEC-BE-056). */
  avg_roas: number | null;
}

/** GET /api/v1/scheduled-posts/count — backend app/schemas/scheduled_post.py ScheduledPostCount (SPEC-BE-010). */
export interface ScheduledPostCount {
  /** Posts with post_status 'pending' or 'scheduled'. */
  pending: number;
}

/** GET /api/v1/ads/ctr-7d — backend app/schemas/campaign.py AdCtr7d (SPEC-BE-011). */
export interface AdCtr7d {
  /** Percentage. Backend placeholder: always 0.0 (no click/impression data exists yet). */
  /** Null when no impressions were imported in the last 7 days (SPEC-BE-056). */
  ctr_7d_pct: number | null;
}

/** One GET /api/v1/campaigns row — backend CampaignListItem (SPEC-BE-038). */
export interface CampaignListItem {
  id: string;
  name: string;
  /** Live campaign_objective, e.g. "conversions". */
  objective: string;
  /** Live channel_type values. */
  channels: string[];
  /** Major units. */
  budget: number;
  currency: string;
  /** Days from start to end; null when either date is unset. */
  duration_days: number | null;
  /** Lifetime ROAS from imported Meta results; null without data (SPEC-BE-056). */
  roas: number | null;
  /** Live campaign_status: running | scheduled | paused. */
  status: string;
  /** Major units imported from Meta (SPEC-BE-056). */
  spent: number;
  /** Opens in the Ads Manager-style builder (SPEC-BE-055). */
  builder: boolean;
  /** Meta's own effective_status, when published. */
  effective_status: string | null;
}

/** GET /api/v1/scheduled-posts/calendar — backend ContentCalendar (SPEC-BE-038). */
export interface ContentCalendar {
  /** Tenant-local Monday, ISO date. */
  week_start: string;
  timezone: string;
  /** Always 7 days, Monday -> Sunday. */
  days: {
    date: string;
    posts: { id: string; channel: string; format: string; status: string; scheduled_at: string }[];
  }[];
}
