/**
 * Campaign Wizard creative types (SPEC-FE-016, SPEC-FE-031), mirroring backend
 * app/schemas/content.py (SPEC-BE-029/030/046) field for field.
 */

export type CampaignObjective =
  | "awareness"
  | "traffic"
  | "engagement"
  | "conversions"
  | "message_replies"
  | "reach";

/** POST /api/v1/content/creatives body — backend CreativeGenerateRequest. */
export interface CreativeGenerateRequest {
  objective: CampaignObjective;
  /** 1+ SKUs of the tenant's own products (unknown SKUs -> 422). */
  skus: string[];
  brief: string;
  /** Live channel_type value. */
  channel: string;
  /** Links the generated asset to a campaign draft (SPEC-FE-031). */
  campaign_id?: string | null;
  title?: string | null;
}

/** POST /api/v1/content/creatives/manual body — backend CreativeManualCreate (SPEC-BE-046). */
export interface CreativeManualCreate {
  channel: string;
  campaign_id: string | null;
  title: string | null;
  /** 1–5 variants; headline 1–120 chars, description up to 500. */
  variants: { headline: string; description: string }[];
}

/** PATCH /api/v1/content/creatives/{id}/variants/{index} body — backend VariantEditRequest. */
export interface VariantEdit {
  headline?: string;
  description?: string;
}

/** One variant — backend CreativeVariantRead. Text only: no image field exists. */
export interface CreativeVariant {
  index: number;
  headline: string;
  description: string;
}

/** POST /content/creatives (201), GET /content/creatives/{id}, POST .../select — backend CreativeAssetRead. */
export interface CreativeAsset {
  id: string;
  campaign_id: string | null;
  title: string | null;
  channel: string;
  format: string;
  status: string;
  variants: CreativeVariant[];
  /** The persisted selection; null until one is selected. */
  selected_variant_index: number | null;
  generated_by_model: string | null;
  created_at: string;
}
