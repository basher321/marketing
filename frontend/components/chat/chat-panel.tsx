"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { discardDraft, fetchMessages, orchestratorKeys, sendMessage } from "@/lib/api/orchestrator";
import type { ChatMessage, PlanRead, ResultItem } from "@/lib/types/orchestrator";

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
              <Link href={r.link} className="ml-1.5 text-accent underline">
                Open
              </Link>
            ) : (
              <a href={r.link} target="_blank" rel="noreferrer" className="ml-1.5 text-accent underline">
                Open in Ads Manager
              </a>
            ))}
          {r.data && r.data.length > 0 && <ResultTable rows={r.data} />}
        </div>
      ))}
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
          <button type="button" className="btn btn-secondary btn-sm" disabled={startOver.isPending} onClick={() => startOver.mutate()}>
            Start over
          </button>
        </div>
      )}
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
