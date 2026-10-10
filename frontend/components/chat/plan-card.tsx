"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { approveApproval, approveGroup, rejectApproval } from "@/lib/api/approvals";
import { editPlanAction, fetchPlan, orchestratorKeys, retryPlanAction } from "@/lib/api/orchestrator";
import type { ActionStatus, ChatMessage, Module, PlanAction, PlanRead } from "@/lib/types/orchestrator";

import { useRecordDecisions, type Decision } from "./decisions";
import WorkflowPreview from "./workflow-preview";

const MODULE_LABEL: Record<Module, string> = {
  ecommerce: "E-Commerce",
  shipping: "Shipping",
  // SPEC-BE-078: campaign actions are Paid Marketing; posts are Organic.
  marketing: "Paid Marketing",
  meta: "Paid Marketing · Meta",
  organic: "Organic Marketing",
  workflows: "Workflows",
  general: "General",
};

// Live statuses that keep the card polling (SPEC-FE-041).
const ACTIVE: ActionStatus[] = ["approved", "running"];
const FINISHED: ActionStatus[] = ["succeeded", "failed", "skipped", "rejected"];

// Timeline look (SPEC-FE-061 FR4): one icon and token color per module.
const MODULE_ICON: Record<Module, string> = {
  ecommerce: "🛒",
  shipping: "🚚",
  marketing: "📣",
  meta: "📣",
  organic: "🌱",
  workflows: "⚙️",
  general: "✦",
};
const MODULE_COLOR: Record<Module, string> = {
  ecommerce: "var(--chart-1)",
  shipping: "var(--chart-2)",
  marketing: "var(--chart-4)",
  meta: "var(--chart-4)",
  organic: "var(--chart-3)",
  workflows: "var(--accent)",
  general: "var(--muted)",
};
const PLAN_TONE: Record<string, string> = {
  executed: "badge-success",
  failed: "badge-danger",
  rejected: "badge-danger",
  pending_approval: "badge-warn",
};

function riskBadge(a: PlanAction): { label: string; className: string } {
  if (a.risk === "read") return { label: "Read", className: "badge badge-neutral" };
  if (a.risk === "draft") return { label: "Draft", className: "badge badge-neutral" };
  if (a.approval_mode === "auto") return { label: "Your approval", className: "badge badge-neutral" };
  if (a.approval_mode === "owner") return { label: "Owner approval", className: "badge badge-warn" };
  return { label: "Needs approval", className: "badge badge-warn" };
}

function statusBadge(status: ActionStatus): { label: string; className: string } {
  switch (status) {
    case "pending_approval":
      return { label: "Pending approval", className: "badge badge-warn" };
    case "approved":
      return { label: "Queued", className: "badge badge-neutral" };
    case "running":
      return { label: "Running…", className: "badge badge-neutral" };
    case "succeeded":
      return { label: "Succeeded", className: "badge badge-success" };
    case "failed":
      return { label: "Failed", className: "badge badge-danger" };
    case "skipped":
      return { label: "Skipped", className: "badge badge-neutral" };
    case "rejected":
      return { label: "Rejected", className: "badge badge-danger" };
  }
}

function paramText(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (Array.isArray(value)) return value.map((v) => (typeof v === "object" ? JSON.stringify(v) : String(v))).join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** Internal links (the app's own pages) use next/link; Ads Manager opens in a new tab. */
function ResultLink({ href }: { href: string }) {
  if (href.startsWith("/")) {
    return (
      <Link href={href} target="_blank" rel="noopener" className="text-accent underline">
        Open
      </Link>
    );
  }
  return (
    <a href={href} target="_blank" rel="noreferrer" className="text-accent underline">
      Open in Ads Manager
    </a>
  );
}

// Edit-before-approval form, built from the step's own params (the backend
// re-validates against the same strict model; errors show inline).
function EditForm({ plan, action, onDone }: { plan: PlanRead; action: PlanAction; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      Object.entries(action.params).map(([k, v]) => [k, typeof v === "object" && v !== null ? JSON.stringify(v) : String(v)]),
    ),
  );
  const save = useMutation({
    mutationFn: () => {
      const params: Record<string, unknown> = {};
      for (const [key, raw] of Object.entries(values)) {
        const original = action.params[key];
        if (typeof original === "number") params[key] = Number(raw);
        else if (typeof original === "boolean") params[key] = raw === "true";
        else if (typeof original === "object" && original !== null) params[key] = JSON.parse(raw);
        else params[key] = raw;
      }
      return editPlanAction(plan.id, action.index, params);
    },
    onSuccess: (next) => {
      queryClient.setQueryData(orchestratorKeys.plan(plan.id), next);
      onDone();
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };
  return (
    <form onSubmit={submit} className="mt-2 grid gap-2 rounded-xl border border-border bg-bg p-2.5">
      {Object.keys(values).map((key) => (
        <label key={key} className="grid gap-1 text-xs">
          <span className="text-muted">{key.replace(/_/g, " ")}</span>
          <input
            className="rounded border border-border bg-panel px-2 py-1 text-[13px]"
            value={values[key]}
            onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.value }))}
          />
        </label>
      ))}
      {save.isError && (
        <p className="m-0 text-xs text-danger" role="alert">
          {save.error instanceof SyntaxError ? "One of the fields isn't valid JSON." : save.error.message}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <button type="button" className="btn btn-secondary btn-sm" onClick={onDone}>
          Cancel
        </button>
        <button type="submit" className="btn btn-sm" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save step"}
        </button>
      </div>
    </form>
  );
}

// Command Chat plan card (SPEC-FE-041 behavior, SPEC-FE-061 timeline look): steps
// grouped by module with risk + live status, dependency hints, results/errors,
// per-step Approve/Reject/Edit/Retry and "Approve all I can" (the backend
// leaves steps this user may not approve pending).
export default function PlanCard({ planId, initial }: { planId: string; initial?: PlanRead }) {
  const queryClient = useQueryClient();
  const record = useRecordDecisions();
  const [editing, setEditing] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const query = useQuery({
    queryKey: orchestratorKeys.plan(planId),
    queryFn: () => fetchPlan(planId),
    initialData: initial,
    refetchInterval: (q) => {
      const data = q.state.data;
      return data && data.actions.some((a) => ACTIVE.includes(a.status)) ? 2000 : false;
    },
  });
  // When a running plan finishes, its result summary is a new chat message:
  // fetch the chat until it arrives (it was only seen after a reload before),
  // so the results card shows and, after a voice command, is spoken.
  // A plan sent in this session (initial) or seen running; a read step can finish
  // before the send request even returns, so it may never be seen running.
  const sawActive = useRef(!!initial);
  const actions = query.data?.actions;
  const running = !!actions?.some((a) => ACTIVE.includes(a.status));
  const settled = !!actions && !running && !actions.some((a) => a.status === "pending_approval");
  if (running) sawActive.current = true;
  useEffect(() => {
    if (!settled || !sawActive.current) return;
    let tries = 0;
    let timer: ReturnType<typeof setTimeout>;
    const hasSummary = () =>
      (queryClient.getQueryData<ChatMessage[]>(orchestratorKeys.messages) ?? []).some((m) => m.kind === "summary" && m.plan_id === planId);
    const tick = () => {
      if (hasSummary() || tries++ >= 8) return;
      void queryClient.invalidateQueries({ queryKey: orchestratorKeys.messages });
      timer = setTimeout(tick, 1500);
    };
    timer = setTimeout(tick, 300);
    return () => clearTimeout(timer);
  }, [settled, planId, queryClient]);
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: orchestratorKeys.plan(planId) });
    // The result summary arrives as a new chat message.
    void queryClient.invalidateQueries({ queryKey: orchestratorKeys.messages });
  };
  const onError = (err: unknown) => setError(err instanceof Error ? err.message : String(err));
  const decide = useMutation({
    mutationFn: ({ id, d }: { id: string; d: "approved" | "rejected" }) =>
      d === "approved" ? approveApproval(id) : rejectApproval(id),
    onMutate: () => setError(null),
    onSuccess: (res) => {
      record({ [res.id]: res.decision as Decision });
      refresh();
    },
    onError,
  });
  const approveAll = useMutation({
    mutationFn: () => approveGroup(planId),
    onMutate: () => setError(null),
    onSuccess: (res) => {
      record(Object.fromEntries(res.decided_ids.map((id) => [id, res.decision as Decision])));
      if (res.decided_count === 0) setError("Nothing left that you can approve: the remaining steps need the owner.");
      refresh();
    },
    onError,
  });
  const retry = useMutation({
    mutationFn: (index: number) => retryPlanAction(planId, index),
    onMutate: () => setError(null),
    onSuccess: (next) => {
      queryClient.setQueryData(orchestratorKeys.plan(planId), next);
      refresh();
    },
    onError,
  });

  if (query.isPending) return <div className="cc-card cc-shimmer h-24 text-[13px] text-muted">Loading plan…</div>;
  if (query.isError) {
    return (
      <div className="cc-card text-[13px] text-danger" role="alert">
        Couldn&apos;t load the plan: {query.error.message}
      </div>
    );
  }
  const plan = query.data;
  if (plan.legacy) {
    return (
      <div className="cc-card text-[13px] text-muted">
        This plan was created before live execution; decide its steps in Pending Approvals.
      </div>
    );
  }
  const busy = decide.isPending || approveAll.isPending || retry.isPending;
  const pending = plan.actions.filter((a) => a.status === "pending_approval");
  const done = plan.actions.filter((a) => FINISHED.includes(a.status)).length;
  const live = plan.actions.some((a) => ACTIVE.includes(a.status));

  return (
    <div className="cc-card cc-plan">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="cc-card-head mb-0">
          <span className="cc-card-icon" aria-hidden="true">
            🧭
          </span>
          Plan · {plan.actions.length} step{plan.actions.length === 1 ? "" : "s"}
        </div>
        <span className={`badge ${PLAN_TONE[plan.status] ?? "badge-neutral"}`}>{plan.status.replace(/_/g, " ")}</span>
      </div>
      <div className="mt-1 flex items-center gap-2 text-[11px] text-muted">
        <div className="cc-progress my-0 flex-1" aria-hidden="true">
          <span style={{ width: `${plan.actions.length ? (done / plan.actions.length) * 100 : 0}%` }} />
        </div>
        {done}/{plan.actions.length} done{live ? " · working…" : ""}
      </div>
      <div className="cc-steps mt-3">
        {plan.actions.map((a) => {
          const risk = riskBadge(a);
          const status = statusBadge(a.status);
          const steps = a.type === "create_workflow" || a.type === "update_workflow";
          const params = Object.entries(a.params).filter(([k]) => !(steps && k === "actions"));
          return (
            <div key={a.index} className="cc-step" data-state={a.status}>
              <span className="cc-step-icon" style={{ color: MODULE_COLOR[a.module] }} aria-hidden="true">
                {a.status === "succeeded" ? "✓" : a.status === "failed" ? "✕" : MODULE_ICON[a.module]}
              </span>
              <div className={`min-w-0 ${a.status === "running" ? "cc-shimmer" : ""}`}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0 text-[13px]">
                    <div className="text-[11px] font-semibold uppercase tracking-wide" style={{ color: MODULE_COLOR[a.module] }}>
                      {a.index}. {MODULE_LABEL[a.module]}
                    </div>
                    <div className="font-medium">
                      {a.description}
                      {a.depends_on.length > 0 && <span className="text-xs font-normal text-muted"> (after #{a.depends_on.join(", #")})</span>}
                    </div>
                  </div>
                  <span className="flex shrink-0 flex-wrap items-center gap-1.5">
                    <span className={risk.className}>{risk.label}</span>
                    <span className={status.className}>{status.label}</span>
                  </span>
                </div>
                {params.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {params.map(([k, v]) => (
                      <span key={k} className="cc-kv" title={`${k.replace(/_/g, " ")}: ${paramText(v)}`}>
                        <b>{k.replace(/_/g, " ")}</b> {paramText(v)}
                      </span>
                    ))}
                  </div>
                )}
                {steps && <WorkflowPreview params={a.params} />}
                {a.status === "succeeded" && a.result?.summary && (
                  <div className="mt-1.5 text-xs text-success">
                    ✓ {a.result.summary} {typeof a.result.link === "string" && <ResultLink href={a.result.link} />}
                  </div>
                )}
                {(a.status === "failed" || a.status === "skipped") && a.error && <div className="mt-1.5 text-xs text-danger">{a.error}</div>}
                {(a.status === "pending_approval" && a.approval_id) || a.status === "failed" ? (
                  <div className="mt-2 flex flex-wrap justify-end gap-1.5">
                    {a.status === "pending_approval" && a.approval_id && (
                      <>
                        <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => setEditing(editing === a.index ? null : a.index)}>
                          Edit
                        </button>
                        <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => decide.mutate({ id: a.approval_id as string, d: "rejected" })}>
                          Reject
                        </button>
                        <button type="button" className="btn btn-sm" disabled={busy} onClick={() => decide.mutate({ id: a.approval_id as string, d: "approved" })}>
                          {a.approval_mode === "owner" ? "Approve (owner)" : "Approve"}
                        </button>
                      </>
                    )}
                    {a.status === "failed" && (
                      <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => retry.mutate(a.index)}>
                        Retry
                      </button>
                    )}
                  </div>
                ) : null}
                {editing === a.index && <EditForm plan={plan} action={a} onDone={() => setEditing(null)} />}
              </div>
            </div>
          );
        })}
      </div>
      {pending.length > 1 && (
        <div className="plan-buttons">
          <button type="button" className="btn btn-sm" disabled={busy} onClick={() => approveAll.mutate()}>
            Approve all I can
          </button>
        </div>
      )}
      {error && (
        <p className="mb-0 mt-2 text-xs text-danger" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
