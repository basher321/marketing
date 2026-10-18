/** Super admin (SPEC-BE-101 / SPEC-FE-068): PilotSonic's own keys and app credentials. */
export type SettingGroup = "socialapi" | "zernio" | "meta_app" | "tiktok_app" | "linkedin_app";

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
export type AccessGroup = "ai" | "socialapi" | "zernio" | "meta_app" | "tiktok_app" | "linkedin_app";

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
