/** Organic Marketing (SPEC-BE-076 / SPEC-BE-078), mirroring app/schemas/organic.py and the organic analytics schemas. */
import type { SocialPlatform } from "./social";

export type PostFormat = "post" | "carousel" | "reel" | "story" | "video";
export type CopyPart = "caption" | "hashtags" | "cta" | "title";
export type ContentStatus = "draft" | "needs_approval" | "approved" | "archived";
export type PostStatus = "pending" | "scheduled" | "publishing" | "published" | "failed" | "cancelled";

export interface Target {
  platform: SocialPlatform;
  post_format?: PostFormat | null;
  platform_options?: Record<string, unknown>;
}

export interface ManualCreate {
  title?: string | null;
  caption: string;
  hashtags: string[];
  cta?: string | null;
  link_url?: string | null;
  media_ids: string[];
  targets: Target[];
  adapt: "rules" | "ai";
}

export interface AICreate {
  prompt: string;
  product_ids: string[];
  tone?: string | null;
  link_url?: string | null;
  targets: Target[];
  media: { mode: "none" | "use" | "generate_photo" | "generate_video"; media_ids?: string[]; generation?: Record<string, unknown> };
}

export interface ContentPatch {
  title?: string | null;
  caption?: string;
  hashtags?: string[];
  cta?: string | null;
  link_url?: string | null;
  media_ids?: string[];
  readapt?: boolean;
}

export interface VersionPatch {
  caption?: string;
  hashtags?: string[];
  cta?: string | null;
  title?: string | null;
  media_ids?: string[];
  post_format?: PostFormat;
  platform_options?: Record<string, unknown>;
}

export interface MediaRef {
  id: string;
  kind: string;
  url: string;
  width: number | null;
  height: number | null;
  duration_ms: number | null;
}

export interface Post {
  id: string;
  version_id: string;
  content_id: string | null;
  platform: SocialPlatform;
  status: PostStatus;
  scheduled_at: string;
  timezone: string;
  /** Wall-clock time in `timezone`, e.g. "2026-10-04T20:00". */
  local_time: string | null;
  published_at: string | null;
  external_post_id: string | null;
  external_url: string | null;
  error_message: string | null;
  retry_count: number;
  title: string | null;
  excerpt: string;
}

export interface Version {
  id: string;
  platform: SocialPlatform;
  status: string;
  post_format: PostFormat;
  caption: string;
  hashtags: string[];
  cta: string | null;
  title: string | null;
  link_url: string | null;
  media: MediaRef[];
  platform_options: Record<string, unknown>;
  warnings: string[];
  edited: boolean;
  variant_index: number;
  variant_count: number;
  account: { status?: string; account_name?: string | null; handle?: string | null; avatar_url?: string | null; extra?: Record<string, unknown>; limits?: Record<string, unknown> };
  post: Post | null;
}

export interface Content {
  id: string;
  title: string | null;
  mode: "manual" | "ai";
  prompt: string | null;
  caption: string;
  hashtags: string[];
  cta: string | null;
  link_url: string | null;
  media: MediaRef[];
  product_ids: string[];
  status: ContentStatus;
  approved_at: string | null;
  media_pending: string[];
  warnings: string[];
  /** SPEC-BE-081: AI copy written with the company's recent results. */
  performance_used: boolean;
  versions: Version[];
  created_at: string;
  updated_at: string;
}

/** "What's working" (SPEC-BE-081), mirroring schemas/organic.py Insights. */
export interface InsightFormat {
  post_format: string;
  avg_engagement_rate: number;
  posts: number;
}

export interface InsightPlatform {
  platform: string;
  posts_with_results: number;
  avg_engagement_rate: number;
  best_hours: { hour: number; label: string; avg_engagement_rate: number; posts: number }[];
  best_format: InsightFormat | null;
  formats: InsightFormat[];
  hashtags_top_third: number | null;
  hashtags_bottom_third: number | null;
}

export interface InsightPost {
  post_id: string;
  platform: string;
  post_format: string;
  excerpt: string;
  engagement_rate: number;
  engagements: number;
  impressions: number;
  published_at: string;
  external_url: string | null;
}

export interface Insights {
  has_data: boolean;
  reason: string | null;
  days: number;
  timezone: string;
  platforms: InsightPlatform[];
  top_posts: InsightPost[];
  bottom_posts: InsightPost[];
  lines: { platform: string; text: string }[];
  generated_at: string;
}

export interface ContentListItem {
  id: string;
  title: string | null;
  mode: string;
  status: ContentStatus;
  excerpt: string;
  platforms: SocialPlatform[];
  thumbnail_url: string | null;
  next_post_at: string | null;
  published_count: number;
  created_at: string;
}

export interface ContentList {
  count: number;
  items: ContentListItem[];
}

export interface Preview {
  version_id: string;
  platform: SocialPlatform;
  post_format: PostFormat;
  /** Exactly what is sent to the platform. */
  text: string;
  title: string | null;
  link_url: string | null;
  media: MediaRef[];
  account: { status?: string; account_name?: string | null; handle?: string | null; avatar_url?: string | null };
  warnings: string[];
  errors: string[];
  caption_max: number;
  more_cutoff: number | null;
}

export interface CalendarDay {
  date: string;
  posts: Post[];
}

export interface Calendar {
  timezone: string;
  start: string;
  end: string;
  days: CalendarDay[];
}

export interface History {
  count: number;
  items: Post[];
}

export interface Summary {
  timezone: string;
  scheduled_next_7d: number;
  published_30d: number;
  failed_open: number;
  awaiting_approval: number;
  by_platform: Record<string, { scheduled: number; published_30d: number; failed: number }>;
  upcoming: Post[];
  recent: Post[];
  scheduler: { running: boolean; publishes: boolean };
}

// --- Organic analytics (SPEC-BE-078) ---------------------------------------
export interface OrganicTotals {
  impressions: number | null;
  reach: number | null;
  likes: number | null;
  comments: number | null;
  shares: number | null;
  saves: number | null;
  clicks: number | null;
  video_views: number | null;
  engagements: number | null;
}

export interface OrganicReport {
  range: string;
  timezone: string;
  posts_published: number;
  totals: OrganicTotals;
  engagement_rate: number | null;
  by_platform: { platform: string; posts_published: number; impressions: number | null; engagements: number | null; engagement_rate: number | null }[];
  daily: { date: string; posts: number; impressions: number | null; engagements: number | null }[];
  top_posts: { post_id: string; platform: string; excerpt: string; external_url: string | null; published_at: string; engagements: number; impressions: number | null }[];
  last_import_at: string | null;
  missing_reason: string | null;
}

export interface OrganicImportResult {
  posts: number;
  rows: number;
  platforms: Record<string, number>;
  errors: string[];
}
