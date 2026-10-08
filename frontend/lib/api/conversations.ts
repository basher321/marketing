/**
 * Conversation AI-reply-draft API (SPEC-FE-014), backed by the real routes in
 * backend app/api/v1/conversations.py (SPEC-BE-026 / SPEC-BE-028). All five
 * require the agent role or higher.
 *
 * Errors arrive as ApiError with the backend's own message: 404 conversation
 * not found, 409 "No pending draft for this conversation." (edit / send /
 * handoff), 400 empty draft on send, 422 / 503 on generate.
 */
import type {
  DraftEdit,
  DraftResponse,
  DraftSendResult,
  HandoffResult,
  InboxList,
} from "../types/conversations";
import { apiFetch } from "./client";

export const conversationKeys = {
  all: ["conversations"] as const,
  // SPEC-FE-013's conversations-list query must use this key so a sent reply
  // or handoff here refreshes the Open Conversations table.
  list: ["conversations", "list"] as const,
  draft: (conversationId: string) => ["conversations", conversationId, "draft"] as const,
};

// Open Conversations table (SPEC-FE-013, backend SPEC-BE-007): the tenant's
// open/pending conversations, newest customer message first. Any role.
export function fetchConversations(): Promise<InboxList> {
  return apiFetch<InboxList>("/api/v1/conversations");
}

function draftPath(conversationId: string): string {
  return `/api/v1/conversations/${encodeURIComponent(conversationId)}`;
}

export function fetchDraft(conversationId: string): Promise<DraftResponse> {
  return apiFetch<DraftResponse>(`${draftPath(conversationId)}/draft`);
}

export function editDraft(conversationId: string, body: string): Promise<DraftResponse> {
  const payload: DraftEdit = { body };
  return apiFetch<DraftResponse>(`${draftPath(conversationId)}/draft`, {
    method: "PATCH",
    body: { ...payload },
  });
}

// No request body: the backend sends the stored draft as-is, so an edit must
// be saved with editDraft() first.
export function sendDraft(conversationId: string): Promise<DraftSendResult> {
  return apiFetch<DraftSendResult>(`${draftPath(conversationId)}/draft/send`, {
    method: "POST",
  });
}

export function handoffConversation(conversationId: string): Promise<HandoffResult> {
  return apiFetch<HandoffResult>(`${draftPath(conversationId)}/handoff`, { method: "POST" });
}

// Replaces any existing pending draft server-side (SPEC-BE-028).
export function generateDraft(conversationId: string): Promise<DraftResponse> {
  return apiFetch<DraftResponse>(`${draftPath(conversationId)}/draft/generate`, {
    method: "POST",
  });
}
