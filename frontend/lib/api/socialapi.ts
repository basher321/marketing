/**
 * SocialAPI.ai (SPEC-BE-083): another way to post and answer on social media,
 * next to the direct connections. Read: any role. Inbox replies and AI drafts:
 * agent+. Key, accounts and posts: manager+. The key never reaches the browser.
 */
import type {
  AccountAnalytics,
  ActionResult,
  Board,
  CallbackRequest,
  CallbackResult,
  Choice,
  CommentedPost,
  ConnectResult,
  Constraint,
  DeleteResult,
  DraftResult,
  DraftTurn,
  KeyStatus,
  PostCreate,
  ReviewList,
  SapiAccountList,
  SapiComment,
  SapiConversation,
  SapiMessage,
  SapiPost,
  SapiPostList,
} from "../types/socialapi";
import { apiFetch } from "./client";

const B = "/api/v1/socialapi";

export const sapiKeys = {
  all: ["socialapi"] as const,
  key: ["socialapi", "key"] as const,
  accounts: ["socialapi", "accounts"] as const,
  boards: (accountId: string) => ["socialapi", "boards", accountId] as const,
  facebookPages: (accountId: string) => ["socialapi", "facebook-pages", accountId] as const,
  constraints: ["socialapi", "constraints"] as const,
  posts: (status: string) => ["socialapi", "posts", status] as const,
  post: (id: string) => ["socialapi", "post", id] as const,
  analytics: (accountId: string, range: string) => ["socialapi", "analytics", accountId, range] as const,
  conversations: ["socialapi", "inbox", "conversations"] as const,
  messages: (id: string) => ["socialapi", "inbox", "messages", id] as const,
  commented: ["socialapi", "inbox", "commented"] as const,
  comments: (postId: string) => ["socialapi", "inbox", "comments", postId] as const,
  reviews: (accountId: string) => ["socialapi", "inbox", "reviews", accountId] as const,
};

/** BroadcastChannel the sign-in tab uses to tell the SocialAPI page an account changed. */
export const SAPI_CHANNEL = "socialapi-accounts";

const qs = (params: Record<string, string | null | undefined>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) p.set(k, v);
  const s = p.toString();
  return s ? `?${s}` : "";
};

// Key
export const fetchKey = () => apiFetch<KeyStatus>(`${B}/key`);
export const saveKey = (apiKey: string) => apiFetch<KeyStatus>(`${B}/key`, { method: "PUT", body: { api_key: apiKey } });
export const testKey = () => apiFetch<KeyStatus>(`${B}/key/test`, { method: "POST" });
export const deleteKey = () => apiFetch<void>(`${B}/key`, { method: "DELETE" });

// Accounts
export const fetchAccounts = () => apiFetch<SapiAccountList>(`${B}/accounts`);
export const connectAccount = (platform: string) => apiFetch<ConnectResult>(`${B}/accounts/connect`, { method: "POST", body: { platform } });
export const finishConnect = (q: CallbackRequest) => apiFetch<CallbackResult>(`${B}/accounts/callback`, { method: "POST", body: q });
export const selectChoice = (body: { platform: string; connection_id: string; choice_id: string; state: string }) =>
  apiFetch<{ account_id: string | null }>(`${B}/accounts/select`, { method: "POST", body });
export const disconnectAccount = (id: string) => apiFetch<void>(`${B}/accounts/${encodeURIComponent(id)}`, { method: "DELETE" });
export const fetchFacebookPages = (id: string) => apiFetch<{ items: Choice[] }>(`${B}/accounts/${encodeURIComponent(id)}/facebook-pages`);
export const chooseFacebookPage = (id: string, pageId: string) =>
  apiFetch<{ account_id: string | null }>(`${B}/accounts/${encodeURIComponent(id)}/facebook-page`, { method: "POST", body: { page_id: pageId } });
export const fetchBoards =(id: string) => apiFetch<{ items: Board[] }>(`${B}/accounts/${encodeURIComponent(id)}/boards`);
export const fetchAccountAnalytics = (id: string, range: "7d" | "30d" | "90d") =>
  apiFetch<AccountAnalytics>(`${B}/accounts/${encodeURIComponent(id)}/analytics${qs({ range })}`);

// Posts
export const fetchConstraints = () => apiFetch<{ items: Constraint[] }>(`${B}/constraints`);
export const fetchPosts = (status: string, cursor?: string | null) => apiFetch<SapiPostList>(`${B}/posts${qs({ status, cursor })}`);
export const fetchPost = (id: string) => apiFetch<SapiPost>(`${B}/posts/${encodeURIComponent(id)}`);
export const createPost = (body: PostCreate) => apiFetch<SapiPost>(`${B}/posts`, { method: "POST", body });
export const publishPost = (id: string) => apiFetch<SapiPost>(`${B}/posts/${encodeURIComponent(id)}/publish`, { method: "POST" });
export const retryPost = (id: string) => apiFetch<SapiPost>(`${B}/posts/${encodeURIComponent(id)}/retry`, { method: "POST" });
export const deletePost = (id: string) => apiFetch<DeleteResult>(`${B}/posts/${encodeURIComponent(id)}`, { method: "DELETE" });

// Inbox
export const fetchConversations = () =>
  apiFetch<{ items: SapiConversation[]; next_cursor: string | null; sync_state: string | null }>(`${B}/inbox/conversations`);
export const fetchMessages = (id: string) =>
  apiFetch<{ items: SapiMessage[]; next_cursor: string | null }>(`${B}/inbox/conversations/${encodeURIComponent(id)}/messages`);
export const sendMessage = (id: string, accountId: string, text: string) =>
  apiFetch<ActionResult>(`${B}/inbox/conversations/${encodeURIComponent(id)}/messages`, { method: "POST", body: { account_id: accountId, text } });
export const fetchCommentedPosts = () => apiFetch<{ items: CommentedPost[]; next_cursor: string | null }>(`${B}/inbox/comments`);
export const fetchComments = (postId: string, accountId: string) =>
  apiFetch<{ items: SapiComment[]; next_cursor: string | null }>(`${B}/inbox/comments/${encodeURIComponent(postId)}${qs({ account_id: accountId })}`);
export const replyComment = (postId: string, accountId: string, commentId: string, text: string) =>
  apiFetch<ActionResult>(`${B}/inbox/comments/${encodeURIComponent(postId)}/reply`, {
    method: "POST",
    body: { account_id: accountId, comment_id: commentId, text },
  });
export const moderateComment = (postId: string, commentId: string, accountId: string, action: "hide" | "unhide" | "delete") =>
  apiFetch<ActionResult>(`${B}/inbox/comments/${encodeURIComponent(postId)}/${encodeURIComponent(commentId)}/moderate`, {
    method: "POST",
    body: { account_id: accountId, action },
  });
export const fetchReviews = (accountId: string) => apiFetch<ReviewList>(`${B}/inbox/reviews/${encodeURIComponent(accountId)}`);
export const replyReview = (reviewId: string, accountId: string, text: string) =>
  apiFetch<ActionResult>(`${B}/inbox/reviews/${encodeURIComponent(reviewId)}/reply`, { method: "POST", body: { account_id: accountId, text } });
export const draftReply = (history: DraftTurn[]) => apiFetch<DraftResult>(`${B}/inbox/draft-reply`, { method: "POST", body: { history } });
