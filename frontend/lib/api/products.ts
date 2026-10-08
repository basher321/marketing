import type { ProductListItem } from "../types/products";
import { apiFetch } from "./client";

export const productKeys = {
  list: ["products", "list"] as const,
};

/**
 * GET /api/v1/products (SPEC-BE-008): the tenant's non-deleted products, most
 * recently updated first, each with its stock and low-stock flag.
 */
export function fetchProducts(): Promise<ProductListItem[]> {
  return apiFetch<ProductListItem[]>("/api/v1/products");
}
