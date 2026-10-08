/**
 * Inventory API (SPEC-FE-027). Reading is open to any role; adjusting stock
 * requires manager or above (403 otherwise).
 */
import type { InventoryAdjust, InventoryItem } from "../types/inventory";
import { apiFetch } from "./client";

export const inventoryKeys = {
  list: ["inventory", "list"] as const,
};

/** GET /api/v1/inventory: one row per variant and location, ordered by product. */
export function fetchInventory(): Promise<InventoryItem[]> {
  return apiFetch<InventoryItem[]>("/api/v1/inventory");
}

/** POST /api/v1/inventory/{id}/adjust: set a new absolute on-hand quantity. */
export function adjustInventory(id: string, body: InventoryAdjust): Promise<InventoryItem> {
  return apiFetch<InventoryItem>(`/api/v1/inventory/${id}/adjust`, { method: "POST", body: { ...body } });
}
