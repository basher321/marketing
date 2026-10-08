/**
 * Knowledge Base API (SPEC-FE-015, SPEC-FE-033): brand settings (SPEC-BE-012),
 * FAQs (SPEC-BE-013/048) and policies (SPEC-BE-048). Reading is open to any
 * role; every write requires manager or above (403 otherwise).
 */
import type {
  BrandSettings,
  BrandSettingsUpdate,
  FAQCreate,
  FAQItem,
  FAQList,
  FAQUpdate,
  Policy,
  PolicyInput,
  PolicyList,
} from "../types/kb";
import { apiFetch } from "./client";

export const kbKeys = {
  brand: ["kb", "brand"] as const,
  faqs: ["kb", "faqs"] as const,
  policies: ["kb", "policies"] as const,
};

// Before the tenant's first save the backend returns documented defaults
// (empty name, tone/style 50, English only, no terms), never a 404.
export function fetchBrandSettings(): Promise<BrandSettings> {
  return apiFetch<BrandSettings>("/api/v1/brand");
}

// One save replaces every field (the mockup's single "Save Brand Settings").
export function saveBrandSettings(body: BrandSettingsUpdate): Promise<BrandSettings> {
  return apiFetch<BrandSettings>("/api/v1/brand", { method: "PUT", body: { ...body } });
}

export function fetchFaqs(): Promise<FAQList> {
  return apiFetch<FAQList>("/api/v1/faqs");
}

export function createFaq(body: FAQCreate): Promise<FAQItem> {
  return apiFetch<FAQItem>("/api/v1/faqs", { method: "POST", body: { ...body } });
}

export function updateFaq(id: string, body: FAQUpdate): Promise<FAQItem> {
  return apiFetch<FAQItem>(`/api/v1/faqs/${encodeURIComponent(id)}`, { method: "PATCH", body: { ...body } });
}

export function deleteFaq(id: string): Promise<void> {
  return apiFetch<void>(`/api/v1/faqs/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function fetchPolicies(): Promise<PolicyList> {
  return apiFetch<PolicyList>("/api/v1/policies");
}

export function createPolicy(body: PolicyInput): Promise<Policy> {
  return apiFetch<Policy>("/api/v1/policies", { method: "POST", body: { ...body } });
}

export function updatePolicy(id: string, body: Partial<PolicyInput>): Promise<Policy> {
  return apiFetch<Policy>(`/api/v1/policies/${encodeURIComponent(id)}`, { method: "PATCH", body: { ...body } });
}

export function deletePolicy(id: string): Promise<void> {
  return apiFetch<void>(`/api/v1/policies/${encodeURIComponent(id)}`, { method: "DELETE" });
}
