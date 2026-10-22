/**
 * Product catalog types (SPEC-FE-011), mirroring backend ProductListItem
 * (app/schemas/product.py, SPEC-BE-008 + its 2026-09-29 stock amendment).
 */

/** Live product_status enum. */
export type ProductStatus = "draft" | "active" | "archived" | "out_of_stock";

export interface ProductListItem {
  id: string;
  sku: string;
  title: string;
  /** Major currency units (e.g. 790.0). */
  price: number;
  /** ISO 4217 code, e.g. "BDT". */
  currency: string;
  /** Live channel_type values. */
  channels: string[];
  status: ProductStatus;
  /** ISO 8601 UTC. */
  updated_at: string;
  /** Available units over all variants/locations; null when not tracked. */
  stock: number | null;
  /** The backend's own low-stock flag (available <= reorder_point). */
  low_stock: boolean;
  /** SPEC-BE-111: the product's category. */
  category_id: string | null;
  category: string | null;
}
