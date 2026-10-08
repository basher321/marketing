/** Zernio paid ads (SPEC-BE-084 / SPEC-FE-055): mirrors backend/app/schemas/zernio.py. */

export type ZPlatform = "facebook" | "instagram" | "tiktok" | "linkedin" | "pinterest" | "twitter" | "googleads";
export type ZRange = "7d" | "30d" | "90d";

export type ZStatus = { configured: boolean; profile_ready: boolean; account_count: number | null };

export type ZAccount = {
  id: string;
  /** Zernio's kind: posting (facebook, instagram, …) or ads (metaads, tiktokads, …). */
  kind: string;
  username: string | null;
  display_name: string | null;
  picture_url: string | null;
  needs_reconnection: boolean;
  parent_account_id: string | null;
};

export type ZGoal = { key: string; label: string };

export type ZPlatformInfo = {
  key: ZPlatform;
  label: string;
  connected: boolean;
  ads_accounts: ZAccount[];
  posting_accounts: ZAccount[];
  goals: ZGoal[];
  ctas: string[];
  media: string[];
  /** Targeting capability names: countries, regions, cities, city_radius, zips, metros, custom_locations,
   * excluded_locations, age, gender, languages, interests, behaviors, income_tier, placements,
   * special_ad_categories, keywords. */
  targeting: string[];
  limits: Record<string, number>;
  bid: boolean;
  bid_strategies: string[];
  validate_supported: boolean;
  preview_supported: boolean;
  campaign_types: string[];
  placements: Record<string, string[]>;
  special_ad_categories: string[];
  income_tiers: string[];
};

export type ZPlatformList = { configured: boolean; platforms: ZPlatformInfo[] };

export type ZConnectResult = { auth_url: string | null; already_connected: boolean; step: "ads" | "posting" };

export type ZCallbackRequest = {
  zs: string;
  connected?: string | null;
  account_id?: string | null;
  error?: string | null;
  error_message?: string | null;
  error_reason?: string | null;
};

export type ZCallbackResult = { platform: string; step: string; connected: boolean; account_id: string | null; message: string };

export type ZAdAccount = {
  id: string;
  name: string | null;
  currency: string | null;
  timezone: string | null;
  status: string | null;
  selectable: boolean;
  unusable_reason: string | null;
  min_daily_budget: number | null;
  business_name: string | null;
};

export type ZIdentityOption = { id: string; name: string | null; kind: string; detail: string | null };

export type ZIdentities = {
  pages: ZIdentityOption[];
  instagram_accounts: ZIdentityOption[];
  tiktok_identities: ZIdentityOption[];
  default_page_id: string | null;
  default_instagram_id: string | null;
};

export type ZSearchHit = {
  id: string;
  name: string;
  type: string | null;
  path: string | null;
  country_code: string | null;
  audience_size: number | null;
};

export type GeoRef = { key: string; name?: string | null };
export type CityRef = GeoRef & { radius?: number | null; distance_unit?: "mile" | "kilometer" | null };
export type CustomLocation = { latitude: number; longitude: number; radius: number; distance_unit: "mile" | "kilometer"; name?: string | null };
export type Entity = { id: string; name: string };

export type ZTargeting = {
  countries: string[];
  regions: GeoRef[];
  cities: CityRef[];
  zips: GeoRef[];
  metros: GeoRef[];
  custom_locations: CustomLocation[];
  excluded: { countries: string[]; regions: GeoRef[]; cities: GeoRef[]; zips: GeoRef[] } | null;
  age_min: number | null;
  age_max: number | null;
  gender: "all" | "male" | "female";
  languages: string[];
  interests: Entity[];
  behaviors: Entity[];
  income_tier: string | null;
};

export type ZReach = { available: boolean; lower: number | null; upper: number | null; daily: number | null };

export type ZBid = { strategy: string; amount?: string | null; roas_floor?: string | null };

export type ZPlacements = Record<string, string[]>;

export type ZCreative = {
  headline?: string | null;
  long_headline?: string | null;
  body?: string | null;
  description?: string | null;
  call_to_action?: string | null;
  link_url?: string | null;
  media_id?: string | null;
  square_media_id?: string | null;
};

export type ZCampaignCreate = {
  platform: ZPlatform;
  account_id: string;
  ad_account_id: string;
  name: string;
  campaign_name?: string | null;
  ad_set_name?: string | null;
  goal: string;
  campaign_type?: "display" | "search" | null;
  /** Money as a decimal string in major units (Zernio takes whole units, not cents). */
  budget: { amount: string; type: "daily" | "lifetime" };
  start_at?: string | null;
  end_at?: string | null;
  bid?: ZBid | null;
  targeting: ZTargeting;
  placements?: ZPlacements | null;
  special_ad_categories: string[];
  creative: ZCreative;
  page_id?: string | null;
  instagram_account_id?: string | null;
  identity_id?: string | null;
  organization_id?: string | null;
  board_id?: string | null;
  promoted_object?: {
    pixel_id?: string | null;
    custom_event_type?: string | null;
    custom_conversion_id?: string | null;
    application_id?: string | null;
    object_store_url?: string | null;
  } | null;
  lead_gen_form_id?: string | null;
  keywords: { text: string; match: "exact" | "phrase" | "broad" }[];
  status: "ACTIVE" | "PAUSED";
  request_id?: string | null;
};

export type ZCreateResult = {
  platform: string;
  campaign_id: string | null;
  ad_set_id: string | null;
  ad_id: string | null;
  status: string | null;
  review_status: string | null;
  message: string;
};

export type ZValidateResult = { supported: boolean; ok: boolean; message: string };
export type ZPreviewResult = { supported: boolean; items: { format: string; html: string | null }[] };

export type ZPost = {
  id: string;
  message: string | null;
  created_at: string | null;
  permalink: string | null;
  picture: string | null;
  media_type: string | null;
};

export type ZBoostCreate = {
  platform: Exclude<ZPlatform, "googleads">;
  account_id: string;
  ad_account_id: string;
  post_id: string;
  name: string;
  goal: string;
  budget: { amount: string; type: "daily" | "lifetime" };
  start_at?: string | null;
  end_at?: string | null;
  targeting: {
    countries: string[];
    regions: GeoRef[];
    cities: CityRef[];
    age_min: number | null;
    age_max: number | null;
    gender: "all" | "male" | "female";
    languages: string[];
    interests: Entity[];
  };
  status: "ACTIVE" | "PAUSED";
  request_id?: string | null;
};

export type ZMetrics = {
  spend: number | null;
  impressions: number | null;
  reach: number | null;
  clicks: number | null;
  ctr: number | null;
  cpc: number | null;
  cpm: number | null;
  conversions: number | null;
  roas: number | null;
};

export type ZMoney = { amount: number | null; type: string | null };

export type ZAdNode = { id: string; name: string | null; status: string | null; review_status: string | null; metrics: ZMetrics | null };
export type ZAdSetNode = { id: string; name: string | null; status: string | null; budget: ZMoney | null; metrics: ZMetrics | null; ads: ZAdNode[] };
export type ZCampaignNode = {
  id: string;
  platform: string;
  name: string | null;
  status: string | null;
  review_status: string | null;
  objective: string | null;
  budget: ZMoney | null;
  currency: string | null;
  ad_account_id: string | null;
  ad_account_name: string | null;
  created_at: string | null;
  metrics: ZMetrics | null;
  ad_sets: ZAdSetNode[];
};

export type ZCampaignList = { items: ZCampaignNode[]; page: number; pages: number; total: number; backfill_pending: boolean };

export type ZStatusResult = { status: string | null; message: string };

export type ZAnalytics = {
  campaign_id: string;
  platform: string;
  currency: string | null;
  start: string;
  end: string;
  backfill_pending: boolean;
  summary: ZMetrics | null;
  daily: { day: string; spend: number | null; impressions: number | null; clicks: number | null; conversions: number | null }[];
  breakdowns: { dimension: string; value: string; spend: number | null; impressions: number | null; clicks: number | null }[];
};

export const emptyTargeting = (): ZTargeting => ({
  countries: [],
  regions: [],
  cities: [],
  zips: [],
  metros: [],
  custom_locations: [],
  excluded: null,
  age_min: null,
  age_max: null,
  gender: "all",
  languages: [],
  interests: [],
  behaviors: [],
  income_tier: null,
});
