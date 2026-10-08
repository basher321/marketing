/**
 * Shipping types (SPEC-FE-029, SPEC-FE-040), mirroring backend
 * app/schemas/shipping.py (SPEC-BE-043, SPEC-BE-058).
 */

export type MethodType = "flat_rate" | "free_shipping" | "carrier_calculated" | "local_pickup" | "local_delivery";
export type Source = "local" | "shopify" | "woocommerce";

export interface RateConditions {
  min_subtotal?: number | null;
  max_subtotal?: number | null;
  min_weight_g?: number | null;
  max_weight_g?: number | null;
}

export interface ValidationIssue {
  zone_id: string | null;
  rate_id: string | null;
  zone: string | null;
  rate: string | null;
  code: string;
  message: string;
  severity: "error" | "warning";
}

export interface ValidationResult {
  ok: boolean;
  issues: ValidationIssue[];
}

export interface ShippingRate {
  id: string;
  name: string;
  carrier: string;
  /** Major units of the tenant currency; 0 = free. */
  rate: number;
  /** Free shipping at or above this order total; null = never. */
  free_over: number | null;
  sla_days_min: number | null;
  sla_days_max: number | null;
  /** "HH:MM" local time of day, or null. */
  cutoff_time: string | null;
  active: boolean;
  source: Source;
  external_id: string | null;
  method_type: MethodType;
  conditions: RateConditions;
  metadata: Record<string, unknown>;
  validation: ValidationResult | null;
  /** The store's API can't apply edits to this method. */
  read_only: boolean;
}

export interface ShippingZone {
  id: string;
  name: string;
  /** ISO 3166-1 alpha-2, e.g. ["BD"]. */
  country_codes: string[];
  /** [] = the whole country. */
  regions: string[];
  active: boolean;
  rates: ShippingRate[];
  source: Source;
  external_id: string | null;
  rest_of_world: boolean;
  validation: ValidationResult | null;
}

export interface ShippingZoneList {
  /** Tenant currency (ISO 4217) for every amount. */
  currency: string;
  zones: ShippingZone[];
}

export interface ShippingZoneCreate {
  name: string;
  country_codes: string[];
  regions: string[];
}

export interface ShippingRateCreate {
  name: string;
  carrier: string;
  rate: number;
  free_over: number | null;
  sla_days_min: number | null;
  sla_days_max: number | null;
  /** "HH:MM" or null. */
  cutoff_time: string | null;
  method_type?: MethodType;
  conditions?: RateConditions | null;
  pickup_instructions?: string | null;
  pickup_location?: string | null;
}

export interface ShippingRateUpdate {
  active?: boolean;
  name?: string;
  rate?: number;
  free_over?: number | null;
  conditions?: RateConditions | null;
  sla_days_min?: number | null;
  sla_days_max?: number | null;
}

export interface ShippingStatus {
  store: { provider: string; connected: boolean; account_name: string | null } | null;
  detected: boolean | null;
  mode: "synced" | "local" | "setup_required";
  last_sync_at: string | null;
  last_sync_status: "ok" | "partial" | "failed" | null;
  errors: { message: string; at?: string }[];
  counts: { zones?: number; methods?: number };
  unsupported: string[];
}

export interface PreviewMethod {
  name: string;
  method_type: MethodType;
  rate: number | null;
  conditions: RateConditions;
  active: boolean;
}

export interface DetectResult {
  detected: boolean;
  provider: string;
  currency: string | null;
  preview: {
    zones: { name: string; country_codes: string[]; regions: string[]; rest_of_world: boolean; methods: PreviewMethod[] }[];
  };
  unsupported: string[];
  warnings: string[];
}

export interface SyncResult {
  created: number;
  updated: number;
  deactivated: number;
  errors: string[];
  last_sync_at: string;
  zones: ShippingZone[];
}

export interface SetupMethod extends ShippingRateCreate {
  method_type: MethodType;
}

export interface ShippingSetup {
  zones: { name: string; country_codes: string[]; regions: string[]; methods: SetupMethod[] }[];
  push_to_store: boolean;
}
