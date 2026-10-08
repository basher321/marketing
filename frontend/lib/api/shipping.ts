/**
 * Shipping API (SPEC-FE-029/040, backend SPEC-BE-043/058): zones and rates,
 * store detect / sync / status, guided setup and validation.
 * Reading is open to any role; every write requires manager or above (403 otherwise).
 */
import type {
  DetectResult,
  ShippingRate,
  ShippingRateCreate,
  ShippingRateUpdate,
  ShippingSetup,
  ShippingStatus,
  ShippingZone,
  ShippingZoneCreate,
  ShippingZoneList,
  SyncResult,
  ValidationResult,
} from "../types/shipping";
import { apiFetch } from "./client";

export const shippingKeys = {
  zones: ["shipping", "zones"] as const,
  status: ["shipping", "status"] as const,
};

export function fetchShippingZones(): Promise<ShippingZoneList> {
  return apiFetch<ShippingZoneList>("/api/v1/shipping/zones");
}

export function createShippingZone(body: ShippingZoneCreate): Promise<ShippingZone> {
  return apiFetch<ShippingZone>("/api/v1/shipping/zones", { method: "POST", body: { ...body } });
}

export function createShippingRate(zoneId: string, body: ShippingRateCreate): Promise<ShippingRate> {
  return apiFetch<ShippingRate>(`/api/v1/shipping/zones/${zoneId}/rates`, { method: "POST", body: { ...body } });
}

export function setShippingRateActive(rateId: string, active: boolean): Promise<ShippingRate> {
  return apiFetch<ShippingRate>(`/api/v1/shipping/rates/${rateId}`, { method: "PATCH", body: { active } });
}

export function updateShippingRate(rateId: string, body: ShippingRateUpdate): Promise<ShippingRate> {
  return apiFetch<ShippingRate>(`/api/v1/shipping/rates/${rateId}`, { method: "PATCH", body: { ...body } });
}

export function fetchShippingStatus(): Promise<ShippingStatus> {
  return apiFetch<ShippingStatus>("/api/v1/shipping/status");
}

export function detectShipping(): Promise<DetectResult> {
  return apiFetch<DetectResult>("/api/v1/shipping/detect", { method: "POST" });
}

export function syncShipping(): Promise<SyncResult> {
  return apiFetch<SyncResult>("/api/v1/shipping/sync", { method: "POST" });
}

export function validateShipping(): Promise<ValidationResult> {
  return apiFetch<ValidationResult>("/api/v1/shipping/validate", { method: "POST" });
}

export function setupShipping(body: ShippingSetup): Promise<SyncResult> {
  return apiFetch<SyncResult>("/api/v1/shipping/setup", { method: "POST", body: { ...body } });
}

/** Guided setup Review step: validates the draft, writes nothing. */
export function validateShippingSetup(body: ShippingSetup): Promise<ValidationResult> {
  return apiFetch<ValidationResult>("/api/v1/shipping/setup/validate", { method: "POST", body: { ...body } });
}
