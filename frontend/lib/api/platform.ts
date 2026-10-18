/**
 * Super admin API (SPEC-BE-101 / SPEC-FE-068). Only PilotSonic's Super admin
 * gets answers under /platform (anyone else: 404); /platform/me says which.
 */
import type {
  AccessGroup,
  CompanyAccess,
  CompanyList,
  PlatformMe,
  SettingGroup,
  SettingGroupRead,
  SettingTest,
} from "../types/platform";
import { apiFetch } from "./client";

export const platformKeys = {
  me: ["platform", "me"] as const,
  aiModels: ["platform", "ai-models"] as const,
  settings: ["platform", "settings"] as const,
  companies: (q: string, page: number) => ["platform", "companies", q, page] as const,
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
