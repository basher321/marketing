import type { BusinessType, Category, EcommerceConfig, ProductDetail, ProductSave } from "../types/ecommerce";
import { apiFetch } from "./client";

export const ecommerceKeys = {
  config: ["ecommerce", "config"] as const,
  categories: ["ecommerce", "categories"] as const,
  product: (id: string) => ["ecommerce", "product", id] as const,
};

/** GET /ecommerce/config (SPEC-BE-111 FR3). */
export function fetchEcommerceConfig(): Promise<EcommerceConfig> {
  return apiFetch<EcommerceConfig>("/api/v1/ecommerce/config");
}

/** PUT /ecommerce/config (manager+): sets and confirms the business type. */
export function saveBusinessType(business_type: BusinessType): Promise<EcommerceConfig> {
  return apiFetch<EcommerceConfig>("/api/v1/ecommerce/config", { method: "PUT", body: { business_type } });
}

/** GET /products/{id} (SPEC-BE-111 FR5). */
export function fetchProduct(id: string): Promise<ProductDetail> {
  return apiFetch<ProductDetail>(`/api/v1/products/${encodeURIComponent(id)}`);
}

export function createProduct(body: ProductSave): Promise<ProductDetail> {
  return apiFetch<ProductDetail>("/api/v1/products", { method: "POST", body: body as Record<string, unknown> });
}

export function updateProduct(id: string, body: ProductSave): Promise<ProductDetail> {
  return apiFetch<ProductDetail>(`/api/v1/products/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: body as Record<string, unknown>,
  });
}

/** DELETE /products/{id}: archives (orders keep pointing at it). */
export function archiveProduct(id: string): Promise<void> {
  return apiFetch<void>(`/api/v1/products/${encodeURIComponent(id)}`, { method: "DELETE" });
}

/** GET /product-categories (SPEC-BE-111 FR6). */
export function fetchCategories(): Promise<Category[]> {
  return apiFetch<Category[]>("/api/v1/product-categories");
}

export function createCategory(name: string, description?: string): Promise<Category> {
  return apiFetch<Category>("/api/v1/product-categories", {
    method: "POST",
    body: { name, ...(description ? { description } : {}) },
  });
}

export function renameCategory(id: string, name: string): Promise<Category> {
  return apiFetch<Category>(`/api/v1/product-categories/${encodeURIComponent(id)}`, { method: "PATCH", body: { name } });
}
