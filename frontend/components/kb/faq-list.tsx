"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { channelLabel } from "@/components/customer/conversations-table";
import { createFaq, deleteFaq, fetchFaqs, kbKeys, updateFaq } from "@/lib/api/kb";
import { ApiError } from "@/lib/types/common";
import type { FAQItem, FAQList } from "@/lib/types/kb";

// Live channel_type values, offered as the FAQ's "Applied to" choices.
const CHANNELS = ["whatsapp", "instagram", "messenger", "facebook", "email", "sms", "web", "tiktok"];
const FORBIDDEN = "Only managers and above can edit the knowledge base.";

// "Applied to: WhatsApp, IG DM, Email" (mockup). The backend stores [] for "all
// channels" (SPEC-BE-013), so only an empty list reads "All channels".
function appliedTo(channels: string[]): string {
  return channels.length === 0 ? "All channels" : channels.map(channelLabel).join(", ");
}

/** A readable message: 403 in plain words; FastAPI 422 field errors joined; else the backend's text. */
export function kbErrorText(err: Error): string {
  if (err instanceof ApiError) {
    if (err.status === 403) return FORBIDDEN;
    const detail = (err.body as { detail?: unknown } | undefined)?.detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d: { msg?: string }) => (d.msg ?? "").replace(/^Value error, /, ""))
        .filter(Boolean)
        .join(" ");
    }
  }
  return err.message;
}

function FaqForm({
  initial,
  submitLabel,
  busy,
  error,
  onSubmit,
  onCancel,
}: {
  initial: { question: string; answer: string; channels: string[] };
  submitLabel: string;
  busy: boolean;
  error: Error | null;
  onSubmit: (v: { question: string; answer: string; channels: string[] }) => void;
  onCancel: () => void;
}) {
  const [question, setQuestion] = useState(initial.question);
  const [answer, setAnswer] = useState(initial.answer);
  const [channels, setChannels] = useState<string[]>(initial.channels);
  const toggle = (ch: string) => setChannels((cur) => (cur.includes(ch) ? cur.filter((c) => c !== ch) : [...cur, ch]));
  const idp = submitLabel === "Add FAQ" ? "faq" : "faq_edit";
  return (
    <form
      className="mt-3"
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        onSubmit({ question, answer, channels });
      }}
    >
      <div className="form-row">
        <label htmlFor={`${idp}_question`}>Question</label>
        <input id={`${idp}_question`} required value={question} onChange={(e) => setQuestion(e.target.value)} />
      </div>
      <div className="form-row">
        <label htmlFor={`${idp}_answer`}>Answer</label>
        <textarea id={`${idp}_answer`} required rows={3} value={answer} onChange={(e) => setAnswer(e.target.value)} />
      </div>
      <fieldset className="form-row border-none p-0">
        <legend className="mb-1.5 text-[13px] font-medium">Applied to (none = all channels)</legend>
        <div className="flex flex-wrap gap-3 text-[13px]">
          {CHANNELS.map((ch) => (
            <label key={ch} className="flex items-center gap-1 font-normal">
              <input type="checkbox" checked={channels.includes(ch)} onChange={() => toggle(ch)} />
              {channelLabel(ch)}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="flex gap-2">
        <button type="submit" className="btn btn-sm" disabled={busy}>
          {busy ? "Saving…" : submitLabel}
        </button>
        <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
      {error && (
        <p className="mb-0 mt-3 text-xs text-danger" role="alert">
          {kbErrorText(error)}
        </p>
      )}
    </form>
  );
}

// One FAQ in the full (KB › FAQs tab) list: answer, Enabled toggle, inline
// Edit and Delete (SPEC-FE-033 / SPEC-BE-048).
function FaqRow({ faq }: { faq: FAQItem }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const replace = (item: FAQItem) =>
    queryClient.setQueryData<FAQList>(kbKeys.faqs, (old) => (old ? { ...old, items: old.items.map((f) => (f.id === item.id ? item : f)) } : old));
  const save = useMutation({
    mutationFn: (v: { question: string; answer: string; channels: string[] }) => updateFaq(faq.id, v),
    onSuccess: (item) => {
      replace(item);
      setEditing(false);
    },
  });
  const toggle = useMutation({ mutationFn: () => updateFaq(faq.id, { enabled: !faq.enabled }), onSuccess: replace });
  const remove = useMutation({
    mutationFn: () => deleteFaq(faq.id),
    onSuccess: () =>
      queryClient.setQueryData<FAQList>(kbKeys.faqs, (old) =>
        old ? { count: old.count - 1, items: old.items.filter((f) => f.id !== faq.id) } : old,
      ),
  });
  const err = toggle.error ?? remove.error;
  if (editing) {
    return (
      <div className="kb-item block" data-faq={faq.id}>
        <FaqForm initial={faq} submitLabel="Save" busy={save.isPending} error={save.error} onSubmit={(v) => save.mutate(v)} onCancel={() => setEditing(false)} />
      </div>
    );
  }
  return (
    <div className={`kb-item ${faq.enabled ? "" : "opacity-60"}`} data-faq={faq.id}>
      <div className="kb-item-icon">?</div>
      <div className="flex-1">
        <b>{faq.question}</b>
        <p className="m-0 mt-1 whitespace-pre-line text-[13px]">{faq.answer}</p>
        <span className="text-xs text-muted">Applied to: {appliedTo(faq.channels)}</span>
        {err && (
          <p className="m-0 mt-1 text-xs text-danger" role="alert">
            {kbErrorText(err)}
          </p>
        )}
      </div>
      <div className="flex shrink-0 items-start gap-1.5">
        <button type="button" className={`badge cursor-pointer border-none ${faq.enabled ? "badge-success" : "badge-neutral"}`} title="Click to turn on/off" disabled={toggle.isPending} onClick={() => toggle.mutate()}>
          {faq.enabled ? "On" : "Off"}
        </button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditing(true)}>
          Edit
        </button>
        <button
          type="button"
          className="btn btn-ghost btn-sm text-danger"
          disabled={remove.isPending}
          onClick={() => {
            if (window.confirm(`Delete the FAQ "${faq.question}"?`)) remove.mutate();
          }}
        >
          Delete
        </button>
      </div>
    </div>
  );
}

// FAQs (SPEC-FE-015 card; SPEC-FE-033 `full` list). The compact card on the
// Brand Voice tab is unchanged. `full` adds search, answers, an On/Off toggle
// (a disabled FAQ isn't used by the AI), inline edit and delete.
export default function FaqList({ full = false }: { full?: boolean }) {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: kbKeys.faqs, queryFn: fetchFaqs });
  const [adding, setAdding] = useState(false);
  const [search, setSearch] = useState("");

  const add = useMutation({
    mutationFn: (v: { question: string; answer: string; channels: string[] }) => createFaq(v),
    onSuccess: (item) => {
      // Append the created FAQ (the backend lists in creation order).
      queryClient.setQueryData<FAQList>(kbKeys.faqs, (old) => (old ? { count: old.count + 1, items: [...old.items, item] } : old));
      setAdding(false);
    },
    // On failure the typed question/answer stay; the message shows below.
  });

  const needle = search.trim().toLowerCase();
  const items = (query.data?.items ?? []).filter(
    (f) => !needle || f.question.toLowerCase().includes(needle) || f.answer.toLowerCase().includes(needle),
  );

  return (
    <div className="card">
      <div className="flex items-center justify-between gap-3">
        <h3 className="m-0">FAQs{query.data ? ` (${query.data.count})` : ""}</h3>
        {full && (
          <input
            type="search"
            aria-label="Search FAQs"
            placeholder="Search questions and answers"
            className="w-64 rounded-md border border-border bg-panel px-3 py-2 text-[13.5px] text-text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        )}
      </div>
      {full && <p className="m-0 mt-2 text-xs text-muted">Enabled FAQs are used by the AI when drafting customer replies.</p>}
      <div className="mt-3">
        {query.isPending ? (
          <p className="text-[13px] text-muted">Loading FAQs…</p>
        ) : query.isError ? (
          <p className="text-[13px] text-danger" role="alert">
            Failed to load FAQs: {query.error.message}
          </p>
        ) : query.data.items.length === 0 ? (
          <p className="text-[13px] text-muted">No FAQs yet{full ? " — add the questions customers ask most." : ""}</p>
        ) : items.length === 0 ? (
          <p className="text-[13px] text-muted">No FAQs match “{search}”.</p>
        ) : (
          <div className="kb-list">
            {items.map((f) =>
              full ? (
                <FaqRow key={f.id} faq={f} />
              ) : (
                <div key={f.id} className="kb-item">
                  <div className="kb-item-icon">?</div>
                  <div>
                    <b>{f.question}</b>
                    <br />
                    <span className="text-xs text-muted">Applied to: {appliedTo(f.channels)}</span>
                  </div>
                </div>
              ),
            )}
          </div>
        )}
      </div>

      {adding ? (
        <FaqForm
          initial={{ question: "", answer: "", channels: [] }}
          submitLabel="Add FAQ"
          busy={add.isPending}
          error={add.error}
          onSubmit={(v) => add.mutate(v)}
          onCancel={() => {
            setAdding(false);
            add.reset();
          }}
        />
      ) : (
        <button type="button" className="btn btn-secondary mt-3" onClick={() => setAdding(true)}>
          + Add FAQ
        </button>
      )}
    </div>
  );
}
