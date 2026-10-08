/**
 * Organization Settings API (SPEC-FE-036): the caller's tenant (SPEC-BE-051)
 * and its users (SPEC-BE-037). Profile/branding need manager+; the user
 * endpoints and the data reset are owner-only (403 otherwise).
 */
import type {
  Branding,
  BrandingSlot,
  LocaleOptions,
  OrgUser,
  OrgUserCreate,
  OrgUserUpdate,
  ResetResult,
  Tenant,
  TenantUpdate,
} from "../types/tenant";
import { apiFetch } from "./client";

export const tenantKeys = {
  me: ["tenant", "me"] as const,
  users: ["tenant", "users"] as const,
  localeOptions: ["tenant", "locale-options"] as const,
};

export function fetchTenant(): Promise<Tenant> {
  return apiFetch<Tenant>("/api/v1/tenants/me");
}

/** Every country, currency, language and timezone (SPEC-BE-072); static, cache it long. */
export function fetchLocaleOptions(): Promise<LocaleOptions> {
  return apiFetch<LocaleOptions>("/api/v1/tenants/locale-options");
}

export function updateTenant(body: TenantUpdate): Promise<Tenant> {
  return apiFetch<Tenant>("/api/v1/tenants/me", { method: "PATCH", body: { ...body } });
}

/** multipart upload; the backend checks the real image type from the bytes. */
export function uploadBrandingImage(slot: BrandingSlot, file: File): Promise<Branding> {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<Branding>(`/api/v1/tenants/me/branding/${slot}`, { method: "PUT", body: form });
}

export function removeBrandingImage(slot: BrandingSlot): Promise<Branding> {
  return apiFetch<Branding>(`/api/v1/tenants/me/branding/${slot}`, { method: "DELETE" });
}

export function updateBrandingText(body: { head_name: string | null; head_title: string | null }): Promise<Branding> {
  return apiFetch<Branding>("/api/v1/tenants/me/branding", { method: "PATCH", body: { ...body } });
}

export function resetCompanyData(body: { confirm_slug: string; password: string }): Promise<ResetResult> {
  return apiFetch<ResetResult>("/api/v1/tenants/me/reset", { method: "POST", body: { ...body } });
}

export function fetchUsers(): Promise<OrgUser[]> {
  return apiFetch<OrgUser[]>("/api/v1/users");
}

export function createUser(body: OrgUserCreate): Promise<OrgUser> {
  return apiFetch<OrgUser>("/api/v1/users", { method: "POST", body: { ...body } });
}

export function updateUser(id: string, body: OrgUserUpdate): Promise<OrgUser> {
  return apiFetch<OrgUser>(`/api/v1/users/${encodeURIComponent(id)}`, { method: "PATCH", body: { ...body } });
}

export function deleteUser(id: string): Promise<void> {
  return apiFetch<void>(`/api/v1/users/${encodeURIComponent(id)}`, { method: "DELETE" });
}
