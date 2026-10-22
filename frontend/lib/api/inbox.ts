import type {
  InboxChannel,
  InboxConversation,
  InboxConversationList,
  InboxCustomerPanel,
  InboxFilters,
  InboxMessage,
  InboxThread,
  WhatsAppConnectInfo,
  WhatsAppStatus,
} from "../types/inbox";
import { apiFetch } from "./client";

export const inboxKeys = {
  all: ["inbox"] as const,
  channels: ["inbox", "channels"] as const,
  list: (f: InboxFilters) => ["inbox", "list", f] as const,
  thread: (key: string) => ["inbox", "thread", key] as const,
  whatsapp: ["inbox", "whatsapp"] as const,
};

const k = (key: string) => encodeURIComponent(key);

/** GET /inbox/channels (SPEC-BE-112 FR1). */
export function fetchInboxChannels(): Promise<{ items: InboxChannel[] }> {
  return apiFetch<{ items: InboxChannel[] }>("/api/v1/inbox/channels");
}

/** GET /inbox/conversations (FR2). */
export function fetchInboxConversations(f: InboxFilters, cursor?: string | null): Promise<InboxConversationList> {
  const s = new URLSearchParams();
  if (f.channel && f.channel !== "all") s.set("channel", f.channel);
  if (f.q) s.set("q", f.q);
  if (f.status) s.set("status", f.status);
  if (f.unread) s.set("unread", "true");
  if (f.mine) s.set("assignee", "me");
  if (cursor) s.set("cursor", cursor);
  return apiFetch<InboxConversationList>(`/api/v1/inbox/conversations?${s.toString()}`);
}

/** GET /inbox/conversations/{key}/messages (FR3); opening marks the customer's messages read. */
export function fetchInboxThread(key: string): Promise<InboxThread> {
  return apiFetch<InboxThread>(`/api/v1/inbox/conversations/${k(key)}/messages`);
}

/** POST /inbox/conversations/{key}/messages (FR4). */
export function sendInboxMessage(key: string, body: string, media_ids: string[] = []): Promise<{ message: InboxMessage }> {
  return apiFetch(`/api/v1/inbox/conversations/${k(key)}/messages`, { method: "POST", body: { body, media_ids } });
}

/** PATCH /inbox/conversations/{key} (FR5; local conversations only). */
export function updateInboxConversation(
  key: string,
  body: { status?: string; assignee_id?: string | null },
): Promise<InboxConversation> {
  return apiFetch<InboxConversation>(`/api/v1/inbox/conversations/${k(key)}`, { method: "PATCH", body });
}

/** POST /inbox/conversations/{key}/link (FR6). */
export function linkInboxCustomer(key: string, customer_id: string): Promise<InboxCustomerPanel> {
  return apiFetch<InboxCustomerPanel>(`/api/v1/inbox/conversations/${k(key)}/link`, { method: "POST", body: { customer_id } });
}

/** WhatsApp Business connection (FR7). */
export function fetchWhatsAppStatus(): Promise<WhatsAppStatus> {
  return apiFetch<WhatsAppStatus>("/api/v1/integrations/whatsapp");
}

export function fetchWhatsAppConnect(): Promise<WhatsAppConnectInfo> {
  return apiFetch<WhatsAppConnectInfo>("/api/v1/integrations/whatsapp/connect");
}

export function postWhatsAppCallback(body: { code: string; state: string; waba_id: string; phone_number_id: string }): Promise<WhatsAppStatus> {
  return apiFetch<WhatsAppStatus>("/api/v1/integrations/whatsapp/callback", { method: "POST", body });
}

export function disconnectWhatsApp(id: string): Promise<void> {
  return apiFetch<void>(`/api/v1/integrations/whatsapp/${encodeURIComponent(id)}`, { method: "DELETE" });
}
