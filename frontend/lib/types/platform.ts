/** Super admin (SPEC-BE-101 / SPEC-FE-068): PilotSonic's own keys and app credentials. */
// SPEC-BE-108 adds twilio, SPEC-BE-112 whatsapp_app.
export type SettingGroup = "socialapi" | "zernio" | "meta_app" | "tiktok_app" | "linkedin_app" | "twilio" | "whatsapp_app";

export interface PlatformMe {
  super_admin: boolean;
}

export interface SettingField {
  field: string;
  label: string;
  secret: boolean;
  set: boolean;
  /** "admin" = saved on this screen, "server" = from backend/.env, null = not set. */
  source: "admin" | "server" | null;
  /** A secret only masked; a plain value (an app id) as it is. */
  value: string | null;
}

export interface SettingGroupRead {
  group: SettingGroup;
  label: string;
  fields: SettingField[];
  last_ok_at: string | null;
  last_error: string | null;
}

export interface SettingTest {
  ok: boolean;
  message: string;
}

/** SPEC-BE-103 / SPEC-FE-069: which companies may use PilotSonic's keys. */
export type AccessGroup = "ai" | "socialapi" | "zernio" | "meta_app" | "tiktok_app" | "linkedin_app" | "sms" | "whatsapp";

export type CompanyAccess = Record<AccessGroup, boolean>;

export interface CompanyRow {
  tenant_id: string;
  name: string;
  slug: string;
  status: string;
  created_at: string | null;
  access: CompanyAccess;
  /** What the company holds at the shared services (made on its first use). */
  socialapi_brand: boolean;
  socialapi_error: string | null;
  zernio_profile: boolean;
}

export interface CompanyList {
  items: CompanyRow[];
  total: number;
  page: number;
  page_size: number;
  groups: { group: AccessGroup; label: string }[];
}


// ---- SPEC-BE-113: app branding and integration health ---------------------------
export interface AppBranding {
  app_name: string;
  tagline: string | null;
  /** data: URLs; null = the built-in PilotSonic mark. */
  logo_url: string | null;
  logo_dark_url: string | null;
  favicon_url: string | null;
}

export type AppBrandingSlot = "logo" | "logo_dark" | "favicon";

export interface IntegrationHealth {
  provider: string;
  label: string;
  configured: boolean;
  last_ok_at: string | null;
  last_error: string | null;
  companies_connected: number;
  companies_with_errors: number;
}

export interface IntegrationErrorRow {
  at: string;
  provider: string;
  /** connection | webhook | invalid_signature | sms_failed */
  kind: string;
  company_id: string | null;
  company_name: string | null;
  message: string;
}
