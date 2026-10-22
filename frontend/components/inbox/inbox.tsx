"use client";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import MediaPicker from "@/components/organic/media-picker";
import { errorText } from "@/components/organic/shared";
import { ConfirmationBadge, StatusBadge, formatWhen } from "@/components/orders/status";
import { generateDraft } from "@/lib/api/conversations";
import { customerKeys, fetchCustomers } from "@/lib/api/customers";
import {
  fetchInboxChannels,
  fetchInboxConversations,
  fetchInboxThread,
  inboxKeys,
  linkInboxCustomer,
  sendInboxMessage,
  updateInboxConversation,
} from "@/lib/api/inbox";
import { fetchUsers, tenantKeys } from "@/lib/api/tenant";
import { formatMoney } from "@/lib/format/money";
import type { InboxConversation, InboxFilters, InboxThread } from "@/lib/types/inbox";

const INPUT = "rounded-md border border-border bg-panel px-3 py-2 text-[13.5px] text-text";
const PLATFORM: Record<string, string> = {
  messenger: "Messenger", instagram: "Instagram", whatsapp: "WhatsApp", sms: "SMS", web: "Website", email: "Email",
  facebook: "Facebook",
};
const TICKS: Record<string, string> = { pending: "…", sent: "✓", delivered: "✓✓", read: "✓✓ read", failed: "⚠ failed", not_sent: "not sent" };

function usePageVisible(): boolean {
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    const on = () => setVisible(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", on);
    return () => document.removeEventListener("visibilitychange", on);
  }, []);
  return visible;
}

function name(c: InboxConversation): string {
  return c.customer.name ?? c.customer.phone ?? c.customer.handle ?? "Unknown";
}

function CustomerPanel({ thread, onLinked }: { thread: InboxThread; onLinked: () => void }) {
  const [search, setSearch] = useState("");
  const found = useQuery({
    queryKey: customerKeys.list(search, 0),
    queryFn: () => fetchCustomers(search, 5, 0),
    enabled: search.trim().length >= 2,
  });
  const link = useMutation({
    mutationFn: (customerId: string) => linkInboxCustomer(thread.conversation.key, customerId),
    onSuccess: onLinked,
  });
  const c = thread.customer;
  return (
    <div className="card">
      <p className="card-title">Customer</p>
      {c ? (
        <>
          <p className="font-semibold">
            <Link href={`/customers/${c.id}`} className="text-accent">{c.name ?? c.phone ?? c.email}</Link>
          </p>
          <p className="text-[13px] text-muted">{[c.phone, c.email].filter(Boolean).join(" · ")}</p>
          <p className="mt-1 text-[13px]">{c.order_count} order(s) · {formatMoney(c.lifetime_value, c.currency)}</p>
          <ul className="mt-2 flex flex-col gap-1 text-[13px]">
            {c.orders.map((o) => (
              <li key={o.id}>
                <Link href={`/orders/${o.id}`} className="text-accent">#{o.order_number}</Link> <StatusBadge status={o.status} />{" "}
                <ConfirmationBadge state={o.confirmation_state} />
              </li>
            ))}
          </ul>
        </>
      ) : (
        <>
          <p className="text-[13px]">{name(thread.conversation)}</p>
          <p className="mb-2 text-[12.5px] text-muted">Not linked to a customer record yet.</p>
          <input className={`${INPUT} w-full`} placeholder="Link to customer: search…" value={search} onChange={(e) => setSearch(e.target.value)} />
          {(found.data ?? []).map((x) => (
            <button key={x.id} type="button" className="mt-1 block w-full rounded-md px-2 py-1 text-left text-[13px] hover:bg-accent-soft"
              disabled={link.isPending} onClick={() => link.mutate(x.id)}>
              {[x.first_name, x.last_name].filter(Boolean).join(" ") || "—"} <span className="text-muted">{x.phone ?? x.email}</span>
            </button>
          ))}
          {link.isError && <p className="text-danger">{errorText(link.error)}</p>}
        </>
      )}
    </div>
  );
}

function Thread({ convKey, onBack }: { convKey: string; onBack: () => void }) {
  const queryClient = useQueryClient();
  const visible = usePageVisible();
  const query = useQuery({
    queryKey: inboxKeys.thread(convKey),
    queryFn: () => fetchInboxThread(convKey),
    refetchInterval: visible ? 10_000 : false,
  });
  const users = useQuery({ queryKey: tenantKeys.users, queryFn: fetchUsers, retry: false });
  const [text, setText] = useState("");
  const [media, setMedia] = useState<string[]>([]);
  const end = useRef<HTMLDivElement>(null);
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: inboxKeys.thread(convKey) });
    void queryClient.invalidateQueries({ queryKey: ["inbox", "list"] });
  };
  const send = useMutation({
    mutationFn: () => sendInboxMessage(convKey, text.trim(), media),
    onSuccess: () => { setText(""); setMedia([]); refresh(); },
  });
  const patch = useMutation({
    mutationFn: (body: { status?: string; assignee_id?: string | null }) => updateInboxConversation(convKey, body),
    onSuccess: refresh,
  });
  const draft = useMutation({
    mutationFn: () => generateDraft(query.data!.conversation.conversation_id),
    onSuccess: (d) => { if (d.draft) setText(d.draft.body); },
  });
  const count = query.data?.items.length ?? 0;
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [count]);
  if (query.isPending) return <div className="card text-muted">Loading conversation…</div>;
  if (query.isError) return <div className="card text-danger">{query.error.message}</div>;
  const t = query.data;
  const c = t.conversation;
  const local = c.key.startsWith("local:");
  return (
    <div className="flex flex-col gap-3">
      <div className="card">
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="btn btn-secondary btn-sm lg:hidden" onClick={onBack}>← Back</button>
          <strong>{name(c)}</strong>
          <span className="badge badge-neutral">{PLATFORM[c.platform] ?? c.platform}</span>
          {c.is_sample && <span className="badge badge-warn">Sample</span>}
          {local && (
            <span className="ml-auto flex flex-wrap gap-2">
              <select aria-label="Status" className={INPUT} value={c.status ?? "open"} disabled={patch.isPending}
                onChange={(e) => patch.mutate({ status: e.target.value })}>
                <option value="open">Open</option>
                <option value="pending">Pending</option>
                <option value="resolved">Resolved</option>
                <option value="archived">Archived</option>
              </select>
              <select aria-label="Assignee" className={INPUT} value={c.assignee_id ?? ""} disabled={patch.isPending || !users.data}
                onChange={(e) => patch.mutate({ assignee_id: e.target.value || null })}>
                <option value="">Unassigned</option>
                {(users.data ?? []).filter((u) => u.status === "active").map((u) => (
                  <option key={u.id} value={u.id}>{[u.first_name, u.last_name].filter(Boolean).join(" ") || u.email}</option>
                ))}
              </select>
            </span>
          )}
        </div>
        {patch.isError && <p className="mt-2 text-danger">{errorText(patch.error)}</p>}
      </div>
      <div className="grid gap-3 lg:grid-cols-[1fr_260px]">
        <div className="card flex flex-col gap-2" style={{ maxHeight: 520, overflowY: "auto" }}>
          {t.items.length === 0 && <p className="text-muted">No messages yet.</p>}
          {t.items.map((m) => (
            <div key={m.id} className={m.direction === "inbound" ? "self-start" : "self-end text-right"} style={{ maxWidth: "80%" }}>
              <div className={`rounded-xl px-3 py-2 text-[13.5px] ${m.direction === "inbound" ? "bg-accent-soft" : "border border-border"} ${m.is_ai_draft ? "opacity-70" : ""}`}>
                {m.is_ai_draft && <span className="badge badge-neutral mr-1">AI draft</span>}
                {m.body}
                {m.attachments.map((a, i) => (
                  <div key={i} className="text-[12px] text-muted">📎 {a.name ?? a.kind ?? "attachment"}{a.url && <> · <a href={a.url} target="_blank" rel="noreferrer" className="text-accent">open</a></>}</div>
                ))}
              </div>
              <div className="mt-0.5 text-[11.5px] text-muted">
                {m.sender ?? ""} · {formatWhen(m.sent_at)}
                {m.delivery && <> · <span className={m.delivery === "failed" ? "text-danger" : ""}>{TICKS[m.delivery] ?? m.delivery}</span></>}
                {m.error && <span className="text-danger"> — {m.error}</span>}
              </div>
            </div>
          ))}
          <div ref={end} />
        </div>
        <CustomerPanel thread={t} onLinked={refresh} />
      </div>
      <form
        className="card flex flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if ((text.trim() || media.length) && t.can_send) send.mutate();
        }}
      >
        {!t.can_send && t.send_blocked_reason && <p className="text-[13px] text-muted">{t.send_blocked_reason}</p>}
        <textarea className={`${INPUT} w-full`} rows={3} maxLength={4000} placeholder={t.can_send ? "Write a reply…" : "Replies can't be sent here"}
          disabled={!t.can_send} value={text} onChange={(e) => setText(e.target.value)} />
        {t.can_send_media && <MediaPicker value={media} onChange={(ids) => setMedia(ids)} kind="image" max={4} />}
        <div className="flex flex-wrap gap-2">
          <button type="submit" className="btn" disabled={!t.can_send || send.isPending || (!text.trim() && !media.length)}>
            {send.isPending ? "Sending…" : "Send"}
          </button>
          {local && t.can_send && (
            <button type="button" className="btn btn-secondary" disabled={draft.isPending} onClick={() => draft.mutate()}>
              {draft.isPending ? "Drafting…" : "✨ Draft with AI"}
            </button>
          )}
        </div>
        {send.isError && <p className="text-danger">{errorText(send.error)}</p>}
        {draft.isError && <p className="text-danger">{errorText(draft.error)}</p>}
      </form>
    </div>
  );
}

// Command Chat → Inbox (SPEC-FE-076 / SPEC-BE-112): every connected channel in one
// list, a thread with delivery ticks and the customer panel. Polls while visible.
export default function Inbox({ initialKey }: { initialKey: string | null }) {
  const visible = usePageVisible();
  const channels = useQuery({ queryKey: inboxKeys.channels, queryFn: fetchInboxChannels });
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<InboxFilters>({ channel: "all", q: "", status: "", unread: false, mine: false });
  const [open, setOpen] = useState<string | null>(initialKey);
  useEffect(() => {
    const t = setTimeout(() => setFilters((f) => ({ ...f, q: search.trim() })), 300);
    return () => clearTimeout(t);
  }, [search]);
  const list = useInfiniteQuery({
    queryKey: inboxKeys.list(filters),
    queryFn: ({ pageParam }) => fetchInboxConversations(filters, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    refetchInterval: visible ? 20_000 : false,
  });
  const items = list.data?.pages.flatMap((p) => p.items) ?? [];
  const errors = list.data?.pages[0]?.channel_errors ?? [];

  if (channels.isSuccess && channels.data.items.length === 0) {
    return (
      <div className="card">
        <h3 className="mt-0">No channels connected yet</h3>
        <p className="text-[13px]">
          Connect Messenger or Instagram through <Link href="/marketing/organic/socialapi" className="text-accent">Organic › SocialAPI</Link>,
          WhatsApp Business in <Link href="/integrations" className="text-accent">Integrations</Link>, or ask PilotSonic for an SMS number.
        </p>
      </div>
    );
  }
  return (
    <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
      <div className={open ? "hidden flex-col gap-2 lg:flex" : "flex flex-col gap-2"}>
        <select aria-label="Channel" className={INPUT} value={filters.channel} onChange={(e) => setFilters({ ...filters, channel: e.target.value })}>
          <option value="all">All channels</option>
          {(channels.data?.items ?? []).map((c) => (
            <option key={c.key} value={c.key}>
              {PLATFORM[c.platform] ?? c.platform} · {c.name}{c.status === "needs_attention" ? " (needs attention)" : ""}
            </option>
          ))}
        </select>
        <input type="search" aria-label="Search conversations" className={INPUT} placeholder="Search name, phone or message" value={search} onChange={(e) => setSearch(e.target.value)} />
        <div className="flex flex-wrap gap-2 text-[13px]">
          <select aria-label="Status filter" className={INPUT} value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value as InboxFilters["status"] })}>
            <option value="">Open + pending</option>
            <option value="resolved">Resolved</option>
            <option value="archived">Archived</option>
          </select>
          <label className="flex items-center gap-1"><input type="checkbox" checked={filters.unread} onChange={(e) => setFilters({ ...filters, unread: e.target.checked })} /> Unread</label>
          <label className="flex items-center gap-1"><input type="checkbox" checked={filters.mine} onChange={(e) => setFilters({ ...filters, mine: e.target.checked })} /> Assigned to me</label>
        </div>
        {errors.map((e) => <p key={e.channel} className="text-[12.5px] text-warn">⚠ {e.message}</p>)}
        <div className="card flex flex-col gap-1" style={{ padding: 6 }}>
          {list.isPending ? (
            <p className="p-2 text-muted">Loading…</p>
          ) : list.isError ? (
            <p className="p-2 text-danger">{list.error.message}</p>
          ) : items.length === 0 ? (
            <p className="p-2 text-muted">No conversations here.</p>
          ) : (
            items.map((c) => (
              <button key={c.key} type="button" onClick={() => setOpen(c.key)}
                className={`rounded-lg px-3 py-2 text-left ${open === c.key ? "bg-accent-soft" : "hover:bg-accent-soft"}`}>
                <div className="flex items-center gap-2">
                  {c.unread > 0 && <span className="h-2 w-2 rounded-full bg-accent" aria-label={`${c.unread} unread`} />}
                  <strong className="truncate">{name(c)}</strong>
                  <span className="ml-auto text-[11.5px] text-muted">{formatWhen(c.last_message.at)}</span>
                </div>
                <div className="flex items-center gap-1 text-[12px] text-muted">
                  <span>{PLATFORM[c.platform] ?? c.platform}</span>
                  {c.is_sample && <span className="badge badge-warn">Sample</span>}
                  {c.assignee_name && <span>· {c.assignee_name}</span>}
                </div>
                <div className="truncate text-[12.5px]">{c.last_message.preview ?? ""}</div>
              </button>
            ))
          )}
          {list.hasNextPage && (
            <button type="button" className="btn btn-secondary btn-sm m-2" disabled={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>
              {list.isFetchingNextPage ? "Loading…" : "Load more"}
            </button>
          )}
        </div>
      </div>
      <div className={open ? "" : "hidden lg:block"}>
        {open ? (
          <Thread key={open} convKey={open} onBack={() => setOpen(null)} />
        ) : (
          <div className="card text-muted">Choose a conversation.</div>
        )}
      </div>
    </div>
  );
}
