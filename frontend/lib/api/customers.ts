import type { CustomerListItem, CustomerPatch, CustomerRecord } from "../types/customers";
import { apiFetch } from "./client";

export const customerKeys = {
  all: ["customers"] as const,
  list: (q: string, offset: number) => ["customers", "list", q, offset] as const,
  record: (id: string) => ["customers", "record", id] as const,
};

/**
 * GET /customers?q&limit&offset (SPEC-BE-109 FR1). The list keeps its SPEC-BE-007
 * shape (an array); the page asks for one extra row to know whether a next page exists.
 */
export function fetchCustomers(q: string, limit: number, offset: number): Promise<CustomerListItem[]> {
  const search = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (q) search.set("q", q);
  return apiFetch<CustomerListItem[]>(`/api/v1/customers?${search.toString()}`);
}

/** GET /customers/{id} (SPEC-BE-109 FR2). */
export function fetchCustomer(id: string): Promise<CustomerRecord> {
  return apiFetch<CustomerRecord>(`/api/v1/customers/${encodeURIComponent(id)}`);
}

/** PATCH /customers/{id} (SPEC-BE-109 FR3). */
export function updateCustomer(id: string, body: CustomerPatch): Promise<CustomerRecord> {
  return apiFetch<CustomerRecord>(`/api/v1/customers/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: body as unknown as Record<string, unknown>,
  });
}
