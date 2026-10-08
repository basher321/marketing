/**
 * Inventory types (SPEC-FE-027), mirroring backend InventoryRead / InventoryAdjust
 * (app/schemas/inventory.py, SPEC-BE-005 + its 2026-09-30 amendment).
 */

export interface InventoryItem {
  id: string;
  variant_id: string;
  location_id: string;
  on_hand: number;
  committed: number;
  /** Database-generated on_hand - committed. */
  available: number;
  reorder_point: number;
  /** The variant's SKU (falls back to the product SKU). */
  sku: string;
  product_title: string;
  /** Variant attribute values joined with " / " (e.g. "L / Blue"); null when none. */
  variant_label: string | null;
  location_name: string;
  /** The backend's own low-stock flag (available <= reorder_point). */
  low_stock: boolean;
}

export interface InventoryAdjust {
  /** New absolute on-hand quantity (>= 0). */
  on_hand: number;
  reason?: string | null;
}
