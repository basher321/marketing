import type {
  OrderCreate,
  OrderDetail,
  OrderList,
  OrderListParams,
  OrderStatusChange,
  PaymentList,
  PaymentStatus,
  SmsSendResult,
} from "../types/orders";
import { apiFetch } from "./client";

export const orderKeys = {
  all: ["orders"] as const,
  list: (params: OrderListParams) => ["orders", "list", params] as const,
  detail: (id: string) => ["orders", "detail", id] as const,
  payments: (status: PaymentStatus | null, offset: number) => ["orders", "payments", status, offset] as const,
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

/** GET /orders/{id} (SPEC-BE-107 FR4). */
export function fetchOrder(id: string): Promise<OrderDetail> {
  return apiFetch<OrderDetail>(`/api/v1/orders/${encodeURIComponent(id)}`);
}

/** POST /orders (SPEC-BE-107 FR3). The same key again returns the first order. */
export function createOrder(body: OrderCreate, idempotencyKey: string): Promise<OrderDetail> {
  return apiFetch<OrderDetail>("/api/v1/orders", {
    method: "POST",
    body: body as unknown as Record<string, unknown>,
    headers: { "Idempotency-Key": idempotencyKey },
  });
}

/** POST /orders/{id}/status (SPEC-BE-107 FR5). */
export function changeOrderStatus(id: string, body: OrderStatusChange): Promise<OrderDetail> {
  return apiFetch<OrderDetail>(`/api/v1/orders/${encodeURIComponent(id)}/status`, {
    method: "POST",
    body: body as unknown as Record<string, unknown>,
  });
}

/** PATCH /orders/{id} (SPEC-BE-107 FR6): notes, tags, tracking, address, payment status. */
export function updateOrder(id: string, body: Record<string, unknown>): Promise<OrderDetail> {
  return apiFetch<OrderDetail>(`/api/v1/orders/${encodeURIComponent(id)}`, { method: "PATCH", body });
}

/** POST /orders/{id}/confirmation-sms (SPEC-BE-108 FR4). */
export function sendConfirmationSms(id: string): Promise<SmsSendResult> {
  return apiFetch<SmsSendResult>(`/api/v1/orders/${encodeURIComponent(id)}/confirmation-sms`, { method: "POST" });
}

/** GET /orders/payments (SPEC-BE-111 FR7). */
export function fetchPayments(status: PaymentStatus | null, offset: number, limit = 25): Promise<PaymentList> {
  const search = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (status) search.set("status", status);
  return apiFetch<PaymentList>(`/api/v1/orders/payments?${search.toString()}`);
}

/** POST /orders/{id}/payment (SPEC-BE-111 FR7). */
export function setPayment(
  id: string,
  body: { payment_status: PaymentStatus; method?: string; reference?: string },
): Promise<OrderDetail> {
  return apiFetch<OrderDetail>(`/api/v1/orders/${encodeURIComponent(id)}/payment`, { method: "POST", body });
}
