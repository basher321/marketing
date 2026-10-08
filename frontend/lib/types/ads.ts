/** Multi-platform Ad Manager (SPEC-BE-062), mirroring backend/app/schemas/ads_builder.py. */

export type PlatformKey = "meta" | "tiktok" | "google" | "youtube" | "linkedin" | "x" | "snapchat" | "pinterest";
export type BuilderPlatform = Exclude<PlatformKey, "meta">;
export type BudgetMode = "daily" | "total" | "none";
export type Level = "campaign" | "group" | "ad";

export interface PlatformObjective {
  key: string;
  label: string;
  description: string;
  available: boolean;
  reason: string | null;
}

export interface Hierarchy {
  campaign: string;
  group: string;
  ad: string;
}

export interface Platform {
  key: PlatformKey;
  label: string;
  runs_on: string;
  channels: string[];
  hierarchy: Hierarchy;
  connected: boolean;
  account_name: string | null;
  connect_hint: string;
  objectives: PlatformObjective[];
  campaign_types: PlatformObjective[];
  creative: {
    formats?: string[];
    text_limits?: Record<string, number>;
    media?: Record<string, string>;
  };
  /** live: publishes once connected; needs_connection: connect first; not_built: publishing spec not built yet. */
  publishing: "live" | "needs_connection" | "not_built";
}

export interface PlatformList {
  platforms: Platform[];
}

export interface CampaignCreate {
  name: string;
  objective: string;
  campaign_type?: string | null;
}

export interface CampaignFields {
  name?: string;
  objective?: string;
  campaign_type?: string | null;
  budget_mode?: BudgetMode;
  /** Major units of the tenant currency. */
  budget?: string | null;
  starts_at?: string | null;
  ends_at?: string | null;
  fields?: Record<string, unknown>;
}

export interface GroupFields {
  name?: string;
  budget_mode?: BudgetMode;
  budget?: string | null;
  starts_at?: string | null;
  ends_at?: string | null;
  targeting?: Record<string, unknown>;
  fields?: Record<string, unknown>;
}

export interface AdFields {
  name?: string;
  creative?: Record<string, unknown>;
}

export interface Issue {
  level: Level;
  id: string | null;
  path: string;
  message: string;
  severity: "error" | "warning";
}

export interface TreeAd {
  id: string;
  name: string;
  status: string;
  external_id: string | null;
  creative: Record<string, unknown>;
}

export interface TreeGroup {
  id: string;
  name: string;
  status: string;
  external_id: string | null;
  budget_mode: BudgetMode;
  budget: number | null;
  starts_at: string | null;
  ends_at: string | null;
  targeting: Record<string, unknown>;
  fields: Record<string, unknown>;
  ads: TreeAd[];
}

export interface TreeCampaign {
  id: string;
  name: string;
  objective: string;
  objective_label: string;
  campaign_type: string | null;
  status: string;
  currency: string;
  budget_mode: BudgetMode;
  budget: number | null;
  starts_at: string | null;
  ends_at: string | null;
  fields: Record<string, unknown>;
  external_id: string | null;
  last_error: string | null;
  pending_approval_id: string | null;
}

export interface PlatformTree {
  platform: BuilderPlatform;
  label: string;
  hierarchy: Hierarchy;
  campaign: TreeCampaign;
  groups: TreeGroup[];
  issues: Issue[];
  connection: { connected: boolean; account_name: string | null; publishing: "available" | "not_built"; message: string | null };
  approval: { required: boolean; reason: string } | null;
}

export interface ValidateResult {
  ok: boolean;
  issues: Issue[];
}

export interface StatusResult {
  id: string;
  name: string;
  level: Level;
  status: string;
}

export interface LookupItem {
  id: string;
  name: string;
  type: string | null;
  extra: Record<string, unknown>;
}

export interface MediaResult {
  media_id: string;
  kind: "image" | "video";
  name: string;
  thumbnail_url: string | null;
}
