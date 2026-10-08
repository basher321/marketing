/**
 * Meta connect (SPEC-BE-054) and Ads Manager-style builder (SPEC-BE-055)
 * types, mirroring app/schemas/integration.py (Meta*) and app/schemas/meta.py.
 * Money is in major units of the campaign currency.
 */

// --- connect ---------------------------------------------------------------
export interface MetaConnectUrl {
  login_url: string;
}
export interface MetaChoices {
  connection_id: string;
  ad_accounts: { id: string; name: string; currency: string; account_status: number }[];
  pages: { id: string; name: string; instagram: { id: string; username: string | null } | null }[];
  pixels: { id: string; name: string; ad_account_id: string }[];
}
export interface MetaSelect {
  ad_account_id: string;
  page_id: string;
  instagram_id: string | null;
  pixel_id: string | null;
}

// --- builder ---------------------------------------------------------------
export type BuilderObjective = "awareness" | "traffic" | "engagement" | "leads" | "app_promotion" | "sales";
export type BudgetType = "daily" | "lifetime";
export type BidStrategy = "LOWEST_COST_WITHOUT_CAP" | "LOWEST_COST_WITH_BID_CAP" | "COST_CAP" | "LOWEST_COST_WITH_MIN_ROAS";
export type ConversionLocation = "none" | "website" | "app" | "instant_form" | "on_ad" | "video" | "page";

export interface TargetRef {
  key: string;
  name: string;
  type?: string | null;
  radius?: number | null;
  distance_unit?: "kilometer" | "mile" | null;
}

export interface Targeting {
  countries: string[];
  regions: TargetRef[];
  cities: TargetRef[];
  zips: TargetRef[];
  age_min: number;
  age_max: number;
  genders: "all" | "male" | "female";
  locales: TargetRef[];
  detailed: TargetRef[];
  custom_audiences: TargetRef[];
  excluded_custom_audiences: TargetRef[];
  advantage_audience: boolean;
  /** Names from a saved audience that must be re-picked from Meta's search. */
  pending_terms?: string[];
}

export interface Placements {
  mode: "advantage" | "manual";
  platforms: ("facebook" | "instagram" | "messenger" | "audience_network")[];
  positions: Record<string, string[]>;
  devices: ("mobile" | "desktop")[];
}

export interface Media {
  type: "image" | "video";
  image_hash?: string | null;
  video_id?: string | null;
  thumbnail_url?: string | null;
  name: string;
  status?: string;
}

// SPEC-BE-082: a carousel card is an image (image_hash) or a video (video_id).
export interface Card {
  type: "image" | "video";
  image_hash?: string | null;
  video_id?: string | null;
  thumbnail_url?: string | null;
  status?: string | null;
  headline: string;
  description: string;
  link?: string | null;
}

export interface ProductSet {
  id: string;
  name: string;
  catalog_id: string;
  catalog_name: string;
  product_count?: number | null;
}

export interface ExistingPost {
  platform: "facebook" | "instagram";
  id: string;
  message: string;
  picture?: string | null;
  permalink_url?: string | null;
  created_time?: string | null;
}

export interface PostList {
  items: ExistingPost[];
  next_cursor: string | null;
}

export interface PostCreate {
  message: string;
  link?: string | null;
  image_url?: string | null;
}

export type AdFormat = "image" | "video" | "carousel" | "existing_post";
export type CarouselSource = "manual" | "product_set";

export interface Destination {
  type: "website" | "app" | "instant_form" | "none";
  url?: string | null;
  app_store_url?: string | null;
  lead_form_id?: string | null;
}

export interface BuilderAd {
  id: string;
  name: string;
  status: string;
  external_ad_id: string | null;
  effective_status: string | null;
  review_feedback: Record<string, unknown> | null;
  last_error: string | null;
  format: AdFormat;
  media: Media[];
  cards: Card[];
  carousel_source: CarouselSource;
  product_set: ProductSet | null;
  existing_post: ExistingPost | null;
  primary_text: string;
  headline: string;
  description: string;
  call_to_action: string;
  destination: Destination;
  url_tags: string;
  use_instagram: boolean;
  content_asset_id: string | null;
}

export interface BuilderAdSet {
  id: string;
  name: string;
  status: string;
  external_id: string | null;
  effective_status: string | null;
  last_error: string | null;
  conversion_location: ConversionLocation;
  optimization_goal: string | null;
  pixel_id: string | null;
  custom_event_type: string | null;
  app_id: string | null;
  app_store_url: string | null;
  budget_type: BudgetType;
  budget: number | null;
  bid_strategy: BidStrategy | null;
  bid_amount: number | null;
  starts_at: string | null;
  ends_at: string | null;
  targeting: Targeting;
  placements: Placements;
  ads: BuilderAd[];
}

export interface BuilderCampaign {
  id: string;
  name: string;
  objective: BuilderObjective;
  status: string;
  currency: string;
  special_ad_categories: string[];
  special_ad_category_country: string[];
  buying_type: string;
  budget_mode: "campaign" | "ad_set";
  budget_type: BudgetType;
  budget: number | null;
  bid_strategy: BidStrategy;
  bid_amount: number | null;
  roas_floor: number | null;
  spend_cap: number | null;
  spent: number;
  starts_at: string | null;
  ends_at: string | null;
  pending_approval_id: string | null;
  effective_status: string | null;
}

export interface Issue {
  level: "campaign" | "ad_set" | "ad";
  id: string | null;
  field: string;
  message: string;
  source: "local" | "meta";
}

export interface BuilderTree {
  campaign: BuilderCampaign;
  ad_sets: BuilderAdSet[];
  missing: Issue[];
  meta: {
    published: boolean;
    campaign_id: string | null;
    ad_account_id: string | null;
    published_at: string | null;
    last_error: string | null;
    effective_status: string | null;
    ads_manager_url: string | null;
  } | null;
  approval: { required: boolean; reason: string } | null;
}

export interface ObjectiveInfo {
  key: BuilderObjective;
  label: string;
  description: string;
  meta_objective: string;
  available: boolean;
  reason: string | null;
  conversion_locations: Record<string, string[]>;
  unavailable_locations: Record<string, string>;
}

export interface ObjectivesResult {
  objectives: ObjectiveInfo[];
  bid_strategies: BidStrategy[];
  special_ad_categories: string[];
  placements: Record<string, string[]>;
  calls_to_action: string[];
  event_types: string[];
  preview_formats: string[];
  connection: { connected: boolean; ad_account_id: string | null; page_id: string | null; instagram_id: string | null; pixel_id: string | null };
}

export interface LookupItem {
  id: string;
  name: string;
  type: string | null;
  extra: Record<string, unknown>;
}

export interface ReachResult {
  available: boolean;
  reason: string | null;
  daily_reach_lower: number | null;
  daily_reach_upper: number | null;
}

export interface MediaResult {
  type: "image" | "video";
  image_hash: string | null;
  video_id: string | null;
  thumbnail_url: string | null;
  status: string;
  name: string;
}

export interface ValidateResult {
  ok: boolean;
  errors: Issue[];
}

export interface PreviewResult {
  format: string;
  iframe_html: string;
}

export interface StatusResult {
  id: string;
  name: string;
  level: string;
  status: string;
}

// Partial update bodies (only sent fields change).
export type CampaignFields = Partial<{
  name: string;
  objective: BuilderObjective;
  special_ad_categories: string[];
  special_ad_category_country: string[];
  budget_mode: "campaign" | "ad_set";
  budget_type: BudgetType;
  budget: number | null;
  bid_strategy: BidStrategy;
  bid_amount: number | null;
  roas_floor: number | null;
  spend_cap: number | null;
}>;

export type AdSetFields = Partial<{
  name: string;
  conversion_location: ConversionLocation;
  optimization_goal: string;
  pixel_id: string | null;
  custom_event_type: string | null;
  app_id: string | null;
  app_store_url: string | null;
  budget_type: BudgetType;
  budget: number | null;
  bid_strategy: BidStrategy;
  bid_amount: number | null;
  starts_at: string | null;
  ends_at: string | null;
  targeting: Targeting;
  placements: Placements;
  audience_id: string;
}>;

export type AdFields = Partial<{
  name: string;
  format: AdFormat;
  media: Media[];
  cards: Card[];
  carousel_source: CarouselSource;
  product_set: ProductSet | null;
  existing_post: ExistingPost | null;
  primary_text: string;
  headline: string;
  description: string;
  call_to_action: string;
  destination: Destination;
  url_tags: string;
  use_instagram: boolean;
  content_asset_id: string;
}>;

// --- results (SPEC-BE-056) ---------------------------------------------------
export interface ResultKpis {
  spend: number | null;
  impressions: number | null;
  reach: number | null;
  clicks: number | null;
  ctr: number | null;
  results: number | null;
  roas: number | null;
}
export interface CampaignResults {
  campaign_id: string;
  currency: string;
  range: string;
  source: string;
  result_metric: string;
  summary: string;
  totals: ResultKpis;
  daily: (ResultKpis & { date: string })[];
  ad_sets: (ResultKpis & { id: string; name: string; status: string; effective_status: string | null })[];
  ads: (ResultKpis & { id: string; name: string; status: string; effective_status: string | null; ad_set_id: string | null })[];
  effective_status: string | null;
  last_sync_at: string | null;
}
export interface MetaSyncResult {
  synced_campaigns: number;
  rows_written: number;
  last_sync_at: string;
  errors: { campaign_id: string | null; message: string; at: string }[];
}
