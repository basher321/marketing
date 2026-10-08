"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Empty, errorText } from "@/components/organic/shared";
import {
  draftReply,
  fetchAccounts,
  fetchCommentedPosts,
  fetchComments,
  fetchConversations,
  fetchMessages,
  fetchReviews,
  moderateComment,
  replyComment,
  replyReview,
  sapiKeys,
  sendMessage,
} from "@/lib/api/socialapi";
import { sapiLabel, type CommentedPost, type DraftTurn, type SapiConversation } from "@/lib/types/socialapi";

// SocialAPI inbox (SPEC-FE-054 / SPEC-BE-083): DMs, comments and reviews read
// live from SocialAPI.ai and answered through it. "Draft with AI" uses the
// same grounded, moderated drafter as Customer Service; nothing is sent until
// the agent presses Send. The Customer Service inbox itself is unchanged.

const when = (v: string | null) => (v ? new Date(v).toLocaleString() : "");

/** Reply text box with an optional AI draft. `onSend` returns a promise; the box clears on success. */
function ReplyBox({
  history,
  onSend,
  placeholder = "Write a reply…",
  note,
}: {
  history: DraftTurn[];
  onSend: (text: string) => Promise<{ message: string | null }>;
  placeholder?: string;
  note?: string;
}) {
  const [text, setText] = useState("");
  const draft = useMutation({ mutationFn: () => draftReply(history), onSuccess: (d) => setText(d.body) });
  const send = useMutation({ mutationFn: () => onSend(text.trim()), onSuccess: () => setText("") });
  const hasCustomer = history.some((t) => t.role === "customer");
  return (
    <div className="mt-2">
      <textarea rows={3} className="w-full" value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} />
      <div className="mt-1 flex flex-wrap items-center gap-2">
        <button type="button" className="btn btn-sm" disabled={!text.trim() || send.isPending} onClick={() => send.mutate()}>
          {send.isPending ? "Sending…" : "Send"}
        </button>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={!hasCustomer || draft.isPending}
          onClick={() => draft.mutate()}
          title="Drafts in your brand voice from the Knowledge Base; you review before sending"
        >
          {draft.isPending ? "Drafting…" : "✨ Draft with AI"}
        </button>
        {draft.data?.fallback === "no_grounding" && (
          <span className="text-xs text-muted">No matching Knowledge Base answer, so this is a holding reply.</span>
        )}
        {draft.data && draft.data.sources.length > 0 && (
          <span className="text-xs text-muted">Based on: {draft.data.sources.map((s) => s.title).join(", ")}</span>
        )}
        {note && <span className="text-xs text-muted">{note}</span>}
      </div>
      {draft.isError && <p className="m-0 mt-1 text-xs text-danger">{errorText(draft.error)}</p>}
      {send.isError && <p className="m-0 mt-1 text-xs text-danger">{errorText(send.error)}</p>}
      {send.data?.message && <p className="m-0 mt-1 text-xs text-muted">{send.data.message}</p>}
    </div>
  );
}

function Messages() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: sapiKeys.conversations, queryFn: fetchConversations, refetchInterval: 30_000 });
  const [sel, setSel] = useState<SapiConversation | null>(null);
  const thread = useQuery({ queryKey: sapiKeys.messages(sel?.id ?? ""), queryFn: () => fetchMessages(sel!.id), enabled: !!sel, refetchInterval: 15_000 });
  const history: DraftTurn[] = (thread.data?.items ?? [])
    .filter((m) => m.text)
    .slice(-20)
    .map((m) => ({ role: m.direction === "outbound" ? "agent" : "customer", text: m.text as string }));
  return (
    <div className="grid-2">
      <section className="card" style={{ padding: 0 }}>
        {list.isError ? (
          <p className="m-0 p-4 text-xs text-danger">{errorText(list.error)}</p>
        ) : !list.data ? (
          <Empty>Loading…</Empty>
        ) : list.data.items.length === 0 ? (
          <Empty>No conversations. DMs come from Instagram and Facebook accounts connected in SocialAPI.</Empty>
        ) : (
          <table>
            <tbody>
              {list.data.items.map((c) => (
                <tr key={c.id} onClick={() => setSel(c)} className={`cursor-pointer ${sel?.id === c.id ? "bg-accent-soft" : ""}`}>
                  <td className="text-[13px]">
                    <strong>{c.participant_name ?? "Unknown"}</strong>
                    {c.unread_count > 0 && <span className="badge badge-warn ml-2">{c.unread_count} new</span>}
                    <div className="max-w-[360px] truncate text-xs text-muted">{c.last_message}</div>
                  </td>
                  <td className="text-xs">{sapiLabel(c.platform)}</td>
                  <td className="whitespace-nowrap text-xs text-muted">{when(c.last_message_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {list.data?.sync_state === "syncing" && <p className="m-0 p-3 text-xs text-muted">SocialAPI is syncing new messages…</p>}
      </section>
      <section className="card">
        {!sel ? (
          <p className="m-0 text-[13px] text-muted">Select a conversation.</p>
        ) : (
          <>
            <div className="mb-2 font-semibold">
              {sel.participant_name ?? "Conversation"} · {sapiLabel(sel.platform)}
            </div>
            <div className="flex max-h-[360px] flex-col gap-2 overflow-y-auto">
              {thread.isError && <p className="m-0 text-xs text-danger">{errorText(thread.error)}</p>}
              {(thread.data?.items ?? []).map((m) => (
                <div key={m.id} className={`msg ${m.direction === "outbound" ? "user" : "ai"}`}>
                  {m.text ?? (m.attachment_url ? <a href={m.attachment_url} target="_blank" rel="noreferrer">{m.attachment_type ?? "attachment"} ↗</a> : "")}
                  <div className="text-[10px] opacity-70">{when(m.created_at)}</div>
                </div>
              ))}
            </div>
            {sel.account_id ? (
              <ReplyBox
                history={history}
                note="Instagram and Facebook allow replies within 24 h of the customer's last message."
                onSend={async (text) => {
                  const r = await sendMessage(sel.id, sel.account_id as string, text);
                  void qc.invalidateQueries({ queryKey: sapiKeys.messages(sel.id) });
                  return r;
                }}
              />
            ) : (
              <p className="m-0 mt-2 text-xs text-muted">SocialAPI didn&apos;t say which account this conversation belongs to.</p>
            )}
          </>
        )}
      </section>
    </div>
  );
}

/** Our post (context) + the comment being answered. */
function commentHistory(postText: string | null, comment: string | null): DraftTurn[] {
  const turns: DraftTurn[] = [];
  if (postText) turns.push({ role: "agent", text: `(Our post) ${postText}` });
  if (comment) turns.push({ role: "customer", text: comment });
  return turns;
}

function CommentThread({ post }: { post: CommentedPost }) {
  const qc = useQueryClient();
  const accountId = post.account_id ?? "";
  const key = sapiKeys.comments(post.platform_id);
  const comments = useQuery({ queryKey: key, queryFn: () => fetchComments(post.platform_id, accountId), enabled: !!accountId });
  const [open, setOpen] = useState<string | null>(null);
  const moderate = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "hide" | "unhide" | "delete" }) => moderateComment(post.platform_id, id, accountId, action),
    onSuccess: () => void qc.invalidateQueries({ queryKey: key }),
  });
  if (!accountId) return <p className="m-0 text-xs text-muted">SocialAPI didn&apos;t say which account owns this post.</p>;
  return (
    <>
      {comments.isError && <p className="m-0 text-xs text-danger">{errorText(comments.error)}</p>}
      {moderate.isError && <p className="m-0 text-xs text-danger">{errorText(moderate.error)}</p>}
      {comments.data?.items.length === 0 && <p className="m-0 text-xs text-muted">No comments.</p>}
      <ul className="m-0 grid list-none gap-2 p-0">
        {(comments.data?.items ?? []).map((c) => (
          <li key={c.id} className={`rounded-md border border-border p-2 ${c.parent_id ? "ml-6" : ""} ${c.is_hidden ? "opacity-60" : ""}`}>
            <div className="text-xs text-muted">
              <strong className="text-text">{c.author_name ?? c.author_username ?? "Someone"}</strong>
              {c.is_owner ? " (you)" : ""} · {when(c.created_at)}
              {c.is_hidden ? " · hidden" : ""}
              {c.like_count ? ` · ♥ ${c.like_count}` : ""}
            </div>
            <div className="text-[13px]">{c.text}</div>
            {!c.is_owner && (
              <div className="mt-1 flex flex-wrap gap-2 text-xs">
                {c.can_reply && (
                  <button type="button" className="text-accent underline" onClick={() => setOpen(open === c.id ? null : c.id)}>
                    Reply
                  </button>
                )}
                {c.can_hide && (
                  <button type="button" className="text-accent underline" disabled={moderate.isPending} onClick={() => moderate.mutate({ id: c.id, action: c.is_hidden ? "unhide" : "hide" })}>
                    {c.is_hidden ? "Unhide" : "Hide"}
                  </button>
                )}
                {c.can_delete && (
                  <button
                    type="button"
                    className="text-danger underline"
                    disabled={moderate.isPending}
                    onClick={() => window.confirm("Delete this comment on the platform?") && moderate.mutate({ id: c.id, action: "delete" })}
                  >
                    Delete
                  </button>
                )}
              </div>
            )}
            {open === c.id && (
              <ReplyBox
                history={commentHistory(post.content, c.text)}
                onSend={async (text) => {
                  const r = await replyComment(post.platform_id, accountId, c.id, text);
                  setOpen(null);
                  void qc.invalidateQueries({ queryKey: key });
                  return r;
                }}
              />
            )}
          </li>
        ))}
      </ul>
    </>
  );
}

function Comments() {
  const posts = useQuery({ queryKey: sapiKeys.commented, queryFn: fetchCommentedPosts, refetchInterval: 60_000 });
  const [sel, setSel] = useState<CommentedPost | null>(null);
  return (
    <div className="grid-2">
      <section className="card" style={{ padding: 0 }}>
        {posts.isError ? (
          <p className="m-0 p-4 text-xs text-danger">{errorText(posts.error)}</p>
        ) : !posts.data ? (
          <Empty>Loading…</Empty>
        ) : posts.data.items.length === 0 ? (
          <Empty>No commented posts yet.</Empty>
        ) : (
          <table>
            <tbody>
              {posts.data.items.map((p) => (
                <tr key={p.id} onClick={() => setSel(p)} className={`cursor-pointer ${sel?.id === p.id ? "bg-accent-soft" : ""}`}>
                  <td className="w-[56px]">{p.thumbnail ? <img src={p.thumbnail} alt="" className="h-10 w-10 rounded object-cover" /> : null}</td>
                  <td className="max-w-[340px] truncate text-[13px]">{p.content ?? "(no text)"}</td>
                  <td className="text-xs">{sapiLabel(p.platform)}</td>
                  <td className="whitespace-nowrap text-xs">💬 {p.comment_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      <section className="card">
        {!sel ? (
          <p className="m-0 text-[13px] text-muted">Select a post to see its comments.</p>
        ) : (
          <>
            <div className="mb-2 flex items-center gap-2 font-semibold">
              {sapiLabel(sel.platform)} post
              {sel.permalink && (
                <a href={sel.permalink} target="_blank" rel="noreferrer" className="text-xs font-normal text-accent underline">
                  Open ↗
                </a>
              )}
            </div>
            <CommentThread key={sel.id} post={sel} />
          </>
        )}
      </section>
    </div>
  );
}

function Reviews() {
  const qc = useQueryClient();
  const accounts = useQuery({ queryKey: sapiKeys.accounts, queryFn: fetchAccounts });
  const google = (accounts.data?.items ?? []).filter((a) => a.platform === "google");
  const [picked, setPicked] = useState("");
  const accountId = picked || google[0]?.id || "";
  const reviews = useQuery({ queryKey: sapiKeys.reviews(accountId), queryFn: () => fetchReviews(accountId), enabled: !!accountId });
  if (accounts.data && google.length === 0) {
    return <p className="text-[13px] text-muted">Reviews come from Google Business Profile: connect one in Organic Marketing › SocialAPI.</p>;
  }
  return (
    <section className="card">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <select value={accountId} onChange={(e) => setPicked(e.target.value)} aria-label="Location">
          {google.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name ?? a.id}
            </option>
          ))}
        </select>
        {reviews.data?.average_rating != null && (
          <span className="text-[13px]">
            ★ {reviews.data.average_rating.toFixed(1)} · {reviews.data.total_count ?? reviews.data.items.length} reviews
          </span>
        )}
      </div>
      {reviews.isError && <p className="m-0 text-xs text-danger">{errorText(reviews.error)}</p>}
      {reviews.data?.items.length === 0 && <p className="m-0 text-xs text-muted">No reviews yet.</p>}
      <ul className="m-0 grid list-none gap-3 p-0">
        {(reviews.data?.items ?? []).map((r) => (
          <li key={r.id} className="rounded-md border border-border p-3">
            <div className="text-xs text-muted">
              <strong className="text-text">{r.author_name ?? "Customer"}</strong> · {"★".repeat(r.rating ?? 0)}
              {"☆".repeat(Math.max(0, 5 - (r.rating ?? 0)))} · {when(r.created_at)}
            </div>
            <div className="text-[13px]">{r.text ?? <span className="text-muted">(rating only)</span>}</div>
            {r.reply_text ? (
              <div className="mt-2 rounded-md bg-accent-soft p-2 text-xs">
                Your reply{r.reply_state && r.reply_state !== "APPROVED" ? ` (${r.reply_state.toLowerCase()})` : ""}: {r.reply_text}
              </div>
            ) : (
              <ReplyBox
                placeholder="Reply publicly…"
                history={[{ role: "customer", text: `${r.rating ?? "?"}-star review: ${r.text ?? "(no text)"}` }]}
                onSend={async (text) => {
                  const res = await replyReview(r.id, accountId, text);
                  void qc.invalidateQueries({ queryKey: sapiKeys.reviews(accountId) });
                  return res;
                }}
              />
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

const TABS = [
  { id: "messages", label: "Messages" },
  { id: "comments", label: "Comments" },
  { id: "reviews", label: "Reviews" },
] as const;

export default function SocialApiInbox() {
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("messages");
  return (
    <>
      <nav className="tabs mb-4" aria-label="SocialAPI inbox sections">
        {TABS.map((t) => (
          <button key={t.id} type="button" className={tab === t.id ? "tab active" : "tab"} aria-current={tab === t.id ? "page" : undefined} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </nav>
      {tab === "messages" ? <Messages /> : tab === "comments" ? <Comments /> : <Reviews />}
    </>
  );
}
