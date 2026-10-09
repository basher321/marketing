"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { fetchMedia, fetchMediaItem, mediaKeys } from "@/lib/api/media";
import { discardDraft, fetchMessages, orchestratorKeys, sendMessage } from "@/lib/api/orchestrator";
import { ApiError } from "@/lib/types/common";
import type { MediaItem, MediaKind } from "@/lib/types/media";
import type { ChatMessage, PlanRead, ResultItem } from "@/lib/types/orchestrator";

import { MediaThumb } from "../organic/media-picker";
import PlanCard from "./plan-card";

export { orchestratorKeys };

function ResultTable({ rows }: { rows: Record<string, unknown>[] }) {
  const cols = Object.keys(rows[0] ?? {}).filter((c) => !c.endsWith("_id") && c !== "id").slice(0, 7);
  if (!cols.length) return null;
  return (
    <div className="mt-1.5 overflow-x-auto">
      <table className="w-full text-[11.5px]">
        <thead>
          <tr>
            {cols.map((c) => (
              <th key={c} className="px-1.5 py-1 text-left font-semibold text-muted">
                {c.replace(/_/g, " ")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 10).map((r, i) => (
            <tr key={i} className="border-t border-border">
              {cols.map((c) => (
                <td key={c} className="px-1.5 py-1">
                  {r[c] === null || r[c] === undefined ? "—" : Array.isArray(r[c]) ? (r[c] as unknown[]).join(", ") : String(r[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > 10 && <div className="text-[11px] text-muted">…and {rows.length - 10} more</div>}
    </div>
  );
}

// A Nano Banana image / Google Flow video the chat made (SPEC-FE-057). The
// signed URL is fetched fresh, so it still works after a reload.
function ResultMediaPreview({ media }: { media: NonNullable<ResultItem["media"]> }) {
  const q = useQuery({ queryKey: mediaKeys.item(media.id), queryFn: () => fetchMediaItem(media.id), staleTime: 30 * 60_000 });
  if (q.error instanceof ApiError && q.error.status === 404)
    return <div className="mt-1.5 text-[11px] text-muted">This file was deleted from the media library.</div>;
  if (q.error) return <div className="mt-1.5 text-[11px] text-danger">Couldn&apos;t load the preview.</div>;
  if (!q.data) return <div className="mt-1.5 h-[180px] w-full max-w-[320px] animate-pulse rounded-md bg-bg" />;
  const url = q.data.url;
  return (
    <div className="mt-1.5 grid max-w-[320px] gap-1" data-testid="chat-result-media">
      {media.kind === "video" ? (
        <video src={url} controls playsInline className="max-h-[320px] w-full rounded-md bg-bg object-contain" />
      ) : (
        <img src={url} alt={q.data.name ?? "Generated image"} className="max-h-[320px] w-full rounded-md bg-bg object-contain" />
      )}
      <a href={url} download={q.data.name ?? undefined} target="_blank" rel="noreferrer" className="text-[11px] text-accent underline">
        Download
      </a>
    </div>
  );
}

// The result summary (SPEC-BE-059 §5): the backend's own text plus its
// structured results (tables and links) - nothing is computed client-side.
function Results({ items }: { items: ResultItem[] }) {
  return (
    <div className="mt-2 grid gap-2">
      {items.map((r) => (
        <div key={r.index} className="text-xs">
          <b>
            {r.index}. {r.label}
          </b>{" "}
          <span className={r.status === "succeeded" ? "text-success" : r.status === "failed" ? "text-danger" : "text-muted"}>
            {r.status}
          </span>
          {r.link &&
            (r.link.startsWith("/") ? (
              <Link href={r.link} target="_blank" rel="noopener" className="ml-1.5 text-accent underline">
                Open
              </Link>
            ) : (
              <a href={r.link} target="_blank" rel="noreferrer" className="ml-1.5 text-accent underline">
                Open in Ads Manager
              </a>
            ))}
          {r.data && r.data.length > 0 && <ResultTable rows={r.data} />}
          {r.media && r.status === "succeeded" && <ResultMediaPreview media={r.media} />}
        </div>
      ))}
    </div>
  );
}

const PAGE_SIZE = 40; // the backend's media page size

// Media library picker for the ad's image/video question (SPEC-FE-056):
// kind filter, name search and paging; choosing an item answers the question.
function ChatMediaPicker({ onPick, onClose, disabled }: { onPick: (item: MediaItem) => void; onClose: () => void; disabled: boolean }) {
  const [kind, setKind] = useState<MediaKind | "">("");
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  useEffect(() => {
    const t = setTimeout(() => {
      setQ(search.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);
  const media = useQuery({ queryKey: ["media", "chat-picker", kind, q, page], queryFn: () => fetchMedia(kind, page, q) });
  const pages = Math.max(1, Math.ceil((media.data?.count ?? 0) / PAGE_SIZE));
  return (
    <div className="mx-[14px] mt-2 rounded-md border border-border p-2" data-testid="chat-media-picker">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        {([["", "All"], ["image", "Images"], ["video", "Videos"]] as const).map(([k, label]) => (
          <button
            key={label}
            type="button"
            className={`btn btn-sm ${kind === k ? "" : "btn-secondary"}`}
            onClick={() => {
              setKind(k);
              setPage(1);
            }}
          >
            {label}
          </button>
        ))}
        <input
          className="min-w-[140px] flex-1"
          placeholder="Search by name…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Search media by name"
        />
        <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
          Close
        </button>
      </div>
      {media.isPending ? (
        <p className="text-xs text-muted">Loading media…</p>
      ) : media.isError ? (
        <p className="text-xs text-danger" role="alert">
          Couldn&apos;t load the media library: {media.error.message}
        </p>
      ) : media.data.items.length === 0 ? (
        <p className="text-xs text-muted">No images or videos match.</p>
      ) : (
        <div className="grid max-h-[260px] grid-cols-[repeat(auto-fill,minmax(96px,1fr))] gap-2 overflow-y-auto">
          {media.data.items.map((item) => (
            <button
              key={item.id}
              type="button"
              disabled={disabled}
              onClick={() => onPick(item)}
              title={item.name ?? item.kind}
              className="flex flex-col items-center gap-1 rounded-md p-1 text-left hover:bg-bg"
            >
              <MediaThumb item={item} size={88} />
              <span className="w-full truncate text-[11px]">{item.name || "Untitled"}</span>
              <span className="text-[10px] text-muted">{item.kind}</span>
            </button>
          ))}
        </div>
      )}
      {pages > 1 && (
        <div className="mt-2 flex items-center justify-end gap-2 text-xs">
          <button type="button" className="btn btn-secondary btn-sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            Previous
          </button>
          <span className="text-muted">
            Page {page} of {pages}
          </span>
          <button type="button" className="btn btn-secondary btn-sm" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
            Next
          </button>
        </div>
      )}
    </div>
  );
}

// Command Chat panel (SPEC-FE-008 markup; SPEC-FE-041 behavior): plan cards
// render for every plan reply (also after a reload, via plan_id), clarifying
// questions show what they're waiting for, and "Start over" drops the
// pending draft.
export default function ChatPanel() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: orchestratorKeys.messages, queryFn: fetchMessages });
  const [text, setText] = useState("");
  const [sentPlans, setSentPlans] = useState<Record<string, PlanRead>>({});
  const bottom = useRef<HTMLDivElement>(null);

  const send = useMutation({
    mutationFn: (body: string) => sendMessage(body),
    onSuccess: (res) => {
      const { reply, plan, ...userMessage } = res;
      queryClient.setQueryData<ChatMessage[]>(orchestratorKeys.messages, (old) => [...(old ?? []), userMessage, reply]);
      if (plan) setSentPlans((p) => ({ ...p, [plan.id]: plan }));
      setText("");
    },
    // On failure the typed text stays so the user can retry.
  });
  const startOver = useMutation({
    mutationFn: discardDraft,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: orchestratorKeys.messages }),
  });

  const messages = query.data ?? [];
  const lastAi = [...messages].reverse().find((m) => m.sender === "ai");
  const waiting = lastAi?.kind === "clarification" && !startOver.isSuccess ? lastAi : null;
  // SPEC-FE-056: "media id" is the label of the ad's image/video question (SPEC-BE-090).
  const wantsMedia = !!waiting?.waiting_for.includes("media id");
  const [picking, setPicking] = useState(false);
  const pickMedia = (item: MediaItem) => {
    setPicking(false);
    send.mutate(`Use the ${item.kind} "${item.name || "untitled"}" (${item.id})`);
  };

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [messages.length]);
  useEffect(() => {
    if (lastAi && lastAi.kind !== "clarification") startOver.reset();
  }, [lastAi?.id]);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (text.trim()) send.mutate(text.trim());
  };

  return (
    <div className="chat-panel">
      <div className="chat-header">Conversation with AI Orchestrator</div>
      <div className="chat-messages">
        {query.isPending ? (
          <p className="text-[13px] text-muted">Loading conversation…</p>
        ) : query.isError ? (
          <p className="text-[13px] text-danger" role="alert">
            Failed to load messages: {query.error.message}
          </p>
        ) : (
          messages.map((m) => (
            <div key={m.id} className="contents">
              <div className={m.sender === "user" ? "msg user" : "msg ai"}>
                <div className="whitespace-pre-line">{m.body}</div>
                {m.kind === "summary" && m.results.length > 0 && <Results items={m.results} />}
                {m.kind === "clarification" && m.waiting_for.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    <span className="badge badge-warn">Waiting for: {m.waiting_for.join(", ")}</span>
                  </div>
                )}
              </div>
              {m.kind === "plan" && m.plan_id && <PlanCard planId={m.plan_id} initial={sentPlans[m.plan_id]} />}
            </div>
          ))
        )}
        {send.isPending && <div className="msg ai text-muted">Thinking…</div>}
        <div ref={bottom} />
      </div>
      {waiting && (
        <div className="flex items-center justify-between gap-2 px-[14px] pt-2 text-xs text-muted">
          <span>Answer the question above, or</span>
          <div className="flex gap-2">
            {wantsMedia && (
              <button type="button" className="btn btn-sm" disabled={send.isPending} onClick={() => setPicking((v) => !v)}>
                Choose from media library
              </button>
            )}
            <button type="button" className="btn btn-secondary btn-sm" disabled={startOver.isPending} onClick={() => startOver.mutate()}>
              Start over
            </button>
          </div>
        </div>
      )}
      {wantsMedia && picking && <ChatMediaPicker onPick={pickMedia} onClose={() => setPicking(false)} disabled={send.isPending} />}
      <form className="chat-input" onSubmit={onSubmit}>
        <input
          placeholder={waiting ? `Your answer (${waiting.waiting_for.join(", ") || "details"})…` : "Message the orchestrator..."}
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={send.isPending}
          aria-label="Message the orchestrator"
        />
        <button type="submit" className="btn" disabled={send.isPending || !text.trim()}>
          {send.isPending ? "Sending…" : "Send"}
        </button>
      </form>
      {send.isError && (
        <p className="m-0 px-[14px] pb-3 text-xs text-danger" role="alert">
          {send.error.message}
        </p>
      )}
    </div>
  );
}
