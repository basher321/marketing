"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { kbErrorText } from "@/components/kb/faq-list";
import { createPolicy, deletePolicy, fetchPolicies, kbKeys, updatePolicy } from "@/lib/api/kb";
import type { Policy, PolicyInput, PolicyType } from "@/lib/types/kb";

export const POLICY_TYPES: { value: PolicyType; label: string }[] = [
  { value: "returns", label: "Returns" },
  { value: "refunds", label: "Refunds" },
  { value: "exchanges", label: "Exchanges" },
  { value: "warranty", label: "Warranty" },
  { value: "shipping", label: "Shipping & delivery" },
  { value: "payment", label: "Payment" },
  { value: "privacy", label: "Privacy" },
  { value: "terms", label: "Terms" },
  { value: "other", label: "Other" },
];
const TYPE_LABEL = Object.fromEntries(POLICY_TYPES.map((t) => [t.value, t.label]));

// ISO (UTC) <-> <input type="date"> (viewer's local calendar date).
function toDateInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function fromDateInput(v: string): string | null {
  return v ? new Date(`${v}T00:00:00`).toISOString() : null;
}
function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function PolicyForm({
  initial,
  fixedType,
  busy,
  error,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial: PolicyInput;
  fixedType?: PolicyType;
  busy: boolean;
  error: Error | null;
  submitLabel: string;
  onSubmit: (v: PolicyInput) => void;
  onCancel: () => void;
}) {
  const [v, setV] = useState({ ...initial, from: toDateInput(initial.effective_from), until: toDateInput(initial.effective_until) });
  const set = <K extends keyof typeof v>(k: K, value: (typeof v)[K]) => setV((cur) => ({ ...cur, [k]: value }));
  return (
    <form
      className="rounded-md border border-border p-4"
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        onSubmit({
          policy_type: fixedType ?? v.policy_type,
          title: v.title,
          body: v.body,
          enabled: v.enabled,
          effective_from: fromDateInput(v.from),
          effective_until: fromDateInput(v.until),
        });
      }}
    >
      <div className="form-grid-2">
        {!fixedType && (
          <div className="form-row">
            <label htmlFor="pol_type">Type</label>
            <select id="pol_type" value={v.policy_type} onChange={(e) => set("policy_type", e.target.value as PolicyType)}>
              {POLICY_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="form-row">
          <label htmlFor="pol_title">Title</label>
          <input id="pol_title" required maxLength={255} value={v.title} onChange={(e) => set("title", e.target.value)} />
        </div>
      </div>
      <div className="form-row">
        <label htmlFor="pol_body">Policy text</label>
        <textarea id="pol_body" required rows={5} maxLength={20000} value={v.body} onChange={(e) => set("body", e.target.value)} />
      </div>
      <div className="form-grid-2">
        <div className="form-row">
          <label htmlFor="pol_from">Effective from (optional)</label>
          <input id="pol_from" type="date" value={v.from} onChange={(e) => set("from", e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor="pol_until">Effective until (optional)</label>
          <input id="pol_until" type="date" value={v.until} onChange={(e) => set("until", e.target.value)} />
        </div>
      </div>
      <label className="mb-3 flex items-center gap-2 text-[13px]">
        <input type="checkbox" checked={v.enabled} onChange={(e) => set("enabled", e.target.checked)} />
        Enabled (the AI may use this policy)
      </label>
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

function PolicyCard({ policy, fixedType }: { policy: Policy; fixedType?: PolicyType }) {
  const queryClient = useQueryClient();
  const refresh = () => void queryClient.invalidateQueries({ queryKey: kbKeys.policies });
  const [editing, setEditing] = useState(false);
  const save = useMutation({
    mutationFn: (v: PolicyInput) => updatePolicy(policy.id, v),
    onSuccess: () => {
      refresh();
      setEditing(false);
    },
  });
  const toggle = useMutation({ mutationFn: () => updatePolicy(policy.id, { enabled: !policy.enabled }), onSuccess: refresh });
  const remove = useMutation({ mutationFn: () => deletePolicy(policy.id), onSuccess: refresh });
  const err = toggle.error ?? remove.error;
  if (editing) {
    return <PolicyForm initial={policy} fixedType={fixedType} busy={save.isPending} error={save.error} submitLabel="Save" onSubmit={(v) => save.mutate(v)} onCancel={() => setEditing(false)} />;
  }
  const dates =
    policy.effective_from || policy.effective_until
      ? `${policy.effective_from ? `From ${shortDate(policy.effective_from)}` : ""}${policy.effective_from && policy.effective_until ? " · " : ""}${policy.effective_until ? `Until ${shortDate(policy.effective_until)}` : ""}`
      : "Always in effect";
  return (
    <div className={`rounded-md border border-border p-4 ${policy.enabled ? "" : "opacity-60"}`} data-policy={policy.id}>
      <div className="mb-1 flex items-start justify-between gap-3">
        <div>
          <b>{policy.title}</b>
          <div className="text-xs text-muted">
            {TYPE_LABEL[policy.policy_type] ?? policy.policy_type} · {dates}
          </div>
        </div>
        <span className={`badge ${policy.enabled ? "badge-success" : "badge-neutral"}`}>{policy.enabled ? "Enabled" : "Disabled"}</span>
      </div>
      <p className="m-0 mb-3 line-clamp-3 whitespace-pre-line text-[13px]">{policy.body}</p>
      <div className="flex gap-1.5">
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditing(true)}>
          Edit
        </button>
        <button type="button" className="btn btn-secondary btn-sm" disabled={toggle.isPending} onClick={() => toggle.mutate()}>
          {policy.enabled ? "Disable" : "Enable"}
        </button>
        <button
          type="button"
          className="btn btn-ghost btn-sm text-danger"
          disabled={remove.isPending}
          onClick={() => {
            if (window.confirm(`Delete the policy "${policy.title}"?`)) remove.mutate();
          }}
        >
          Delete
        </button>
      </div>
      {err && (
        <p className="mb-0 mt-2 text-xs text-danger" role="alert">
          {kbErrorText(err)}
        </p>
      )}
    </div>
  );
}

// Policies (SPEC-FE-033 / SPEC-BE-048), grouped by type. `only` limits the
// list (and the new-policy form) to one type — the Shipping tab uses it for
// the delivery policy text.
export default function Policies({ only }: { only?: PolicyType }) {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: kbKeys.policies, queryFn: fetchPolicies });
  const [adding, setAdding] = useState(false);
  const create = useMutation({
    mutationFn: (v: PolicyInput) => createPolicy(v),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: kbKeys.policies });
      setAdding(false);
    },
  });
  const items = (query.data?.items ?? []).filter((p) => !only || p.policy_type === only);
  const groups = POLICY_TYPES.filter((t) => !only || t.value === only)
    .map((t) => ({ ...t, items: items.filter((p) => p.policy_type === t.value) }))
    .filter((g) => g.items.length > 0);

  return (
    <div className="card">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="m-0">{only === "shipping" ? "Delivery policy" : "Policies"}</h3>
        {!adding && (
          <button type="button" className="btn btn-sm" onClick={() => setAdding(true)}>
            {only === "shipping" ? "+ Add delivery policy" : "+ New policy"}
          </button>
        )}
      </div>
      <p className="m-0 mb-3 text-xs text-muted">Enabled policies are used by the AI when drafting replies.</p>
      {adding && (
        <div className="mb-4">
          <PolicyForm
            initial={{ policy_type: only ?? "returns", title: "", body: "", enabled: true, effective_from: null, effective_until: null }}
            fixedType={only}
            busy={create.isPending}
            error={create.error}
            submitLabel="Create policy"
            onSubmit={(v) => create.mutate(v)}
            onCancel={() => {
              setAdding(false);
              create.reset();
            }}
          />
        </div>
      )}
      {query.isPending ? (
        <p className="text-[13px] text-muted">Loading policies…</p>
      ) : query.isError ? (
        <p className="text-[13px] text-danger" role="alert">
          Failed to load policies: {query.error.message}
        </p>
      ) : items.length === 0 ? (
        <p className="text-[13px] text-muted">
          {only === "shipping"
            ? "No delivery policy yet — describe delivery times, areas and charges so the AI can answer shipping questions."
            : "No policies yet — add your return, refund and payment rules so the AI can answer customers correctly."}
        </p>
      ) : (
        groups.map((g) => (
          <div key={g.value} className="mb-4">
            {!only && <h4 className="mb-2 mt-0 text-[13px] text-muted">{g.label}</h4>}
            <div className="grid gap-3 md:grid-cols-2">
              {g.items.map((p) => (
                <PolicyCard key={p.id} policy={p} fixedType={only} />
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
