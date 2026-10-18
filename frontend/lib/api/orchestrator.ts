/**
 * Command Chat API (SPEC-FE-008, SPEC-FE-041) against the backend's
 * app/api/v1/orchestrator.py.
 */
import type {
  ChatList,
  ChatMessage,
  ChatRead,
  FileRead,
  JobSchedule,
  PlanRead,
  ProjectRead,
  SendMessageResult,
  SpeechRead,
  TranscriptRead,
} from "../types/orchestrator";
import { getAuthToken } from "../auth/token";
import { ApiError } from "../types/common";
import { apiFetch } from "./client";

const BASE = "/api/v1/orchestrator";

export const orchestratorKeys = {
  // The prefix of every chat's messages: invalidating it refreshes the open chat (SPEC-FE-066).
  messages: ["orchestrator", "messages"] as const,
  chatMessages: (chatId: string | null) => ["orchestrator", "messages", chatId ?? "new"] as const,
  plan: (id: string) => ["orchestrator", "plan", id] as const,
  chats: ["orchestrator", "chats"] as const,
  chatList: (q: string, archived: boolean, projectId: string | null) => ["orchestrator", "chats", q, archived, projectId ?? ""] as const,
  chat: (id: string) => ["orchestrator", "chat", id] as const,
  projects: ["orchestrator", "projects"] as const,
  project: (id: string) => ["orchestrator", "project", id] as const,
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
export function sendMessage(
  body: string,
  voice?: { language: string | null },
  fileIds: string[] = [],
  where: { chatId?: string | null; projectId?: string | null } = {},
): Promise<SendMessageResult> {
  // SPEC-BE-095: `voice` marks a reviewed voice transcript; it is planned like typed text.
  // SPEC-BE-096: file_ids are attachments uploaded with uploadChatFile.
  // SPEC-BE-099: into this chat, or a new one (in a project when given).
  const payload: Record<string, unknown> = { body };
  if (voice) payload.voice = voice;
  if (fileIds.length) payload.file_ids = fileIds;
  if (where.chatId) payload.chat_id = where.chatId;
  else {
    payload.new_chat = true;
    if (where.projectId) payload.project_id = where.projectId;
  }
  return apiFetch<SendMessageResult>(`${BASE}/messages`, { method: "POST", body: payload });
}

export function fetchPlan(id: string): Promise<PlanRead> {
  return apiFetch<PlanRead>(`${BASE}/plans/${encodeURIComponent(id)}`);
}

export function editPlanAction(planId: string, index: number, params: Record<string, unknown>, runAt?: string | null): Promise<PlanRead> {
  return apiFetch<PlanRead>(`${BASE}/plans/${encodeURIComponent(planId)}/actions/${index}`, {
    method: "PATCH",
    body: runAt ? { params, run_at: runAt } : { params },
  });
}

export function retryPlanAction(planId: string, index: number): Promise<PlanRead> {
  return apiFetch<PlanRead>(`${BASE}/plans/${encodeURIComponent(planId)}/actions/${index}/retry`, { method: "POST" });
}

/** SPEC-BE-102: take one queued / waiting / needs-input / failed job out; its dependents are skipped too. */
export function skipPlanAction(planId: string, index: number): Promise<PlanRead> {
  return apiFetch<PlanRead>(`${BASE}/plans/${encodeURIComponent(planId)}/actions/${index}/skip`, { method: "POST" });
}

/** "Start over": the next message is planned without the pending draft. */
export function discardDraft(chatId?: string | null): Promise<void> {
  return apiFetch<void>(`${BASE}/draft/discard${chatId ? `?chat_id=${encodeURIComponent(chatId)}` : ""}`, { method: "POST" });
}

/** A voice recording -> its text and language, on the company's own AI keys (SPEC-BE-095). */
export function transcribeVoice(audio: Blob): Promise<TranscriptRead> {
  const form = new FormData();
  const ext = audio.type.includes("mp4") ? "m4a" : audio.type.includes("ogg") ? "ogg" : "webm";
  form.append("audio", audio, `voice.${ext}`);
  // The browser's languages: a hint that steers transcription, never a rule (SPEC-BE-095 Amendment C).
  if (typeof navigator !== "undefined" && navigator.languages?.length) form.append("languages", navigator.languages.slice(0, 6).join(","));
  return apiFetch<TranscriptRead>(`${BASE}/voice/transcribe`, { method: "POST", body: form });
}

/** An AI reply read aloud in `language` (translated for speech when needed). */
export function speakMessage(id: string, language: string | null): Promise<SpeechRead> {
  return apiFetch<SpeechRead>(`${BASE}/messages/${encodeURIComponent(id)}/speech`, { method: "POST", body: { language } });
}

// ---- Chat attachments (SPEC-BE-096 / SPEC-FE-064) ----

/**
 * Uploads one file with upload progress (XMLHttpRequest, since fetch has no
 * upload progress). Same base URL and bearer token as apiFetch; on a 401
 * (expired access token) it retries once through apiFetch, which refreshes
 * the token, without progress.
 */
export function uploadChatFile(file: File, onProgress: (fraction: number) => void, signal?: AbortSignal): Promise<FileRead> {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!baseUrl) return Promise.reject(new Error("NEXT_PUBLIC_API_BASE_URL is not set."));
  const url = `${baseUrl.replace(/\/+$/, "")}${BASE}/files`;
  const form = () => {
    const f = new FormData();
    f.append("file", file, file.name);
    return f;
  };
  return new Promise<FileRead>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    const token = getAuthToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      let body: unknown = undefined;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        body = xhr.responseText;
      }
      if (xhr.status === 401) {
        apiFetch<FileRead>(`${BASE}/files`, { method: "POST", body: form() }).then(resolve, reject);
        return;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body as FileRead);
        return;
      }
      const msg =
        body && typeof body === "object" && typeof (body as { error?: unknown }).error === "string"
          ? (body as { error: string }).error
          : body && typeof body === "object" && typeof (body as { detail?: unknown }).detail === "string"
            ? (body as { detail: string }).detail
            : xhr.status === 413
              ? "The file can be at most 100 MB."
              : `HTTP ${xhr.status}`;
      reject(new ApiError(xhr.status, msg, body));
    };
    xhr.onerror = () => reject(new ApiError(0, "Couldn't reach the server.", undefined));
    xhr.onabort = () => reject(new ApiError(0, "Upload cancelled.", undefined));
    signal?.addEventListener("abort", () => xhr.abort());
    xhr.send(form());
  });
}

// ---- Job lists (SPEC-BE-097 / SPEC-FE-065) ----
const plan = (id: string) => `${BASE}/plans/${encodeURIComponent(id)}`;

export function removeJob(planId: string, index: number): Promise<PlanRead> {
  return apiFetch<PlanRead>(`${plan(planId)}/actions/${index}`, { method: "DELETE" });
}

export function addJob(
  planId: string,
  job: { type: string; params: Record<string, unknown>; description?: string; item_key?: string | null; depends_on?: number[]; run_at?: string | null },
): Promise<PlanRead> {
  return apiFetch<PlanRead>(`${plan(planId)}/actions`, { method: "POST", body: job });
}

export function editItem(planId: string, key: string, fields: Record<string, unknown>): Promise<PlanRead> {
  return apiFetch<PlanRead>(`${plan(planId)}/items/${encodeURIComponent(key)}`, { method: "PATCH", body: { fields } });
}

export function setJobSchedule(planId: string, schedule: JobSchedule): Promise<PlanRead> {
  return apiFetch<PlanRead>(`${plan(planId)}/schedule`, { method: "PATCH", body: { ...schedule } });
}

export function submitJobList(planId: string): Promise<PlanRead> {
  return apiFetch<PlanRead>(`${plan(planId)}/submit`, { method: "POST" });
}

export function controlJobList(planId: string, op: "pause" | "resume" | "cancel" | "retry-failed"): Promise<PlanRead> {
  return apiFetch<PlanRead>(`${plan(planId)}/${op}`, { method: "POST" });
}

// ---- Chat history and projects (SPEC-BE-099 / SPEC-FE-066) ----
export function fetchChatMessages(chatId: string): Promise<ChatMessage[]> {
  return apiFetch<ChatMessage[]>(`${BASE}/chats/${encodeURIComponent(chatId)}/messages`);
}

export function fetchChats(q = "", archived = false, projectId: string | null = null): Promise<ChatList> {
  const qs = new URLSearchParams();
  if (q.trim()) qs.set("q", q.trim());
  if (archived) qs.set("archived", "true");
  if (projectId) qs.set("project_id", projectId);
  qs.set("limit", "100");
  return apiFetch<ChatList>(`${BASE}/chats?${qs.toString()}`);
}

export function fetchChat(id: string): Promise<ChatRead> {
  return apiFetch<ChatRead>(`${BASE}/chats/${encodeURIComponent(id)}`);
}

export function updateChat(id: string, changes: { title?: string; pinned?: boolean; project_id?: string | null; archived?: boolean }): Promise<ChatRead> {
  return apiFetch<ChatRead>(`${BASE}/chats/${encodeURIComponent(id)}`, { method: "PATCH", body: changes });
}

export function deleteChat(id: string): Promise<void> {
  return apiFetch<void>(`${BASE}/chats/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function fetchProjects(): Promise<ProjectRead[]> {
  return apiFetch<ProjectRead[]>(`${BASE}/projects`);
}

export function fetchProject(id: string): Promise<ProjectRead> {
  return apiFetch<ProjectRead>(`${BASE}/projects/${encodeURIComponent(id)}`);
}

export function createProject(p: { name: string; description?: string; instructions?: string; emoji?: string }): Promise<ProjectRead> {
  return apiFetch<ProjectRead>(`${BASE}/projects`, { method: "POST", body: p });
}

export function updateProject(id: string, p: { name?: string; description?: string; instructions?: string; emoji?: string }): Promise<ProjectRead> {
  return apiFetch<ProjectRead>(`${BASE}/projects/${encodeURIComponent(id)}`, { method: "PATCH", body: p });
}

export function deleteProject(id: string): Promise<void> {
  return apiFetch<void>(`${BASE}/projects/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function addProjectFile(id: string, fileId: string): Promise<ProjectRead> {
  return apiFetch<ProjectRead>(`${BASE}/projects/${encodeURIComponent(id)}/files`, { method: "POST", body: { file_id: fileId } });
}

export function removeProjectFile(id: string, fileId: string): Promise<ProjectRead> {
  return apiFetch<ProjectRead>(`${BASE}/projects/${encodeURIComponent(id)}/files/${encodeURIComponent(fileId)}`, { method: "DELETE" });
}
