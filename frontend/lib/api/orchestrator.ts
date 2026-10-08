/**
 * Command Chat API (SPEC-FE-008, SPEC-FE-041) against the backend's
 * app/api/v1/orchestrator.py.
 */
import type { ChatMessage, PlanRead, SendMessageResult } from "../types/orchestrator";
import { apiFetch } from "./client";

const BASE = "/api/v1/orchestrator";

export const orchestratorKeys = {
  messages: ["orchestrator", "messages"] as const,
  plan: (id: string) => ["orchestrator", "plan", id] as const,
};

/** The tenant's chat history, oldest first (the backend's own ordering). */
export function fetchMessages(): Promise<ChatMessage[]> {
  return apiFetch<ChatMessage[]>(`${BASE}/messages`);
}

/**
 * Sends one message. The backend stores it and the AI reply, and returns the
 * plan (if any). Read/draft steps start right away in the background; the
 * plan card polls fetchPlan() for their status.
 */
export function sendMessage(body: string): Promise<SendMessageResult> {
  return apiFetch<SendMessageResult>(`${BASE}/messages`, { method: "POST", body: { body } });
}

export function fetchPlan(id: string): Promise<PlanRead> {
  return apiFetch<PlanRead>(`${BASE}/plans/${encodeURIComponent(id)}`);
}

export function editPlanAction(planId: string, index: number, params: Record<string, unknown>): Promise<PlanRead> {
  return apiFetch<PlanRead>(`${BASE}/plans/${encodeURIComponent(planId)}/actions/${index}`, {
    method: "PATCH",
    body: { params },
  });
}

export function retryPlanAction(planId: string, index: number): Promise<PlanRead> {
  return apiFetch<PlanRead>(`${BASE}/plans/${encodeURIComponent(planId)}/actions/${index}/retry`, { method: "POST" });
}

/** "Start over": the next message is planned without the pending draft. */
export function discardDraft(): Promise<void> {
  return apiFetch<void>(`${BASE}/draft/discard`, { method: "POST" });
}
