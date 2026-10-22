/** Customer list and record (SPEC-FE-073), mirroring backend app/schemas/customer.py (SPEC-BE-109). */
import type { ConfirmationState, StatusEvent } from "./orders";

export interface CustomerListItem {
  id: string;
  first_name: string | null;
  last_name: string | null;
  email: string | null;
  phone: string | null;
  created_at: string;
  order_count: number;
  lifetime_value: number;
  currency: string | null;
  last_order_at: string | null;
}

export interface CustomerProfile {
  id: string;
  name: string | null;
  first_name: string | null;
  last_name: string | null;
  phone: string | null;
  email: string | null;
  address: Record<string, string> | null;
  city: string | null;
  country_code: string | null;
  tags: string[];
  accepts_marketing: boolean;
  sms_opt_out: boolean;
  order_count: number;
  lifetime_value: number;
  currency: string;
  created_at: string;
}

export interface CustomerOrderRow {
  id: string;
  order_number: string;
  status: string;
  confirmation_state: ConfirmationState;
  total: number;
  currency: string;
  placed_at: string;
  tracking_number: string | null;
  tracking_url: string | null;
}

export interface CustomerHistoryEvent extends StatusEvent {
  order_id: string;
  order_number: string;
}

export interface CustomerSms {
  id: string;
  direction: "outbound" | "inbound";
  kind: string;
  body: string;
  status: string;
  interpreted: string | null;
  error: string | null;
  at: string;
  order_number: string | null;
}

export interface CustomerConversation {
  id: string;
  channel: string;
  status: string;
  topic: string | null;
  last_message: string | null;
  last_message_at: string | null;
  unread: number;
}

export interface CustomerRecord {
  customer: CustomerProfile;
  current_order: CustomerOrderRow | null;
  orders: CustomerOrderRow[];
  status_history: CustomerHistoryEvent[];
  sms: CustomerSms[];
  conversations: CustomerConversation[];
}

export interface CustomerPatch {
  first_name?: string;
  last_name?: string;
  email?: string | null;
  phone?: string | null;
  address?: Record<string, string> | null;
  city?: string;
  tags?: string[];
  accepts_marketing?: boolean;
}
