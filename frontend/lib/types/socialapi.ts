/** SocialAPI.ai (SPEC-BE-083 / SPEC-FE-054): mirrors backend/app/schemas/socialapi.py. */

export type KeyStatus = {
  status: "not_configured" | "connected" | "error";
  key_masked: string | null;
  last_ok_at: string | null;
  last_error: string | null;
  account_count: number | null;
  docs_url: string;
};

export type SapiAccount = {
  id: string;
  platform: string;
  name: string | null;
  username: string | null;
  /** SocialAPI's own status: active | reconnect_required */
  status: string;
  avatar_url: string | null;
  /** Facebook: set only once one Page is active on the login. */
  page_name: string | null;
  /** Facebook: the login whose Pages can be chosen. */
  login_id: string | null;
  reconnect_reason: string | null;
};

export type PlatformOption = { platform: string; label: string };

export type SapiAccountList = { configured: boolean; items: SapiAccount[]; connectable: PlatformOption[] };

export type ConnectResult = { auth_url: string | null; account: SapiAccount | null };

export type CallbackRequest = {
  status: "success" | "error" | "selection_required";
  state: string;
  platform?: string | null;
  account_id?: string | null;
  connection_id?: string | null;
  error?: string | null;
  error_description?: string | null;
};

export type Choice = {
  id: string;
  name: string;
  detail: string | null;
  picture_url: string | null;
  assignable: boolean;
  assigned_account_id: string | null;
};

export type CallbackResult = {
  status: "connected" | "selection_required";
  platform: string;
  account_id: string | null;
  connection_id: string | null;
  choices: Choice[];
};

export type Board = { id: string; board_id: string; name: string; privacy: string | null };

export type PostMode = "now" | "schedule" | "draft";

export type PostCreate = {
  text: string;
  title?: string | null;
  targets: { account_id: string; board_id?: string | null }[];
  media_ids: string[];
  first_comment?: string | null;
  mode: PostMode;
  scheduled_at?: string | null;
};

export type TargetMetrics = { likes: number | null; comments: number | null; shares: number | null; saves: number | null };

export type Target = {
  account_id: string;
  platform: string | null;
  status: string | null;
  permalink: string | null;
  platform_post_id: string | null;
  published_at: string | null;
  scheduled_at: string | null;
  error: string | null;
  metrics: TargetMetrics | null;
  metrics_synced_at: string | null;
};

export type SapiPost = {
  id: string;
  /** draft | scheduled | publishing | published | partial | failed | cancelled */
  status: string;
  text: string | null;
  title: string | null;
  media_count: number;
  created_at: string | null;
  scheduled_at: string | null;
  published_at: string | null;
  targets: Target[];
};

export type SapiPostList = { items: SapiPost[]; next_cursor: string | null };

export type DeleteResult = { ok: boolean; results: { account_id: string | null; outcome: string | null; message: string | null }[] };

export type Constraint = {
  platform: string;
  text_max_length: number | null;
  carousel_max_items: number | null;
  max_video_duration_sec: number | null;
  scheduling_supported: boolean | null;
};

export type AccountAnalytics = {
  account_id: string;
  start: string;
  end: string;
  series: { metric: string; kind: string | null; points: { day: string; value: number | null }[] }[];
};

export type SapiConversation = {
  id: string;
  account_id: string | null;
  platform: string | null;
  participant_name: string | null;
  participant_picture: string | null;
  last_message: string | null;
  last_message_at: string | null;
  unread_count: number;
  status: string | null;
};

export type SapiMessage = {
  id: string;
  text: string | null;
  direction: string | null;
  sender_name: string | null;
  status: string | null;
  created_at: string | null;
  attachment_type: string | null;
  attachment_url: string | null;
};

export type CommentedPost = {
  id: string;
  platform_id: string;
  account_id: string | null;
  platform: string | null;
  content: string | null;
  permalink: string | null;
  thumbnail: string | null;
  comment_count: number;
  published_at: string | null;
};

export type SapiComment = {
  id: string;
  text: string | null;
  author_name: string | null;
  author_username: string | null;
  author_picture: string | null;
  created_at: string | null;
  like_count: number;
  reply_count: number;
  parent_id: string | null;
  is_hidden: boolean;
  is_owner: boolean;
  can_reply: boolean;
  can_delete: boolean;
  can_hide: boolean;
};

export type SapiReview = {
  id: string;
  author_name: string | null;
  author_avatar: string | null;
  rating: number | null;
  text: string | null;
  created_at: string | null;
  reply_text: string | null;
  reply_state: string | null;
};

export type ReviewList = { items: SapiReview[]; next_cursor: string | null; average_rating: number | null; total_count: number | null };

export type ActionResult = { ok: boolean; message: string | null };

export type DraftTurn = { role: "customer" | "agent"; text: string };

export type DraftResult = {
  body: string;
  confidence: number;
  fallback: string | null;
  sources: { kind: string; title: string }[];
};

export const SAPI_LABEL: Record<string, string> = {
  instagram: "Instagram",
  facebook: "Facebook",
  threads: "Threads",
  tiktok: "TikTok",
  linkedin: "LinkedIn",
  youtube: "YouTube",
  twitter: "X (Twitter)",
  bluesky: "Bluesky",
  pinterest: "Pinterest",
  google: "Google Business",
  telegram: "Telegram",
  whatsapp: "WhatsApp",
  zalo: "Zalo",
};

export const sapiLabel = (p: string | null | undefined) => (p ? SAPI_LABEL[p] ?? p : "—");
