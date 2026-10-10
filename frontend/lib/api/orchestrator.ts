/**
 * Command Chat API (SPEC-FE-008, SPEC-FE-041) against the backend's
 * app/api/v1/orchestrator.py.
 */
import type { ChatMessage, PlanRead, SendMessageResult, SpeechRead, TranscriptRead } from "../types/orchestrator";
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
export function sendMessage(body: string, voice?: { language: string | null }): Promise<SendMessageResult> {
  // SPEC-BE-095: `voice` marks a reviewed voice transcript; it is planned like typed text.
  return apiFetch<SendMessageResult>(`${BASE}/messages`, { method: "POST", body: voice ? { body, voice } : { body } });
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

/** A voice recording -> its text and language, on the company's own AI keys (SPEC-BE-095). */
export function transcribeVoice(audio: Blob): Promise<TranscriptRead> {
  const form = new FormData();
  const ext = audio.type.includes("mp4") ? "m4a" : audio.type.includes("ogg") ? "ogg" : "webm";
  form.append("audio", audio, `voice.${ext}`);
  return apiFetch<TranscriptRead>(`${BASE}/voice/transcribe`, { method: "POST", body: form });
}

/** An AI reply read aloud in `language` (translated for speech when needed). */
export function speakMessage(id: string, language: string | null): Promise<SpeechRead> {
  return apiFetch<SpeechRead>(`${BASE}/messages/${encodeURIComponent(id)}/speech`, { method: "POST", body: { language } });
}
