/** Unified inbox (SPEC-FE-076), mirroring app/schemas/inbox.py (SPEC-BE-112). */
import type { ConfirmationState } from "./orders";

export interface InboxChannel {
  /** local:<channel> | local:whatsapp:<integration id> | socialapi:<account id> */
  key: string;
  platform: string;
  source: "socialapi" | "whatsapp_cloud" | "twilio" | "local";
  account_id: string | null;
  name: string;
  status: "connected" | "needs_attention";
  problem: string | null;
  can_send: boolean;
  can_send_media: boolean;
}

export interface InboxConversation {
  /** local:<uuid> | socialapi:<account>:<id> */
  key: string;
  channel: string;
  platform: string;
  conversation_id: string;
  customer: { id: string | null; name: string | null; handle: string | null; phone: string | null; email: string | null; avatar: string | null };
  last_message: { preview: string | null; at: string | null; direction: string | null };
  unread: number;
  status: string | null;
  assignee_id: string | null;
  assignee_name: string | null;
  topic: string | null;
  /** Demo data, never a synced conversation. */
  is_sample: boolean;
}

export interface InboxConversationList {
  items: InboxConversation[];
  next_cursor: string | null;
  channel_errors: { channel: string; message: string }[];
}

export interface InboxMessage {
  id: string;
  direction: "inbound" | "outbound" | string;
  sender: string | null;
  body: string | null;
  attachments: { kind?: string | null; url?: string | null; name?: string | null; media_id?: string | null }[];
  sent_at: string | null;
  /** pending | sent | delivered | read | failed | not_sent; null for the customer's messages. */
  delivery: string | null;
  error: string | null;
  is_ai_draft: boolean;
}

export interface InboxCustomerPanel {
  id: string;
  name: string | null;
  phone: string | null;
  email: string | null;
  order_count: number;
  lifetime_value: number;
  currency: string;
  orders: { id: string; order_number: string; status: string; confirmation_state: ConfirmationState; total: number; currency: string }[];
}

export interface InboxThread {
  conversation: InboxConversation;
  customer: InboxCustomerPanel | null;
  can_send: boolean;
  can_send_media: boolean;
  send_blocked_reason: string | null;
  items: InboxMessage[];
  next_cursor: string | null;
}

export interface InboxFilters {
  channel: string;
  q: string;
  status: "open" | "pending" | "resolved" | "archived" | "";
  unread: boolean;
  mine: boolean;
}

export interface WhatsAppStatus {
  available: boolean;
  reason: string | null;
  accounts: { id: string; phone_number: string | null; name: string | null; status: string; last_error: string | null; connected_at: string | null }[];
}

export interface WhatsAppConnectInfo {
  app_id: string;
  config_id: string;
  graph_version: string;
  state: string;
}
