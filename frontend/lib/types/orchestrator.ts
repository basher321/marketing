/**
 * Command Chat types (SPEC-FE-008, SPEC-FE-041), mirroring the backend's
 * app/schemas/orchestrator.py field for field. Datetimes are ISO-8601 strings.
 *
 * Since SPEC-BE-059 every AI reply carries its kind: a plan reply and its
 * later result summary link to the plan (plan_id), and a clarifying question
 * lists what it is waiting for, so plan cards also render after a reload.
 */
export type MessageKind = "message" | "plan" | "clarification" | "summary";

export interface ResultItem {
  index: number;
  label: string;
  status: string;
  summary: string | null;
  link: string | null;
  data: Record<string, unknown>[] | null;
  /** A generated image/video (SPEC-BE-092 / SPEC-FE-057); its URL comes from GET /media/{id}. */
  media: { id: string; kind: "image" | "video" } | null;
}

export interface ChatMessage {
  id: string;
  sender: "user" | "ai";
  body: string;
  sent_at: string;
  kind: MessageKind;
  plan_id: string | null;
  waiting_for: string[];
  results: ResultItem[];
  /** SPEC-BE-095: a user message that came from a voice command. */
  voice: boolean;
  voice_language: string | null;
}

export type Module = "ecommerce" | "shipping" | "marketing" | "meta" | "organic" | "workflows" | "general";
export type Risk = "read" | "draft" | "change" | "spend";
export type ApprovalMode = "auto" | "approval" | "owner";
export type ActionStatus =
  | "pending_approval"
  | "approved"
  | "running"
  | "succeeded"
  | "failed"
  | "skipped"
  | "rejected";

export interface PlanAction {
  index: number;
  type: string;
  label: string;
  module: Module;
  risk: Risk;
  approval_mode: ApprovalMode;
  description: string;
  params: Record<string, unknown>;
  depends_on: number[];
  cost_estimate_cents: number | null;
  approval_id: string | null;
  status: ActionStatus;
  result: (Record<string, unknown> & { summary?: string; link?: string }) | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface PlanRead {
  id: string;
  status: string;
  title: string;
  estimated_cost_cents: number | null;
  created_at: string;
  /** Stored before SPEC-BE-059: no per-step status (use the approvals panel). */
  legacy: boolean;
  actions: PlanAction[];
  dropped_count: number;
}

/** POST /orchestrator/messages (201): the stored user message plus the AI reply and plan. */
export interface SendMessageResult extends ChatMessage {
  reply: ChatMessage;
  plan: PlanRead | null;
}

/** POST /orchestrator/voice/transcribe (SPEC-BE-095). */
export interface TranscriptRead {
  text: string;
  language: string | null;
  provider: string;
}

/** POST /orchestrator/messages/{id}/speech: base64 audio plus the spoken text. */
export interface SpeechRead {
  audio: string;
  mime: string;
  text: string;
  language: string | null;
  provider: string;
  note: string | null;
}
