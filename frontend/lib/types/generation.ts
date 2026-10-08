/** Photo / video generation (SPEC-BE-077), mirroring app/schemas/generation.py. */
import type { MediaItem } from "./media";
import type { Target } from "./organic";
import type { SocialPlatform } from "./social";

export type GenerationKind = "image" | "video";
export type GenerationStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface PhotoRequest {
  prompt: string;
  product_ids: string[];
  reference_media_ids: string[];
  aspect_ratio?: string | null;
  style?: string | null;
  target_platform?: SocialPlatform | null;
  count: number;
}

export interface VideoRequest {
  prompt: string;
  product_ids: string[];
  reference_media_ids: string[];
  aspect_ratio?: "9:16" | "16:9" | "1:1" | null;
  duration_s: number;
  style?: string | null;
  negative_prompt?: string | null;
  target_platform?: SocialPlatform | null;
}

export interface GenerationJob {
  id: string;
  kind: GenerationKind;
  status: GenerationStatus;
  request: Record<string, unknown>;
  /** What the provider really makes: duration_s, aspect_ratio, provider. */
  effective: Record<string, unknown>;
  provider: string | null;
  model: string | null;
  attempts: { provider: string; outcome: string; at: string }[];
  media: MediaItem | null;
  parent_job_id: string | null;
  approved_at: string | null;
  cost_cents: number;
  error: string | null;
  /** e.g. "15 s requested → 8 s generated (…)". */
  notes: string[];
  content_id: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface JobList {
  count: number;
  items: GenerationJob[];
}

export interface ProviderReadiness {
  key: string;
  label: string;
  ready: boolean;
  reason: string | null;
  model: string | null;
  durations: number[];
  aspect_ratios: string[];
  reference_images: boolean;
}

export interface Readiness {
  image: ProviderReadiness[];
  video: ProviderReadiness[];
  image_ready: boolean;
  video_ready: boolean;
  setup_hint: string;
}

export interface ApproveRequest {
  create_content?: { caption?: string | null; targets: Target[]; adapt: "rules" | "ai" } | null;
}
