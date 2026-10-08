/**
 * Knowledge Base types (SPEC-FE-015, SPEC-FE-033), mirroring the backend schemas
 * app/schemas/brand.py (SPEC-BE-012), app/schemas/faq.py (SPEC-BE-013/048) and
 * app/schemas/policy.py (SPEC-BE-048).
 */

/** "en" | "bn" — the languages the mockup's select offers. */
export type LanguageCode = "en" | "bn";

/** GET/PUT /api/v1/brand response — backend BrandSettingsRead. */
export interface BrandSettings {
  brand_name: string;
  /** 0–100, Formal ↔ Playful (stored as voice_config.tone). */
  tone: number;
  /** 0–100, Concise ↔ Detailed (stored as voice_config.style). */
  style: number;
  primary_language: string;
  supported_languages: string[];
  forbidden_terms: string[];
}

/** PUT /api/v1/brand body — backend BrandSettingsUpdate: every field required. */
export interface BrandSettingsUpdate {
  brand_name: string;
  tone: number;
  style: number;
  primary_language: LanguageCode;
  supported_languages: LanguageCode[];
  forbidden_terms: string[];
}

/** One FAQ — backend FAQItem. channels [] means "All channels". */
export interface FAQItem {
  id: string;
  question: string;
  /** SPEC-BE-048: the full answer and the enabled flag. */
  answer: string;
  /** A disabled FAQ stays listed but is not used by the AI. */
  enabled: boolean;
  channels: string[];
}

/** PATCH /api/v1/faqs/{id} body — only the fields sent change (SPEC-BE-048). */
export interface FAQUpdate {
  question?: string;
  answer?: string;
  channels?: string[];
  enabled?: boolean;
}

/** Live policies.policy_type values the API accepts (SPEC-BE-048). */
export type PolicyType =
  | "returns"
  | "refunds"
  | "exchanges"
  | "warranty"
  | "shipping"
  | "payment"
  | "privacy"
  | "terms"
  | "other";

export interface Policy {
  id: string;
  policy_type: PolicyType;
  title: string;
  body: string;
  enabled: boolean;
  /** ISO 8601 UTC, or null = no limit. */
  effective_from: string | null;
  effective_until: string | null;
  updated_at: string;
}

export interface PolicyList {
  count: number;
  items: Policy[];
}

export interface PolicyInput {
  policy_type: PolicyType;
  title: string;
  body: string;
  enabled: boolean;
  effective_from: string | null;
  effective_until: string | null;
}

/** GET /api/v1/faqs — backend FAQList; count === items.length. */
export interface FAQList {
  count: number;
  items: FAQItem[];
}

/** POST /api/v1/faqs body — backend FAQCreate. */
export interface FAQCreate {
  question: string;
  answer: string;
  /** Live channel_type values; [] = all channels. */
  channels: string[];
}
