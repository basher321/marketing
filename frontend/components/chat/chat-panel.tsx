"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";

import { formatMoney } from "@/lib/format/money";
import { fetchMedia, fetchMediaItem, mediaKeys } from "@/lib/api/media";
import { discardDraft, fetchChat, fetchChatMessages, fetchProject, orchestratorKeys, sendMessage } from "@/lib/api/orchestrator";
import { ApiError } from "@/lib/types/common";
import type { MediaItem, MediaKind } from "@/lib/types/media";
import type { ChatMessage, PlanRead, ResultItem } from "@/lib/types/orchestrator";

import { MediaThumb } from "../organic/media-picker";
import { AttachButton, AttachmentChips, DropOverlay, MessageFiles, useAttachments, useDropZone } from "./attachments";
import { FixLine } from "./job-board";
import PlanCard from "./plan-card";
import {
  MicIcon,
  ReplyVoice,
  VoiceBar,
  canRecord,
  languageLabel,
  useReplyPlayer,
  useVoiceRecorder,
  useVoiceRepliesSetting,
} from "./voice";

export { orchestratorKeys };

// ---------------------------------------------------------------------------
// Generative UI catalog (SPEC-FE-061). The backend's structured output
// (message kind, waiting_for, plan_id, results[].data / .media) picks which
// of these components renders; the model never sends markup. Every number
// and label shown is the backend's own.
// ---------------------------------------------------------------------------

// Welcome suggestions: each uses an existing Command Chat action.
const SUGGESTIONS: { icon: string; title: string; hint: string; commands: string[] }[] = [
  { icon: "🛒", title: "E-Commerce", hint: "Products, orders and stock", commands: ["Show products low on stock", "Show my latest orders"] },
  { icon: "📣", title: "Paid Marketing", hint: "Campaigns and results", commands: ["Show my campaigns", "Show campaign results for the last 7 days"] },
  { icon: "🌱", title: "Organic Marketing", hint: "Posts and what's working", commands: ["What's working on my organic posts?", "Show my scheduled organic posts"] },
  { icon: "⚙️", title: "Workflows", hint: "Automate the busywork", commands: ["Show my workflows", "Create a workflow that notifies me when stock is low"] },
  { icon: "🚚", title: "Shipping", hint: "Zones and delivery rates", commands: ["Show my shipping setup", "Show my shipping zones and rates"] },
];
const QUICK = ["Show products low on stock", "Show my campaigns", "What's working on my organic posts?"];
// Decorative while the plan is drafted: it claims no step has happened.
const THINKING = ["Understanding your request…", "Looking at your business data…", "Drafting a plan…"];

function clockTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function label(col: string): string {
  return col.replace(/_/g, " ");
}

function cellText(row: Record<string, unknown>, col: string): string {
  const v = row[col];
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "number") {
    if (/price|amount|spend|revenue|total|cost|budget/.test(col) && typeof row.currency === "string") return formatMoney(v, row.currency);
    return v.toLocaleString("en-US", { maximumFractionDigits: 2 });
  }
  if (Array.isArray(v)) return v.map((x) => (typeof x === "object" ? JSON.stringify(x) : String(x))).join(", ");
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function Cell({ row, col }: { row: Record<string, unknown>; col: string }) {
  const v = row[col];
  if (col === "status" && typeof v === "string") {
    const tone = /fail|cancel|error|out_of_stock/.test(v) ? "badge-danger" : /active|running|published|succeeded|delivered|enabled/.test(v) ? "badge-success" : /pending|draft|paused|scheduled/.test(v) ? "badge-warn" : "badge-neutral";
    return <span className={`badge ${tone}`}>{label(v)}</span>;
  }
  if (col === "low_stock" && typeof v === "boolean") return v ? <span className="badge badge-warn">Low</span> : <span className="text-muted">—</span>;
  return <>{cellText(row, col)}</>;
}

type View = "tiles" | "bars" | "table";

/** Picks the component for a result's rows by their shape. */
function shapeOf(rows: Record<string, unknown>[]) {
  const cols = Object.keys(rows[0] ?? {}).filter((c) => !c.endsWith("_id") && c !== "id" && c !== "currency");
  const numeric = cols.filter((c) => rows.every((r) => typeof r[c] === "number"));
  const text = cols.filter((c) => !numeric.includes(c) && rows.every((r) => typeof r[c] === "string" || r[c] === null));
  const tiles = rows.length === 1 && numeric.length >= 1 && numeric.length <= 6;
  const bars = rows.length >= 2 && rows.length <= 12 && numeric.length >= 1 && text.length >= 1;
  const initial: View = tiles ? "tiles" : bars && numeric.length <= 2 && cols.length <= 4 ? "bars" : "table";
  return { cols, numeric, text, tiles, bars, initial };
}

function ResultData({ rows }: { rows: Record<string, unknown>[] }) {
  const shape = shapeOf(rows);
  const [view, setView] = useState<View>(shape.initial);
  const [metric, setMetric] = useState(shape.numeric[0] ?? "");
  if (!shape.cols.length) return null;
  const views: View[] = [...(shape.tiles ? (["tiles"] as const) : []), ...(shape.bars ? (["bars"] as const) : []), "table"];
  const max = Math.max(1, ...rows.map((r) => Math.abs(Number(r[metric]) || 0)));
  return (
    <div>
      {views.length > 1 && (
        <div className="mt-1.5 flex flex-wrap items-center gap-2">
          <div className="cc-seg" role="group" aria-label="View">
            {views.map((v) => (
              <button key={v} type="button" aria-pressed={view === v} onClick={() => setView(v)}>
                {v === "tiles" ? "Cards" : v === "bars" ? "Chart" : "Table"}
              </button>
            ))}
          </div>
          {view === "bars" && shape.numeric.length > 1 && (
            <div className="cc-seg" role="group" aria-label="Measure">
              {shape.numeric.map((m) => (
                <button key={m} type="button" aria-pressed={metric === m} onClick={() => setMetric(m)}>
                  {label(m)}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      {view === "tiles" ? (
        <div className="cc-tiles">
          {shape.cols.map((c) => (
            <div key={c} className="cc-tile">
              <div className="cc-tile-label">{label(c)}</div>
              <div className={shape.numeric.includes(c) ? "cc-tile-value" : "mt-1 text-[13px] font-medium"}>
                <Cell row={rows[0]} col={c} />
              </div>
            </div>
          ))}
        </div>
      ) : view === "bars" ? (
        <div className="cc-bars">
          {rows.map((r, i) => {
            const value = Number(r[metric]) || 0;
            return (
              <div key={i} className="cc-bar-row">
                <span className="cc-bar-label" title={cellText(r, shape.text[0])}>
                  {cellText(r, shape.text[0])}
                </span>
                <span className="cc-bar-track">
                  <span className="cc-bar-fill block" style={{ width: `${Math.max(2, (Math.abs(value) / max) * 100)}%`, animationDelay: `${i * 40}ms` }} />
                </span>
                <span className="tabular-nums font-medium">{cellText(r, metric)}</span>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="cc-table">
          <table>
            <thead>
              <tr>
                {shape.cols.slice(0, 8).map((c) => (
                  <th key={c}>{label(c)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 25).map((r, i) => (
                <tr key={i}>
                  {shape.cols.slice(0, 8).map((c) => (
                    <td key={c}>
                      <Cell row={r} col={c} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {view === "table" && rows.length > 25 && <div className="mt-1 text-[11px] text-muted">…and {rows.length - 25} more</div>}
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
  if (!q.data) return <div className="cc-shimmer mt-2 h-[180px] w-full max-w-[320px] rounded-xl" />;
  const url = q.data.url;
  return (
    <div className="mt-2 grid max-w-[340px] gap-1" data-testid="chat-result-media">
      {media.kind === "video" ? (
        <video src={url} controls playsInline className="max-h-[340px] w-full rounded-xl border border-border bg-bg object-contain" />
      ) : (
        <img src={url} alt={q.data.name ?? "Generated image"} className="max-h-[340px] w-full rounded-xl border border-border bg-bg object-contain" />
      )}
      <a href={url} download={q.data.name ?? undefined} target="_blank" rel="noreferrer" className="text-[11px] text-accent underline">
        Download
      </a>
    </div>
  );
}

const RESULT_ICON: Record<string, string> = { succeeded: "✓", failed: "✕", skipped: "–", rejected: "–" };

// The result summary (SPEC-BE-059 §5): the backend's own text plus its
// structured results, each rendered by its shape.
function ResultsCard({ items }: { items: ResultItem[] }) {
  return (
    <div className="cc-card">
      <div className="cc-card-head">
        <span className="cc-card-icon" aria-hidden="true">
          ✨
        </span>
        Results
      </div>
      <div className="grid gap-3">
        {items.map((r) => (
          <div key={r.index} className="min-w-0 text-[12.5px]">
            <div className="flex flex-wrap items-center gap-1.5">
              <span
                className={`inline-grid h-5 w-5 place-items-center rounded-full text-[11px] font-bold ${
                  r.status === "succeeded" ? "bg-success text-white" : r.status === "failed" ? "bg-danger text-white" : "bg-bg text-muted"
                }`}
                aria-hidden="true"
              >
                {RESULT_ICON[r.status] ?? "•"}
              </span>
              <b>{r.label}</b>
              {r.link &&
                (r.link.startsWith("/") ? (
                  <Link href={r.link} target="_blank" rel="noopener" className="ml-1 text-accent underline">
                    Open
                  </Link>
                ) : (
                  <a href={r.link} target="_blank" rel="noreferrer" className="ml-1 text-accent underline">
                    Open in Ads Manager
                  </a>
                ))}
            </div>
            {r.summary && <div className={`ml-[26px] mt-0.5 ${r.status === "failed" ? "text-danger" : "text-muted"}`}>{r.summary}</div>}
            {r.status === "failed" && r.fix && <div className="ml-[26px] mt-0.5"><FixLine fix={r.fix} /></div>}
            {r.data && r.data.length > 0 && (
              <div className="ml-[26px]">
                <ResultData rows={r.data} />
              </div>
            )}
            {r.media && r.status === "succeeded" && (
              <div className="ml-[26px]">
                <ResultMediaPreview media={r.media} />
              </div>
            )}
          </div>
        ))}
      </div>
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
    <div className="cc-card mt-2" data-testid="chat-media-picker">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        {([["", "All"], ["image", "Images"], ["video", "Videos"]] as const).map(([k, text]) => (
          <button
            key={text}
            type="button"
            className="cc-chip"
            aria-pressed={kind === k}
            style={kind === k ? { borderColor: "var(--accent)", background: "var(--accent-soft)" } : undefined}
            onClick={() => {
              setKind(k);
              setPage(1);
            }}
          >
            {text}
          </button>
        ))}
        <input
          className="min-w-[140px] flex-1 rounded-lg border border-border bg-bg px-2.5 py-1.5 text-[13px]"
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
              className="flex flex-col items-center gap-1 rounded-lg p-1 text-left hover:bg-bg"
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

function Thinking() {
  const [stage, setStage] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setStage((s) => Math.min(s + 1, THINKING.length - 1)), 1800);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="cc-row">
      <span className="cc-orb cc-orb-sm" data-busy="true" aria-hidden="true" />
      <div className="cc-bubble ai flex items-center gap-2.5 text-muted">
        <span className="cc-dots" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
        {THINKING[stage]}
      </div>
    </div>
  );
}

function Welcome({ composer, onPick, disabled }: { composer: ReactNode; onPick: (cmd: string) => void; disabled: boolean }) {
  return (
    <div className="cc-welcome">
      <span className="cc-orb cc-orb-lg mx-auto block" aria-hidden="true" />
      <h2 className="cc-hero-title">What should we get done today?</h2>
      <p className="m-0 text-[13.5px] text-muted">
        Type or speak in any language. I turn it into a plan across your store, ads, posts and workflows, and nothing that
        changes your business or spends money runs without your approval.
      </p>
      <div className="cc-idle-composer">{composer}</div>
      <div className="cc-suggest-grid">
        {SUGGESTIONS.map((s, i) => (
          <div key={s.title} className="cc-suggest" style={{ animationDelay: `${i * 60}ms` }}>
            <div className="flex items-center gap-2">
              <span className="cc-card-icon" aria-hidden="true">
                {s.icon}
              </span>
              <div>
                <div className="text-[13px] font-semibold">{s.title}</div>
                <div className="text-[11.5px] text-muted">{s.hint}</div>
              </div>
            </div>
            {s.commands.map((c) => (
              <button key={c} type="button" className="cc-suggest-cmd" disabled={disabled} onClick={() => onPick(c)}>
                → {c}
              </button>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      className="cc-link"
      onClick={() =>
        void navigator.clipboard?.writeText(text).then(() => {
          setDone(true);
          setTimeout(() => setDone(false), 1500);
        })
      }
    >
      {done ? "✓ Copied" : "Copy"}
    </button>
  );
}

/** The bubble text by kind: a plan card / results card already shows the steps. */
function bubbleText(m: ChatMessage): string {
  if (m.kind === "plan" && m.plan_id) {
    const lines = m.body.split("\n");
    const kept = lines.filter((l) => !/^\d+\.\s/.test(l));
    return kept.length ? kept.join("\n") : m.body;
  }
  if (m.kind === "summary" && m.results.length > 0) return m.body.split("\n")[0];
  return m.body;
}

// Command Chat panel (SPEC-FE-008/041 behavior, SPEC-FE-061 look, SPEC-FE-062
// voice): plan cards render for every plan reply (also after a reload, via
// plan_id), clarifying questions show what they're waiting for, and "Start
// over" drops the pending draft.
export default function ChatPanel({ chatId = null, newChatProjectId = null, initialText = "", onChatCreated, onOpenHistory }: {
  /** The open chat (SPEC-FE-066); null = a new, empty chat. */
  chatId?: string | null;
  /** The project a new chat starts in. */
  newChatProjectId?: string | null;
  /** Put in the composer, not sent: a Dashboard quick action or palette request (?ask=). */
  initialText?: string;
  onChatCreated?: (id: string) => void;
  onOpenHistory?: () => void;
} = {}) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: orchestratorKeys.chatMessages(chatId),
    queryFn: () => fetchChatMessages(chatId as string),
    enabled: !!chatId,
  });
  const chatInfo = useQuery({ queryKey: orchestratorKeys.chat(chatId ?? "none"), queryFn: () => fetchChat(chatId as string), enabled: !!chatId });
  const newProject = useQuery({ queryKey: orchestratorKeys.project(newChatProjectId ?? "none"), queryFn: () => fetchProject(newChatProjectId as string), enabled: !chatId && !!newChatProjectId });
  const [text, setText] = useState(initialText);
  const [voiceMark, setVoiceMark] = useState<{ language: string | null } | null>(null);
  const [sentPlans, setSentPlans] = useState<Record<string, PlanRead>>({});
  const bottom = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const [voiceReplies, setVoiceReplies] = useVoiceRepliesSetting();
  const player = useReplyPlayer();
  // Attachments (SPEC-FE-064): 📎, drag-and-drop over the chat, or paste.
  const attach = useAttachments();
  const drop = useDropZone(attach.add);
  const [micOk, setMicOk] = useState(true);
  useEffect(() => setMicOk(canRecord()), []);

  const send = useMutation({
    mutationFn: (v: { body: string; voice?: { language: string | null }; fileIds?: string[] }) =>
      sendMessage(v.body, v.voice, v.fileIds ?? [], { chatId, projectId: newChatProjectId }),
    onSuccess: (res) => {
      const { reply, plan, ...userMessage } = res;
      const target = res.chat_id ?? chatId;
      queryClient.setQueryData<ChatMessage[]>(orchestratorKeys.chatMessages(target ?? null), (old) => [...(old ?? []), userMessage, reply]);
      void queryClient.invalidateQueries({ queryKey: orchestratorKeys.chats });
      if (target && target !== chatId) {
        void queryClient.invalidateQueries({ queryKey: orchestratorKeys.projects });
        onChatCreated?.(target); // a new chat: the page opens it (?c=)
      }
      if (plan) setSentPlans((p) => ({ ...p, [plan.id]: plan }));
      setText("");
      setVoiceMark(null);
      attach.clear();
      input.current?.focus();
    },
    // On failure the typed text stays so the user can retry.
  });
  const startOver = useMutation({
    mutationFn: () => discardDraft(chatId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: orchestratorKeys.messages }),
  });

  // Voice command -> transcript in the composer for review (the user's choice).
  const recorder = useVoiceRecorder((t) => {
    setText(t.text);
    setVoiceMark({ language: t.language });
    requestAnimationFrame(() => input.current?.focus());
  });
  const recording = recorder.state !== "idle";

  const messages = (chatId ? query.data : undefined) ?? [];
  const idle = (chatId ? query.isSuccess : true) && messages.length === 0 && !send.isPending;
  const wasIdle = useRef(false);
  const [dropIn, setDropIn] = useState(false);
  useEffect(() => {
    if (wasIdle.current && !idle) setDropIn(true);
    wasIdle.current = idle;
  }, [idle]);
  const lastAi = [...messages].reverse().find((m) => m.sender === "ai");
  const lastUser = [...messages].reverse().find((m) => m.sender === "user");
  // Replies are spoken in the language asked for ("reply in English"), else the one spoken (SPEC-FE-062 Amendment C).
  const replyLanguage = (m: ChatMessage | undefined) => m?.reply_language ?? m?.voice_language ?? null;
  const lastVoiceLanguage = replyLanguage([...messages].reverse().find((m) => m.sender === "user" && m.voice));
  const waiting = lastAi?.kind === "clarification" && !startOver.isSuccess ? lastAi : null;
  // SPEC-FE-056: "media id" is the label of the ad's image/video question (SPEC-BE-090).
  const wantsMedia = !!waiting?.waiting_for.includes("media id");
  const [picking, setPicking] = useState(false);
  const submit = (body: string, voice?: { language: string | null }) => {
    if (send.isPending || attach.busy) return; // Send waits for uploads to finish
    const fileIds = attach.ready.map((f) => f.id);
    const message = body.trim() || (fileIds.length ? "Read these files and suggest jobs" : "");
    if (message) send.mutate({ body: message, voice, fileIds });
  };
  const pickMedia = (item: MediaItem) => {
    setPicking(false);
    submit(`Use the ${item.kind} "${item.name || "untitled"}" (${item.id})`);
  };

  // Spoken replies (SPEC-FE-062): after a voice command, each new AI message
  // (the reply now, the summary later) is read in the command's language.
  // A new chat starts with nothing seen, so its first reply can be spoken too.
  const seen = useRef<Set<string> | null>(chatId ? null : new Set());
  useEffect(() => {
    if (!query.data) return;
    if (seen.current === null) {
      seen.current = new Set(query.data.map((m) => m.id));
      return;
    }
    const known = seen.current;
    const fresh = query.data.filter((m) => !known.has(m.id));
    fresh.forEach((m) => known.add(m.id));
    if (!voiceReplies || !lastUser?.voice) return;
    const after = query.data.slice(query.data.findIndex((m) => m.id === lastUser.id) + 1);
    // In order: the reply now, the summary when its steps finish (queued, never cut off).
    fresh
      .filter((m) => m.sender === "ai" && m.kind !== "progress" && after.some((a) => a.id === m.id))
      .forEach((m) => player.enqueue(m.id, replyLanguage(lastUser)));
  }, [query.data]);

  // The first view jumps to the latest message (again once cards have laid
  // out); later messages scroll smoothly.
  const scrolledOnce = useRef(false);
  useEffect(() => {
    if (!messages.length) return;
    if (!scrolledOnce.current) {
      scrolledOnce.current = true;
      bottom.current?.scrollIntoView({ block: "end" });
      const t = setTimeout(() => bottom.current?.scrollIntoView({ block: "end" }), 400);
      return () => clearTimeout(t);
    }
    bottom.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages.length, send.isPending]);
  useEffect(() => {
    if (lastAi && lastAi.kind !== "clarification") startOver.reset();
  }, [lastAi?.id]);
  // Auto-growing composer: up to 8 lines (200px, the CSS max-height), then it
  // scrolls. Re-measured when it moves between the middle and the bottom.
  useLayoutEffect(() => {
    const el = input.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [text, recording, idle]);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit(text, voiceMark ?? undefined);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit(text, voiceMark ?? undefined);
    }
  };
  const startRecording = () => {
    player.stopAll();
    void recorder.start();
  };

  // One composer, in the middle while the chat is empty (ChatGPT / Claude style)
  // and at the bottom once it starts (SPEC-FE-061 Amendment A).
  const composer = (
      <div className={`cc-composer-wrap ${dropIn ? "cc-drop" : ""}`}>
        {!idle && !recording && !text && !waiting && messages.length > 0 && (
          <div className="cc-quick mb-2">
            {QUICK.map((q) => (
              <button key={q} type="button" className="cc-chip" disabled={send.isPending} onClick={() => submit(q)}>
                ✦ {q}
              </button>
            ))}
          </div>
        )}
        {recording ? (
          <VoiceBar rec={recorder} />
        ) : (
          <>
          <AttachmentChips items={attach.items} onRemove={attach.remove} />
          <form className="cc-composer" onSubmit={onSubmit}>
            <div className="flex min-w-0 flex-1 flex-col">
              {voiceMark && (
                <span className="cc-voice-badge ml-1.5 mt-1 self-start">
                  🎙 {languageLabel(voiceMark.language)}
                  <button type="button" className="cc-link ml-1" aria-label="Send as typed text instead" onClick={() => setVoiceMark(null)}>
                    ✕
                  </button>
                </span>
              )}
              <textarea
                ref={input}
                rows={1}
                className="cc-textarea"
                placeholder={
                  waiting
                    ? `Your answer (${waiting.waiting_for.join(", ") || "details"})…`
                    : "Ask anything, or tap the mic and speak in any language…"
                }
                value={text}
                onChange={(e) => {
                  setText(e.target.value);
                  if (!e.target.value.trim()) setVoiceMark(null);
                }}
                onKeyDown={onKeyDown}
                onPaste={(e) => {
                  const files = Array.from(e.clipboardData.files);
                  if (files.length) {
                    e.preventDefault();
                    attach.add(files);
                  }
                }}
                disabled={send.isPending}
                aria-label="Message the orchestrator"
              />
            </div>
            <AttachButton onFiles={attach.add} disabled={send.isPending} />
            <button
              type="button"
              className="cc-icon-btn"
              onClick={startRecording}
              disabled={send.isPending || !micOk}
              aria-label="Speak a command"
              title={micOk ? "Speak a command (any language)" : "This browser can't record audio"}
            >
              <MicIcon />
            </button>
            <button
              type="submit"
              className="cc-icon-btn primary"
              disabled={send.isPending || attach.busy || (!text.trim() && attach.ready.length === 0)}
              aria-label="Send"
              title={attach.busy ? "Waiting for the files to finish uploading" : "Send (Enter)"}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M5 12h14M13 6l6 6-6 6" />
              </svg>
            </button>
          </form>
          </>
        )}
        {send.isError && (
          <p className="m-0 mt-1.5 px-1 text-xs text-danger" role="alert">
            {send.error.message}
          </p>
        )}
      </div>
  );

  return (
    <section className={`cc-panel ${idle ? "idle" : ""}`} aria-label="Command Chat" {...drop.props}>
      {drop.over && <DropOverlay />}
      <header className="cc-header">
        <span className="cc-orb" data-busy={send.isPending || player.current !== null} aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <span className="cc-title">PilotSonic</span>
            {(chatInfo.data?.project ?? (newProject.data ? { emoji: newProject.data.emoji, name: newProject.data.name } : null)) && (
              <span className="cc-proj-chip" data-testid="project-chip">
                {(chatInfo.data?.project ?? newProject.data)?.emoji} {(chatInfo.data?.project ?? newProject.data)?.name}
              </span>
            )}
            {chatInfo.data && <span className="hidden truncate text-[12px] text-muted sm:inline" title={chatInfo.data.title}>· {chatInfo.data.title}</span>}
          </div>
          <div className="cc-status">
            <span className="cc-status-dot" aria-hidden="true" />
            {send.isPending ? "Planning…" : player.current ? "Speaking…" : "Online · changes wait for your approval"}
          </div>
        </div>
        {onOpenHistory && (
          <button type="button" className="btn btn-secondary btn-sm cc-hist-open" onClick={onOpenHistory} aria-label="Chats and projects">
            🕘 Chats
          </button>
        )}
        <label className="flex cursor-pointer items-center gap-2 text-xs text-muted" title="Read replies aloud after a voice command">
          <span className="hidden sm:inline">Voice replies</span>
          <button
            type="button"
            role="switch"
            aria-checked={voiceReplies}
            aria-label="Voice replies"
            className="cc-switch"
            onClick={() => {
              if (voiceReplies) player.stopAll();
              setVoiceReplies(!voiceReplies);
            }}
          />
        </label>
      </header>

      {idle ? (
        <div className="cc-idle">
          <Welcome composer={composer} onPick={(c) => submit(c)} disabled={send.isPending} />
        </div>
      ) : (
      <div className="cc-scroll" role="log" aria-live="polite" aria-label="Conversation">
        {chatId && query.isPending ? (
          <div className="grid gap-3">
            <div className="cc-shimmer h-10 w-2/3" />
            <div className="cc-shimmer ml-auto h-10 w-1/2" />
            <div className="cc-shimmer h-24 w-3/4" />
          </div>
        ) : chatId && query.isError ? (
          <p className="text-[13px] text-danger" role="alert">
            Failed to load messages: {query.error.message}
          </p>
        ) : (
          messages.map((m) =>
            m.sender === "user" ? (
              <div key={m.id} className="cc-row user">
                <div className="cc-stack">
                  {m.files?.length > 0 && <MessageFiles files={m.files} />}
                  <div className="cc-bubble user whitespace-pre-line">{m.body}</div>
                  <div className="cc-meta">
                    {m.voice && <span className="cc-voice-badge">🎙 Voice · {languageLabel(m.voice_language)}</span>}
                    <span>{clockTime(m.sent_at)}</span>
                  </div>
                </div>
              </div>
            ) : (
              <div key={m.id} className="cc-row">
                <span className="cc-orb cc-orb-sm" data-busy={player.current === m.id} aria-hidden="true" />
                <div className={`cc-stack ${m.kind === "plan" || m.kind === "summary" || m.kind === "clarification" ? "wide" : ""}`}>
                  {m.kind === "clarification" ? (
                    <div className="cc-card cc-question">
                      <div className="cc-card-head">
                        <span className="cc-card-icon" aria-hidden="true">
                          💬
                        </span>
                        Needs a few details
                      </div>
                      <div className="whitespace-pre-line text-[13.5px]">{m.body}</div>
                      {m.waiting_for.length > 0 && (
                        <div className="mt-2 flex flex-wrap items-center gap-1.5">
                          <span className="text-[11px] text-muted">Waiting for:</span>
                          {m.waiting_for.map((w) => (
                            <span key={w} className="cc-chip">
                              {w}
                            </span>
                          ))}
                        </div>
                      )}
                      {waiting?.id === m.id && (
                        <div className="mt-2.5 flex flex-wrap gap-2">
                          {wantsMedia && (
                            <button type="button" className="btn btn-sm" disabled={send.isPending} onClick={() => setPicking((v) => !v)}>
                              Choose from media library
                            </button>
                          )}
                          <button type="button" className="btn btn-secondary btn-sm" disabled={startOver.isPending} onClick={() => startOver.mutate()}>
                            Start over
                          </button>
                        </div>
                      )}
                    </div>
                  ) : (
                    m.kind === "progress" ? (
                      <div className={`cc-progress-line ${m.body.startsWith("✗") ? "is-fail" : ""}`}>{m.body}</div>
                    ) : (
                      <div className="cc-bubble ai whitespace-pre-line">{bubbleText(m)}</div>
                    )
                  )}
                  {waiting?.id === m.id && wantsMedia && picking && (
                    <ChatMediaPicker onPick={pickMedia} onClose={() => setPicking(false)} disabled={send.isPending} />
                  )}
                  {m.kind === "plan" && m.plan_id && <PlanCard planId={m.plan_id} initial={sentPlans[m.plan_id]} />}
                  {m.kind === "summary" && m.results.length > 0 && <ResultsCard items={m.results} />}
                  <div className="cc-meta">
                    <span>{clockTime(m.sent_at)}</span>
                    <CopyButton text={m.body} />
                    <ReplyVoice audio={player.replies[m.id]} shownText={m.body} onToggle={() => player.toggle(m.id, lastVoiceLanguage)} />
                  </div>
                </div>
              </div>
            ),
          )
        )}
        {send.isPending && <Thinking />}
        <div ref={bottom} />
      </div>
      )}

      {!idle && !(chatId && query.isPending) && composer}
    </section>
  );
}
