/**
 * Orders types (SPEC-FE-026, SPEC-FE-073), mirroring backend app/schemas/order.py
 * (SPEC-BE-041 list, SPEC-BE-107 lifecycle, SPEC-BE-108 confirmation SMS,
 * SPEC-BE-111 payments).
 */

/** Live order_status enum (SPEC-BE-107 added awaiting_confirmation and returned). */
export const ORDER_STATUSES = [
  "pending",
  "awaiting_confirmation",
  "confirmed",
  "processing",
  "shipped",
  "delivered",
  "returned",
  "cancelled",
  "refunded",
] as const;
export type OrderStatus = (typeof ORDER_STATUSES)[number];

/** The SMS reply position (SPEC-BE-107 FR7). */
export type ConfirmationState = "not_sent" | "waiting" | "confirmed" | "cancelled";

export interface OrderListItem {
  id: string;
  order_number: string;
  /** ISO 8601 UTC. */
  placed_at: string;
  /** Full name, else email, else phone; null for a guest order. */
  customer_name: string | null;
  /** Live channel_type value. */
  channel: string;
  /** SUM of the order's item quantities. */
  item_count: number;
  /** Major currency units. */
  total: number;
  currency: string;
  payment_method: string | null;
  payment_status: string | null;
  status: OrderStatus;
  tracking_number: string | null;
  confirmation_state: ConfirmationState;
}

export interface OrderList {
  /** Every matching order, before limit/offset. */
  total: number;
  items: OrderListItem[];
}

export interface OrderListParams {
  status: OrderStatus | null;
  q: string;
  limit: number;
  offset: number;
}

export interface OrderLine {
  id: string;
  variant_id: string | null;
  product_id: string | null;
  sku: string | null;
  title: string | null;
  variant: string | null;
  quantity: number;
  unit_price: number;
  line_total: number;
  /** Cost saved when the order was placed; null = no cost set. */
  unit_cost: number | null;
}

export interface StatusEvent {
  id: string;
  from_status: string | null;
  to_status: string;
  /** user | system | customer_sms | store_sync */
  actor_type: string;
  actor_name: string | null;
  reason: string | null;
  at: string;
}

export interface SmsBrief {
  id: string;
  direction: "outbound" | "inbound";
  kind: string;
  body: string;
  status: string;
  interpreted: string | null;
  error: string | null;
  at: string;
}

export interface OrderConfirmation {
  state: ConfirmationState;
  last_sms: SmsBrief | null;
  sms_count: number;
  replies: SmsBrief[];
  can_send: boolean;
  send_blocked_reason: string | null;
}

export interface OrderDetail {
  id: string;
  order_number: string;
  status: OrderStatus;
  channel: string;
  placed_at: string;
  currency: string;
  subtotal: number;
  discount: number;
  shipping: number;
  tax: number;
  total: number;
  payment_method: string | null;
  payment_status: string | null;
  tracking_number: string | null;
  tracking_url: string | null;
  shipping_address: Record<string, unknown>;
  notes: string | null;
  tags: string[];
  fulfilled_at: string | null;
  delivered_at: string | null;
  cancelled_at: string | null;
  customer: { id: string; name: string | null; phone: string | null; email: string | null } | null;
  items: OrderLine[];
  status_history: StatusEvent[];
  confirmation: OrderConfirmation;
  /** Statuses this user may set now (from the backend's rules). */
  allowed_next: OrderStatus[];
}

export interface OrderCreate {
  customer: { id?: string; name?: string; phone?: string; email?: string; address?: Record<string, string> };
  items: { variant_id?: string; product_id?: string; quantity: number; unit_price?: string }[];
  discount?: string;
  shipping?: string;
  tax?: string;
  payment_method?: string;
  payment_status?: "unpaid" | "paid" | "cod";
  channel?: string;
  notes?: string;
  shipping_address?: Record<string, string>;
}

export interface OrderStatusChange {
  to: OrderStatus;
  reason?: string;
  tracking_number?: string;
  tracking_url?: string;
}

export interface SmsSendResult {
  sms_id: string;
  status: string;
  order_status: OrderStatus;
}

export type PaymentStatus = "unpaid" | "paid" | "cod" | "refunded";

export interface PaymentRow {
  order_id: string;
  order_number: string;
  customer_name: string | null;
  placed_at: string;
  status: string;
  payment_method: string | null;
  payment_status: string | null;
  reference: string | null;
  total: number;
  currency: string;
}

export interface PaymentList {
  total: number;
  sums: Record<string, number>;
  items: PaymentRow[];
}
