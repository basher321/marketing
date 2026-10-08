/** AI Ad Autopilot (SPEC-BE-069/070), mirroring backend/app/schemas/ai_campaign.py and ai_model.py. */
import type { PlatformKey } from "./ads";

export type RunStatus =
  | "queued"
  | "running"
  | "needs_input"
  | "ready_for_review"
  | "publishing"
  | "awaiting_approval"
  | "published"
  | "failed"
  | "cancelled";

export interface AICampaignCreate {
  prompt: string;
  platforms: PlatformKey[];
  goal: "sales" | "traffic" | "leads" | "awareness" | "app" | null;
  budget: { amount: string; mode: "daily" | "total" };
  schedule: { starts_at: string | null; ends_at: string | null };
  skus: string[];
  landing_url: string;
  visuals: "generate" | "products" | "builder";
  youtube_video: string | null;
  variants_per_group: number;
}

export interface RunStage {
  name: string;
  status: "pending" | "running" | "done" | "failed" | "skipped";
  started_at: string | null;
  ended_at: string | null;
  provider: string | null;
  note: string | null;
  error: string | null;
}

export interface SafetyIssue {
  ref: string;
  severity: "error" | "warning";
  rule: string;
  message: string;
  source: string;
}

export interface PreviewAd {
  ref: string;
  platform: string;
  format: string;
  group: string;
  copy: Record<string, string | string[]>;
  images: { ratio: string | null; preview: string | null; source: string | null }[];
  angle: string | null;
}

export interface PreviewCampaign {
  platform: string;
  label: string;
  campaign_id: string | null;
  name: string;
  objective: string;
  campaign_type: string | null;
  budget: number;
  budget_mode: string;
  status: string | null;
  groups: { name: string; audience: Record<string, unknown> }[];
}

export interface AICampaignRun {
  id: string;
  status: RunStatus;
  stage: string | null;
  prompt: string;
  request: Partial<AICampaignCreate> & { answers?: { question: string; answer: string }[] };
  stages: RunStage[];
  questions: string[];
  summary: string | null;
  campaigns: PreviewCampaign[];
  ads: PreviewAd[];
  safety: SafetyIssue[];
  can_publish: boolean;
  publish_note: string | null;
  cost_cents: number;
  error: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface AICampaignRunSummary {
  id: string;
  status: RunStatus;
  stage: string | null;
  prompt: string;
  platforms: string[];
  cost_cents: number;
  campaign_ids: string[];
  created_by: string | null;
  created_at: string;
  error: string | null;
}

// --- Creative providers (SPEC-BE-070) ---
export type CreativeKind = "plan" | "copy" | "review" | "image" | "video";

export interface MCPTool {
  id: string;
  name: string;
  url: string;
  enabled: boolean;
  token_masked: string | null;
  tools: Partial<Record<CreativeKind, string>>;
  arguments: Partial<Record<CreativeKind, Record<string, unknown>>>;
  cost_cents_per_call: number;
  last_error: string | null;
  last_ok_at: string | null;
}

export interface CreativeSettings {
  order: Record<CreativeKind, string[]>;
  available: Record<CreativeKind, { key: string; label: string; ready: boolean }[]>;
  mcp_tools: MCPTool[];
}

export interface MCPToolSave {
  name: string;
  url: string;
  token?: string;
  enabled: boolean;
  tools: Partial<Record<CreativeKind, string>>;
  arguments: Partial<Record<CreativeKind, Record<string, unknown>>>;
  cost_cents_per_call: number;
}

export interface MCPToolTest {
  ok: boolean;
  message: string;
  tools_found: string[];
}

// --- Readiness for the "Create with AI" form (SPEC-FE-046 amendment) ---
export interface Readiness {
  platforms: { key: PlatformKey; label: string; usable: boolean; reason: string | null }[];
  text_ai: { ready: boolean; models: { provider: string; label: string; model: string; last_error: string | null }[]; reason: string | null };
  image_ai: { ready: boolean; sources: { key: string; label: string; note: string }[]; reason: string | null };
  products: {
    sku: string;
    title: string;
    status: string;
    price: number;
    compare_at: number | null;
    discount_pct: number;
    currency: string;
    has_photo: boolean;
    selectable: boolean;
    reason: string | null;
  }[];
  brand: { name: string; has_logo: boolean; forbidden_terms: string[] };
  currency: string;
  country: string;
}
