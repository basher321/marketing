/**
 * Integrations types (SPEC-FE-021, SPEC-FE-037), mirroring the backend
 * schemas in app/schemas/integration.py (SPEC-BE-017/052) and
 * app/schemas/ai_model.py (SPEC-BE-053) field for field.
 */

/** Backend three-way status (SPEC-BE-017), derived per provider. */
export type IntegrationConnectionStatus = "connected" | "needs_reconnect" | "not_connected";

/** One row of GET /api/v1/integrations. Secrets are never returned. */
export interface IntegrationStatus {
  /** Live integration_provider enum value, e.g. "meta_ads". */
  provider: string;
  name: string;
  /** Ads, Social, Messaging, Email, Commerce, CRM. */
  category: string;
  status: IntegrationConnectionStatus;
  last_synced_at: string | null;
  account_name: string | null;
  /** Keys of fields that have a saved value. */
  configured_fields: string[];
  /** Non-secret values as saved; secrets as "••••" + last 4. */
  masked: Record<string, string>;
  last_error: string | null;
  /** ISO 8601 UTC of the last passing connection test. */
  verified_at: string | null;
}

export interface CatalogField {
  key: string;
  label: string;
  secret: boolean;
  required: boolean;
  help: string;
}

export interface CatalogProvider {
  provider: string;
  label: string;
  category: string;
  fields: CatalogField[];
  test: boolean;
  docs_url: string;
}

export interface IntegrationSave {
  account_name?: string | null;
  /** A secret sent as "" keeps the saved value. */
  fields: Record<string, string>;
}

export interface IntegrationTestResult {
  status: IntegrationConnectionStatus;
  ok: boolean;
  message: string;
  last_error: string | null;
  verified_at: string | null;
  account_name: string | null;
}

// ---- AI models (SPEC-BE-053)
// SPEC-BE-088 adds OpenRouter and a local Ollama (no key).
export type AIProvider = "anthropic" | "openai" | "gemini" | "groq" | "openrouter" | "ollama";

export interface AIModelProvider {
  provider: AIProvider;
  label: string;
  enabled: boolean;
  /** Null until the company chooses one; there is no built-in default (SPEC-BE-053 amendment). */
  model: string | null;
  image_model: string | null;
  /** OpenAI and Gemini also have image models. */
  has_images: boolean;
  /** Video generation (SPEC-BE-077): Sora on OpenAI, Veo on Gemini. */
  video_model: string | null;
  has_video: boolean;
  /** 0 = tried first. */
  priority: number;
  key_masked: string | null;
  last_error: string | null;
  last_ok_at: string | null;
  docs_url: string;
  /** False for a local provider that takes no key (Ollama, SPEC-BE-088). */
  needs_key: boolean;
}

export interface AIModelList {
  providers: AIModelProvider[];
  env_fallback: { provider: string; configured: boolean };
}

export interface AIModelUpdate {
  api_key?: string;
  model?: string;
  /** Empty string clears it. */
  image_model?: string;
  /** Empty string clears it (SPEC-BE-077). */
  video_model?: string;
  enabled?: boolean;
}

export interface AIModelTestResult {
  ok: boolean;
  latency_ms: number;
  model: string;
  error: string | null;
  /** On a 404 (retired model): what the key can use now, best first. */
  suggested: string | null;
  suggestions: string[];
}

export interface ModelOption {
  id: string;
  label: string;
}

/** GET /ai-models/{provider}/models: the provider's live list for the saved key. */
export interface ProviderModels {
  ok: boolean;
  error: string | null;
  chat: ModelOption[];
  image: ModelOption[];
  /** Veo / Sora models (SPEC-BE-077). */
  video?: ModelOption[];
  suggested: { chat: string | null; image: string | null };
}
