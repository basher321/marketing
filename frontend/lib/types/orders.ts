/**
 * Orders list types (SPEC-FE-026), mirroring backend OrderList / OrderListItem
 * (app/schemas/order.py, SPEC-BE-041).
 */

/** Live order_status enum. */
export const ORDER_STATUSES = [
  "pending",
  "confirmed",
  "processing",
  "shipped",
  "delivered",
  "cancelled",
  "refunded",
] as const;
export type OrderStatus = (typeof ORDER_STATUSES)[number];

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
