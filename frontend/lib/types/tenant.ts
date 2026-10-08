/**
 * Organization Settings types (SPEC-FE-036), mirroring backend
 * app/schemas/tenant.py (SPEC-BE-051) and app/schemas/user.py (SPEC-BE-037).
 */

export interface Branding {
  /** data: URLs (PNG/JPEG/WebP, <= 1 MB), or null. */
  logo_url: string | null;
  banner_url: string | null;
  head: { name: string | null; title: string | null; photo_url: string | null };
}

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  subdomain: string;
  status: string;
  currency: string;
  timezone: string;
  country_code: string | null;
  default_language: string;
  branding: Branding;
  created_at: string;
}

export interface TenantUpdate {
  name?: string;
  country_code?: string;
  currency?: string;
  timezone?: string;
  default_language?: string;
}

/** GET /tenants/locale-options (SPEC-BE-072): worldwide lists from CLDR + IANA. */
export interface CountryOption {
  code: string;
  name: string;
  /** The country's currency, null where it has none (Antarctica). */
  currency: string | null;
  timezones: string[];
}

export interface CurrencyOption {
  code: string;
  name: string;
  symbol: string;
  /** ISO 4217 minor digits: JPY 0, USD 2, KWD 3. */
  decimals: number;
}

export interface LanguageOption {
  code: string;
  name: string;
  native_name: string;
}

export interface TimezoneOption {
  name: string;
  /** Current UTC offset, e.g. "+06:00". */
  offset: string;
}

export interface LocaleOptions {
  countries: CountryOption[];
  currencies: CurrencyOption[];
  languages: LanguageOption[];
  timezones: TimezoneOption[];
}

export type BrandingSlot = "logo" | "banner" | "head_photo";

/** Live role_type values the users API accepts. */
export type RoleType = "owner" | "manager" | "operator" | "analyst" | "viewer";

export interface OrgUser {
  id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  role: RoleType | string;
  /** active, invited, disabled, locked. */
  status: string;
  last_login_at: string | null;
  created_at: string;
}

export interface OrgUserCreate {
  email: string;
  password: string;
  first_name: string | null;
  last_name: string | null;
  role: RoleType;
}

export interface OrgUserUpdate {
  role?: RoleType;
  status?: "active" | "disabled";
}

export interface ResetResult {
  deleted: Record<string, number>;
  reset_at: string;
}
