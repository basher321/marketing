import type { OrderList, OrderListParams } from "../types/orders";
import { apiFetch } from "./client";

export const orderKeys = {
  list: (params: OrderListParams) => ["orders", "list", params] as const,
};

/**
 * GET /api/v1/orders (SPEC-BE-041): the tenant's orders, newest first,
 * optionally filtered by status and a search over order number / customer.
 */
export function fetchOrders(params: OrderListParams): Promise<OrderList> {
  const search = new URLSearchParams({ limit: String(params.limit), offset: String(params.offset) });
  if (params.status) search.set("status", params.status);
  if (params.q) search.set("q", params.q);
  return apiFetch<OrderList>(`/api/v1/orders?${search.toString()}`);
}
