/**
 * Command Chat types (SPEC-FE-008, SPEC-FE-041), mirroring the backend's
 * app/schemas/orchestrator.py field for field. Datetimes are ISO-8601 strings.
 *
 * Since SPEC-BE-059 every AI reply carries its kind: a plan reply and its
 * later result summary link to the plan (plan_id), and a clarifying question
 * lists what it is waiting for, so plan cards also render after a reload.
 */
/** progress = a job list's progress / failure line (SPEC-BE-097). */
export type MessageKind = "message" | "plan" | "clarification" | "summary" | "progress";

/** How to fix a failed step (SPEC-BE-100); href is an app page, or null. */
export interface FixHint {
  text: string;
  href: string | null;
  link_label: string | null;
}

export interface ResultItem {
  index: number;
  label: string;
  status: string;
  summary: string | null;
  link: string | null;
  fix?: FixHint | null;
  data: Record<string, unknown>[] | null;
  /** A generated image/video (SPEC-BE-092 / SPEC-FE-057); its URL comes from GET /media/{id}. */
  media: { id: string; kind: "image" | "video" } | null;
}

export interface ChatMessage {
  id: string;
  sender: "user" | "ai";
  body: string;
  sent_at: string;
  /** SPEC-BE-099: the chat this message belongs to. */
  chat_id?: string | null;
  kind: MessageKind;
  plan_id: string | null;
  waiting_for: string[];
  results: ResultItem[];
  /** SPEC-BE-095: a user message that came from a voice command. */
  voice: boolean;
  voice_language: string | null;
  /** SPEC-BE-095 Amendment C: the reply language the user asked for ("reply in English"). */
  reply_language?: string | null;
  /** SPEC-BE-096: files attached to a user message. */
  files: MessageFile[];
}

export interface MessageFile {
  id: string;
  name: string;
  kind: string;
  bytes: number;
  summary: string;
  media_ids: string[];
}

export type Module = "ecommerce" | "shipping" | "marketing" | "meta" | "organic" | "workflows" | "general";
export type Risk = "read" | "draft" | "change" | "spend";
export type ApprovalMode = "auto" | "approval" | "owner";
export type ActionStatus =
  | "draft"
  | "needs_input"
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
  fix?: FixHint | null;
  started_at: string | null;
  finished_at: string | null;
  /** Job lists (SPEC-BE-097) */
  item_key?: string | null;
  run_at?: string | null;
  missing?: { field: string; question: string }[];
}

export interface PlanItem {
  key: string;
  label: string;
  fields: Record<string, unknown>;
  media_ids: string[];
  source: string;
}

export type RunMode = "sequential" | "parallel" | "scheduled";

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
  /** Job lists (SPEC-BE-097) */
  job_list?: boolean;
  mode?: RunMode | null;
  start_at?: string | null;
  concurrency?: number | null;
  submitted_at?: string | null;
  paused_at?: string | null;
  items?: PlanItem[];
  schedule?: { mode?: RunMode; start_at?: string | null; item_daily_time?: string | null; item_every_minutes?: number | null; concurrency?: number | null };
  removed?: number[];
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

/** POST /orchestrator/files (SPEC-BE-096): a stored, extracted chat attachment. */
export interface FileRead {
  id: string;
  name: string;
  kind: "pdf" | "docx" | "xlsx" | "csv" | "text" | "json" | "image" | "zip";
  mime: string;
  bytes: number;
  status: string;
  summary: string;
  items_count: number;
  media_ids: string[];
  warnings: string[];
  created_at: string | null;
}

export interface JobSchedule {
  mode: RunMode;
  start_at?: string | null;
  concurrency?: number | null;
  item_daily_time?: string | null;
  item_every_minutes?: number | null;
  per_job?: Record<string, string>;
}

// ---- Chat history and projects (SPEC-BE-099 / SPEC-FE-066) ----
export interface ChatProjectRef {
  id: string;
  name: string;
  emoji: string;
}

export interface ChatRead {
  id: string;
  title: string;
  title_source: "auto" | "ai" | "manual";
  project: ChatProjectRef | null;
  pinned: boolean;
  archived: boolean;
  message_count: number;
  preview: string;
  last_message_at: string | null;
  created_at: string | null;
}

export interface ChatList {
  items: ChatRead[];
  has_more: boolean;
}

export interface ProjectRead {
  id: string;
  name: string;
  description: string;
  instructions: string;
  emoji: string;
  archived: boolean;
  chat_count: number;
  last_activity_at: string | null;
  created_at: string | null;
  files: FileRead[];
}
