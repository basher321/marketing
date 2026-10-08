/**
 * Pricing rule types (SPEC-FE-028), mirroring backend PricingRuleList /
 * PricingRuleRead / PricingRuleCreate (app/schemas/pricing.py, SPEC-BE-042).
 */

/** Live pricing_rule_type enum. */
export type PricingRuleType = "percent_discount" | "fixed_discount" | "tiered" | "fixed_price";
/** Live pricing_scope enum. */
export type PricingScope = "sku" | "category" | "all" | "tag";
/** Derived by the backend at request time. */
export type PricingRuleState = "active" | "scheduled" | "expired" | "disabled";

export interface PricingRule {
  id: string;
  name: string;
  description: string | null;
  rule_type: PricingRuleType;
  /** Percentage for percent_discount; major units of the tenant currency otherwise. */
  value: number;
  scope: PricingScope;
  /** Number of products/categories/tags the rule targets; 0 for "all". */
  scope_count: number;
  min_quantity: number | null;
  /** ISO 8601 UTC. */
  starts_at: string | null;
  ends_at: string | null;
  priority: number;
  enabled: boolean;
  state: PricingRuleState;
}

export interface PricingRuleList {
  count: number;
  /** Tenant currency (ISO 4217) for fixed amounts. */
  currency: string;
  items: PricingRule[];
}

export interface PricingRuleCreate {
  name: string;
  description: string | null;
  rule_type: "percent_discount" | "fixed_discount" | "fixed_price";
  value: number;
  scope: "all" | "sku";
  /** Product ids when scope is "sku"; empty for "all". */
  product_ids: string[];
  min_quantity: number | null;
  /** ISO 8601 with offset. */
  starts_at: string | null;
  ends_at: string | null;
  priority: number;
}
