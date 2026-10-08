/**
 * Campaign Wizard types (SPEC-FE-030), mirroring backend app/schemas/campaign.py
 * (CampaignDetail / CampaignDraftCreate / CampaignDraftUpdate, SPEC-BE-044/047)
 * and app/schemas/audience.py (SPEC-BE-045) field for field.
 */
import type { CampaignObjective } from "./content";

export type WizardStep = "audience" | "creative" | "budget" | "channels";

export interface ApprovalPreview {
  required: boolean;
  /** e.g. "daily spend 285714 > cap 5000 (BDT cents)". */
  reason: string;
}

export interface CampaignDetail {
  id: string;
  name: string;
  objective: CampaignObjective;
  description: string | null;
  /** Live campaign_status: draft, scheduled, running, paused, completed, failed. */
  status: string;
  channels: string[];
  currency: string;
  /** Major units. */
  total_budget: number;
  /** Major units, derived: total / duration_days. */
  daily_budget: number;
  duration_days: number | null;
  /** ISO 8601 UTC. */
  starts_at: string | null;
  ends_at: string | null;
  audience_id: string | null;
  creative_asset_id: string | null;
  /** Launch-rule preview; null until budget + schedule are set. */
  approval: ApprovalPreview | null;
  pending_approval_id: string | null;
  /** Incomplete steps, in order. Empty = ready to launch. */
  missing: WizardStep[];
  created_at: string;
  updated_at: string;
  launched_at: string | null;
  /** Created in the Ads Manager-style builder (SPEC-BE-055). */
  builder?: boolean;
}

export interface CampaignDraftCreate {
  name: string;
  objective: CampaignObjective;
  description: string | null;
}

/** Only the fields sent are changed; audience_id / creative_asset_id may be null to clear. */
export interface CampaignDraftUpdate {
  name?: string;
  objective?: CampaignObjective;
  description?: string | null;
  audience_id?: string | null;
  creative_asset_id?: string | null;
  total_budget?: number;
  starts_at?: string;
  ends_at?: string;
  channels?: string[];
}

export interface AudienceTargeting {
  countries: string[];
  regions: string[];
  age_min: number;
  age_max: number;
  /** Empty = all genders. */
  genders: ("male" | "female")[];
  interests: string[];
  languages: string[];
}

export interface Audience {
  id: string;
  name: string;
  description: string | null;
  targeting: AudienceTargeting;
  /** Always null: no ad-platform data to estimate reach. */
  estimated_size: number | null;
  created_at: string;
}

export interface AudienceList {
  count: number;
  items: Audience[];
}

export interface AudienceCreate {
  name: string;
  description: string | null;
  targeting: AudienceTargeting;
}
