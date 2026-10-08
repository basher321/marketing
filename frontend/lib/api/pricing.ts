/**
 * Pricing rules API (SPEC-FE-028, backend SPEC-BE-042). Reading is open to any
 * role; creating and enabling/disabling require manager or above (403 otherwise).
 */
import type { PricingRule, PricingRuleCreate, PricingRuleList } from "../types/pricing";
import { apiFetch } from "./client";

export const pricingKeys = {
  rules: ["pricing", "rules"] as const,
};

export function fetchPricingRules(): Promise<PricingRuleList> {
  return apiFetch<PricingRuleList>("/api/v1/pricing/rules");
}

export function createPricingRule(body: PricingRuleCreate): Promise<PricingRule> {
  return apiFetch<PricingRule>("/api/v1/pricing/rules", { method: "POST", body: { ...body } });
}

export function setPricingRuleEnabled(id: string, enabled: boolean): Promise<PricingRule> {
  return apiFetch<PricingRule>(`/api/v1/pricing/rules/${id}`, { method: "PATCH", body: { enabled } });
}
