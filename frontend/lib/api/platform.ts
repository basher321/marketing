/**
 * Super admin API (SPEC-BE-101 / SPEC-FE-068). Only PilotSonic's Super admin
 * gets answers under /platform (anyone else: 404); /platform/me says which.
 */
import type {
  AccessGroup,
  AppBranding,
  AppBrandingSlot,
  IntegrationErrorRow,
  IntegrationHealth,
  CompanyAccess,
  CompanyList,
  PlatformMe,
  SettingGroup,
  SettingGroupRead,
  SettingTest,
} from "../types/platform";
import type { IntegrationSave, IntegrationStatus, IntegrationTestResult } from "../types/integrations";
import { apiFetch } from "./client";

export const platformKeys = {
  me: ["platform", "me"] as const,
  aiModels: ["platform", "ai-models"] as const,
  settings: ["platform", "settings"] as const,
  companies: (q: string, page: number) => ["platform", "companies", q, page] as const,
  companyIntegrations: (tenantId: string) => ["platform", "companies", tenantId, "integrations"] as const,
  branding: ["platform", "branding"] as const,
  health: ["platform", "integrations", "health"] as const,
  errors: (provider: string, cursor: string | null) => ["platform", "integrations", "errors", provider, cursor] as const,
};

export function fetchPlatformMe(): Promise<PlatformMe> {
  return apiFetch<PlatformMe>("/api/v1/platform/me");
}

export function fetchPlatformSettings(): Promise<SettingGroupRead[]> {
  return apiFetch<SettingGroupRead[]>("/api/v1/platform/settings");
}

/** Only fields sent with a value change; `clear` removes saved ones (the server's .env value then applies). */
export function savePlatformSettings(group: SettingGroup, values: Record<string, string>, clear: string[] = []): Promise<SettingGroupRead> {
  return apiFetch<SettingGroupRead>(`/api/v1/platform/settings/${group}`, { method: "PUT", body: { values, clear } });
}

export function testPlatformSettings(group: SettingGroup): Promise<SettingTest> {
  return apiFetch<SettingTest>(`/api/v1/platform/settings/${group}/test`, { method: "POST" });
}

/** SPEC-BE-103: every company with its access switches (paged, searchable by name or slug). */
export function fetchCompanies(q: string, page: number, pageSize = 25): Promise<CompanyList> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (q.trim()) params.set("q", q.trim());
  return apiFetch<CompanyList>(`/api/v1/platform/companies?${params}`);
}

/** Only the groups to change: true = may use PilotSonic's key, false = blocked. */
export function saveCompanyAccess(tenantId: string, access: Partial<Record<AccessGroup, boolean>>): Promise<CompanyAccess> {
  return apiFetch<CompanyAccess>(`/api/v1/platform/companies/${tenantId}/access`, { method: "PUT", body: { access } });
}


/** SPEC-BE-115: a company's API-key integrations (store, email, CRM, WhatsApp token), set by the Super admin. */
function companyIntegrationPath(tenantId: string, provider?: string): string {
  return `/api/v1/platform/companies/${tenantId}/integrations${provider ? `/${encodeURIComponent(provider)}` : ""}`;
}

export function fetchCompanyIntegrations(tenantId: string): Promise<IntegrationStatus[]> {
  return apiFetch<IntegrationStatus[]>(companyIntegrationPath(tenantId));
}

export function saveCompanyIntegration(tenantId: string, provider: string, body: IntegrationSave): Promise<IntegrationTestResult> {
  return apiFetch<IntegrationTestResult>(companyIntegrationPath(tenantId, provider), { method: "PUT", body: { ...body } });
}

export function testCompanyIntegration(tenantId: string, provider: string): Promise<IntegrationTestResult> {
  return apiFetch<IntegrationTestResult>(`${companyIntegrationPath(tenantId, provider)}/test`, { method: "POST" });
}

export function removeCompanyIntegration(tenantId: string, provider: string): Promise<void> {
  return apiFetch<void>(companyIntegrationPath(tenantId, provider), { method: "DELETE" });
}

/** GET /platform/branding (SPEC-BE-113): public, the login page reads it too. */
export function fetchAppBranding(): Promise<AppBranding> {
  return apiFetch<AppBranding>("/api/v1/platform/branding");
}

export function saveAppBranding(body: { app_name?: string; tagline?: string }): Promise<AppBranding> {
  return apiFetch<AppBranding>("/api/v1/platform/branding", { method: "PUT", body });
}

export function uploadAppBrandingImage(slot: AppBrandingSlot, file: File): Promise<AppBranding> {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<AppBranding>(`/api/v1/platform/branding/${slot}`, { method: "PUT", body: form });
}

export function removeAppBrandingImage(slot: AppBrandingSlot): Promise<AppBranding> {
  return apiFetch<AppBranding>(`/api/v1/platform/branding/${slot}`, { method: "DELETE" });
}

/** Super admin: integration health and the errors log (SPEC-BE-113 FR3). */
export function fetchIntegrationHealth(): Promise<{ items: IntegrationHealth[] }> {
  return apiFetch<{ items: IntegrationHealth[] }>("/api/v1/platform/integrations/health");
}

export function fetchIntegrationErrors(provider: string, cursor: string | null): Promise<{ items: IntegrationErrorRow[]; next_cursor: string | null }> {
  const s = new URLSearchParams();
  if (provider) s.set("provider", provider);
  if (cursor) s.set("cursor", cursor);
  return apiFetch(`/api/v1/platform/integrations/errors?${s.toString()}`);
}
