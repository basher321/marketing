"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { approveGroup } from "@/lib/api/approvals";
import { fetchMediaItem, mediaKeys } from "@/lib/api/media";
import {
  addJob,
  controlJobList,
  editItem,
  editPlanAction,
  fetchPlan,
  orchestratorKeys,
  removeJob,
  retryPlanAction,
  setJobSchedule,
  skipPlanAction,
  submitJobList,
} from "@/lib/api/orchestrator";
import { fetchTenant, tenantKeys } from "@/lib/api/tenant";
import type { ActionStatus, FixHint, Module, PlanAction, PlanItem, PlanRead } from "@/lib/types/orchestrator";

import { AddJobForm, fmtTime, ItemForm, JobForm, SchedulePanel, SubmitSheet } from "./job-editor";

// Job board (SPEC-FE-065, backend SPEC-BE-097): a job list from files or a big
// command. A draft is reviewed and edited here, then submitted; after that it
// shows live progress with pause/resume/cancel/retry. Nothing is computed that
// the backend doesn't send: statuses, times and results are its own.

const MODULE_ICON: Record<Module, string> = {
  ecommerce: "🛒", shipping: "🚚", marketing: "📣", meta: "📣", organic: "🌱", workflows: "⚙️", general: "✦",
};
const MODULE_NAME: Record<Module, string> = {
  ecommerce: "E-Commerce", shipping: "Shipping", marketing: "Paid", meta: "Paid · Meta", organic: "Organic", workflows: "Workflows", general: "General",
};
const STATUS: Record<ActionStatus, { label: string; tone: string }> = {
  draft: { label: "Draft", tone: "badge-neutral" },
  needs_input: { label: "Needs input", tone: "badge-warn" },
  pending_approval: { label: "Waiting for approval", tone: "badge-warn" },
  approved: { label: "Queued", tone: "badge-neutral" },
  running: { label: "Running…", tone: "badge-neutral" },
  succeeded: { label: "Done", tone: "badge-success" },
  failed: { label: "Failed", tone: "badge-danger" },
  skipped: { label: "Skipped", tone: "badge-neutral" },
  rejected: { label: "Rejected", tone: "badge-danger" },
};
const LIVE: ActionStatus[] = ["approved", "running"];
const PAGE = 25; // item groups rendered at a time (windowing for big lists)

function paramSummary(params: Record<string, unknown>): string {
  return Object.entries(params)
    .filter(([, v]) => v !== null && v !== "" && !(Array.isArray(v) && v.length === 0))
    .slice(0, 4)
    .map(([k, v]) => `${k.replace(/_/g, " ")}: ${Array.isArray(v) ? v.join(", ") : typeof v === "object" ? "…" : String(v)}`)
    .join(" · ");
}

function errText(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/** How to fix a failed step (SPEC-BE-100 / SPEC-FE-067): the backend's text and page. */
export function FixLine({ fix }: { fix: FixHint | null | undefined }) {
  if (!fix) return null;
  return (
    <div className="text-[11.5px]" data-testid="fix-line">
      <b className="font-medium">How to fix:</b> {fix.text}
      {fix.href && fix.link_label && (
        <>
          {" "}
          <Link href={fix.href} target="_blank" className="text-accent underline">{fix.link_label}</Link>
        </>
      )}
    </div>
  );
}

/** SPEC-BE-102 / SPEC-FE-068: steps that can be skipped, and how many not-finished steps depend on one. */
export function skippable(a: PlanAction): boolean {
  return a.status === "pending_approval" || a.status === "needs_input" || a.status === "failed" || (a.status === "approved" && !a.started_at);
}

export function confirmSkip(a: PlanAction, actions: PlanAction[]): boolean {
  const open = new Set(["approved", "pending_approval", "needs_input", "draft"]);
  const gone = new Set<number>();
  const visit = (index: number) => {
    for (const x of actions) if (x.depends_on.includes(index) && open.has(x.status) && !gone.has(x.index)) { gone.add(x.index); visit(x.index); }
  };
  visit(a.index);
  return window.confirm(`Skip #${a.index} ${a.label}?${gone.size ? ` ${gone.size} job(s) that need it are skipped too.` : ""} The rest keeps running.`);
}

/** A failed AI/read step, or a queued one in a submitted list, can still be edited (SPEC-BE-100 FR5). */
export function fixable(a: PlanAction, jobList: boolean): boolean {
  if (a.risk !== "read" && a.risk !== "draft") return false;
  return a.status === "failed" || (jobList && a.status === "approved" && !a.started_at);
}

function ItemThumb({ mediaId }: { mediaId: string }) {
  const q = useQuery({ queryKey: mediaKeys.item(mediaId), queryFn: () => fetchMediaItem(mediaId), staleTime: 30 * 60_000 });
  return q.data ? <img src={q.data.url} alt="" className="cc-item-thumb" /> : <span className="cc-item-thumb cc-shimmer" />;
}

type Panel =
  | { kind: "job"; index: number }
  | { kind: "item"; key: string }
  | { kind: "add" }
  | { kind: "schedule" }
  | { kind: "submit" }
  | null;

export default function JobBoard({ initial }: { initial: PlanRead }) {
  const queryClient = useQueryClient();
  const tenant = useQuery({ queryKey: tenantKeys.me, queryFn: fetchTenant, staleTime: 5 * 60_000 });
  const tz = tenant.data?.timezone;
  const query = useQuery({
    queryKey: orchestratorKeys.plan(initial.id),
    queryFn: () => fetchPlan(initial.id),
    initialData: initial,
    refetchInterval: (q) => {
      const d = q.state.data;
      if (!d || d.status === "draft" || d.status === "cancelled") return false;
      if (d.actions.some((a) => a.status === "running")) return 2000;
      return d.actions.some((a) => LIVE.includes(a.status) || a.status === "pending_approval") ? 15_000 : false;
    },
  });
  const plan = query.data ?? initial;
  const draft = plan.status === "draft";
  const [panel, setPanel] = useState<Panel>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "needs" | "failed">("all");
  const [moduleFilter, setModuleFilter] = useState<string>("");
  const [search, setSearch] = useState("");
  // The first 8 groups start open; after that the user decides (adding a group never collapses others).
  const [open, setOpen] = useState<Set<string>>(() => new Set(["__once", ...(initial.items ?? []).slice(0, 8).map((it) => it.key)]));
  const [shown, setShown] = useState(PAGE);
  const [flash, setFlash] = useState<Set<number>>(new Set());

  const apply = (next: PlanRead, changed: number[] = []) => {
    queryClient.setQueryData(orchestratorKeys.plan(plan.id), next);
    if (changed.length) {
      setFlash(new Set(changed));
      setTimeout(() => setFlash(new Set()), 1600);
    }
    setError(null);
  };
  const onError = (err: unknown) => setError(errText(err));
  const messages = () => void queryClient.invalidateQueries({ queryKey: orchestratorKeys.messages });

  const edit = useMutation({
    mutationFn: (v: { index: number; params: Record<string, unknown>; runAt: string | null }) => editPlanAction(plan.id, v.index, v.params, v.runAt),
    onSuccess: (next, v) => { apply(next, [v.index]); setPanel(null); },
    onError,
  });
  const remove = useMutation({
    mutationFn: (index: number) => removeJob(plan.id, index),
    onSuccess: (next) => apply(next),
    onError,
  });
  const add = useMutation({
    mutationFn: (job: Parameters<typeof addJob>[1]) => addJob(plan.id, job),
    onSuccess: (next) => { apply(next, [Math.max(...next.actions.map((a) => a.index))]); setPanel(null); },
    onError,
  });
  const item = useMutation({
    mutationFn: (v: { key: string; fields: Record<string, unknown> }) => editItem(plan.id, v.key, v.fields),
    onSuccess: (next, v) => { apply(next, next.actions.filter((a) => a.item_key === v.key).map((a) => a.index)); setPanel(null); },
    onError,
  });
  const schedule = useMutation({
    mutationFn: (s: Parameters<typeof setJobSchedule>[1]) => setJobSchedule(plan.id, s),
    onSuccess: (next) => { apply(next); setPanel(null); },
    onError,
  });
  const submit = useMutation({
    mutationFn: () => submitJobList(plan.id),
    onSuccess: (next) => { apply(next); setPanel(null); messages(); void queryClient.invalidateQueries({ queryKey: ["approvals"] }); },
    onError: (err) => {
      onError(err);
      if (/need input/.test(errText(err))) {
        setPanel(null);
        setFilter("needs");
      }
    },
  });
  const control = useMutation({
    mutationFn: (op: "pause" | "resume" | "cancel" | "retry-failed") => controlJobList(plan.id, op),
    onSuccess: (next) => { apply(next); messages(); },
    onError,
  });
  const retry = useMutation({
    mutationFn: (index: number) => retryPlanAction(plan.id, index),
    onSuccess: (next) => apply(next),
    onError,
  });
  // SPEC-FE-067: a failed job is saved and run again in one go.
  const fixRetry = useMutation({
    mutationFn: async (v: { index: number; params: Record<string, unknown>; runAt: string | null }) => {
      await editPlanAction(plan.id, v.index, v.params, v.runAt);
      return retryPlanAction(plan.id, v.index);
    },
    onSuccess: (next, v) => { apply(next, [v.index]); setPanel(null); messages(); },
    onError,
  });
  const approveAll = useMutation({
    mutationFn: () => approveGroup(plan.id),
    onSuccess: () => { void query.refetch(); messages(); },
    onError,
  });
  const skip = useMutation({
    mutationFn: (index: number) => skipPlanAction(plan.id, index),
    onSuccess: (next, index) => { apply(next, [index]); messages(); },
    onError,
  });
  const busy = [edit, remove, add, item, schedule, submit, control, retry, fixRetry, approveAll, skip].some((m) => m.isPending);

  const counts = useMemo(() => {
    const c: Partial<Record<ActionStatus, number>> = {};
    for (const a of plan.actions) c[a.status] = (c[a.status] ?? 0) + 1;
    return c;
  }, [plan.actions]);
  const now = Date.now();
  const scheduled = plan.actions.filter((a) => a.status === "approved" && a.run_at && new Date(a.run_at).getTime() > now).length;
  const finished = (counts.succeeded ?? 0) + (counts.failed ?? 0) + (counts.skipped ?? 0) + (counts.rejected ?? 0);
  const total = plan.actions.length;

  const items = plan.items ?? [];
  const byItem = useMemo(() => {
    const groups = new Map<string, PlanAction[]>();
    const q = search.trim().toLowerCase();
    const label = new Map(items.map((it) => [it.key, it.label.toLowerCase()]));
    for (const a of plan.actions) {
      if (filter === "needs" && a.status !== "needs_input") continue;
      if (filter === "failed" && a.status !== "failed") continue;
      if (moduleFilter && a.module !== moduleFilter) continue;
      const key = a.item_key ?? "__once";
      if (q && !(label.get(key) ?? "").includes(q) && !a.label.toLowerCase().includes(q) && !a.description.toLowerCase().includes(q)) continue;
      groups.set(key, [...(groups.get(key) ?? []), a]);
    }
    return groups;
  }, [plan.actions, items, filter, moduleFilter, search]);
  const groupKeys = [...(byItem.has("__once") ? ["__once"] : []), ...items.map((it) => it.key).filter((k) => byItem.has(k))];
  const modules = Array.from(new Set(plan.actions.map((a) => a.module)));
  const itemOf = (k: string) => items.find((it) => it.key === k);

  const row = (a: PlanAction) => {
    const st = STATUS[a.status] ?? STATUS.draft;
    const link = typeof a.result?.link === "string" ? a.result.link : null;
    return (
      <div key={a.index} className={`cc-job ${a.status === "needs_input" ? "is-need" : ""} ${flash.has(a.index) ? "is-flash" : ""}`} data-testid="job-row" data-status={a.status}>
        <span className="cc-job-icon" aria-hidden="true">{a.status === "succeeded" ? "✓" : a.status === "failed" ? "✕" : MODULE_ICON[a.module]}</span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5 text-[12.5px]">
            <b className="font-medium">#{a.index} {a.label}</b>
            <span className={`badge ${st.tone}`}>{st.label}</span>
            {a.approval_mode !== "auto" && (draft || a.status === "pending_approval") && (
              <span className="badge badge-neutral">{a.approval_mode === "owner" ? "Owner approval" : "Manager approval"}</span>
            )}
            {a.run_at && <span className="text-[11px] text-muted">⏰ {fmtTime(a.run_at, tz)}</span>}
          </div>
          <div className="truncate text-[11.5px] text-muted" title={paramSummary(a.params)}>{a.description !== a.label ? `${a.description} · ` : ""}{paramSummary(a.params)}</div>
          {a.status === "needs_input" && a.missing?.length ? (
            <div className="text-[11.5px] text-warn">Needs: {a.missing.map((m) => m.question).join(" ")}</div>
          ) : null}
          {a.status === "succeeded" && typeof a.result?.summary === "string" && (
            <div className="text-[11.5px] text-success">
              {a.result.summary}{" "}
              {link && (link.startsWith("/") ? <Link href={link} target="_blank" className="text-accent underline">Open</Link> : <a href={link} target="_blank" rel="noreferrer" className="text-accent underline">Open</a>)}
            </div>
          )}
          {(a.status === "failed" || (a.status === "skipped" && a.error)) && <div className="text-[11.5px] text-danger">{a.error}</div>}
          {a.status === "failed" && <FixLine fix={a.fix} />}
          {panel?.kind === "job" && panel.index === a.index && (
            <JobForm job={a} tz={tz} busy={edit.isPending || fixRetry.isPending} error={error} onCancel={() => setPanel(null)}
                     saveLabel={a.status === "failed" ? "Save & retry" : "Save job"}
                     onSave={(params, runAt) => (a.status === "failed" ? fixRetry : edit).mutate({ index: a.index, params, runAt })} />
          )}
        </div>
        <div className="flex shrink-0 flex-wrap justify-end gap-1">
          {draft && (
            <>
              <button type="button" className="cc-link" disabled={busy} onClick={() => setPanel({ kind: "job", index: a.index })}>Edit</button>
              <button type="button" className="cc-link" disabled={busy} title="Duplicate"
                      onClick={() => add.mutate({ type: a.type, params: a.params, description: a.description, item_key: a.item_key ?? null, depends_on: a.depends_on, run_at: a.run_at ?? null })}>
                Duplicate
              </button>
              <button type="button" className="cc-link" disabled={busy} onClick={() => {
                const deps = plan.actions.filter((x) => x.depends_on.includes(a.index)).length;
                if (!deps || window.confirm(`Remove #${a.index}? ${deps} job(s) that depend on it go too.`)) remove.mutate(a.index);
              }}>Remove</button>
            </>
          )}
          {!draft && fixable(a, true) && (
            <button type="button" className="cc-link" disabled={busy} onClick={() => setPanel({ kind: "job", index: a.index })}>Edit</button>
          )}
          {a.status === "failed" && <button type="button" className="cc-link text-accent" disabled={busy} onClick={() => retry.mutate(a.index)}>Retry</button>}
          {!draft && plan.status !== "cancelled" && skippable(a) && (
            <button type="button" className="cc-link" disabled={busy} onClick={() => { if (confirmSkip(a, plan.actions)) skip.mutate(a.index); }}>Skip</button>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="cc-card cc-board" data-testid="job-board">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="cc-card-head mb-0">
          <span className="cc-card-icon" aria-hidden="true">🗂️</span>
          <span className="min-w-0">
            Job list · {total} job{total === 1 ? "" : "s"}
            {items.length > 0 && <span className="font-normal text-muted"> · {items.length} item{items.length === 1 ? "" : "s"}</span>}
          </span>
        </div>
        <span className={`badge ${draft ? "badge-warn" : plan.status === "executed" ? "badge-success" : plan.status === "failed" || plan.status === "cancelled" ? "badge-danger" : "badge-neutral"}`}>
          {draft ? "Draft: review, then submit" : plan.status === "paused" ? "Paused" : plan.status.replace(/_/g, " ")}
        </span>
      </div>
      <div className="mt-1.5 text-[12px] text-muted">{plan.title}</div>
      <div className="mt-2 flex flex-wrap gap-1.5 text-[11.5px]">
        {(["draft", "needs_input", "pending_approval", "running", "succeeded", "failed"] as ActionStatus[]).map((s) =>
          counts[s] ? <span key={s} className={`badge ${STATUS[s].tone}`}>{counts[s]} {STATUS[s].label.toLowerCase()}</span> : null)}
        {scheduled > 0 && <span className="badge badge-neutral">{scheduled} scheduled</span>}
        {(counts.approved ?? 0) - scheduled > 0 && <span className="badge badge-neutral">{(counts.approved ?? 0) - scheduled} queued</span>}
      </div>
      {!draft && (
        <div className="mt-2 flex items-center gap-2 text-[11px] text-muted">
          <div className="cc-progress my-0 flex-1" aria-hidden="true"><span style={{ width: `${total ? (finished / total) * 100 : 0}%` }} /></div>
          {finished}/{total} finished
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <div className="cc-seg" role="group" aria-label="Show">
          {([["all", "All"], ["needs", `Needs input${counts.needs_input ? ` (${counts.needs_input})` : ""}`], ["failed", `Failed${counts.failed ? ` (${counts.failed})` : ""}`]] as const).map(([k, label]) => (
            <button key={k} type="button" aria-pressed={filter === k} onClick={() => setFilter(k)}>{label}</button>
          ))}
        </div>
        {modules.length > 1 && (
          <select className="cc-mini-select" value={moduleFilter} onChange={(e) => setModuleFilter(e.target.value)} aria-label="Module">
            <option value="">All modules</option>
            {modules.map((m) => <option key={m} value={m}>{MODULE_NAME[m]}</option>)}
          </select>
        )}
        {items.length > 3 && (
          <input className="cc-mini-input" placeholder="Search items…" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search items" />
        )}
      </div>

      <div className="mt-2 grid gap-2">
        {groupKeys.length === 0 && <p className="m-0 text-[12.5px] text-muted">No jobs match.</p>}
        {groupKeys.slice(0, shown).map((key) => {
          const it: PlanItem | undefined = itemOf(key);
          const jobs = byItem.get(key) ?? [];
          const isOpen = open.has(key) || filter !== "all" || !!search;
          const done = jobs.filter((a) => a.status === "succeeded").length;
          return (
            <div key={key} className="cc-group" data-testid="job-group">
              <button type="button" className="cc-group-head" aria-expanded={isOpen}
                      onClick={() => setOpen((s) => { const n = new Set(s); if (n.has(key)) n.delete(key); else n.add(key); return n; })}>
                {it?.media_ids[0] ? <ItemThumb mediaId={it.media_ids[0]} /> : <span className="cc-item-thumb cc-item-ph" aria-hidden="true">{key === "__once" ? "✦" : "▢"}</span>}
                <span className="min-w-0 flex-1 text-left">
                  <span className="block truncate text-[13px] font-semibold">{key === "__once" ? "For the whole list" : it?.label}</span>
                  {it && <span className="block truncate text-[11px] text-muted">{Object.entries(it.fields).slice(0, 4).map(([k, v]) => `${k}: ${String(v)}`).join(" · ")}</span>}
                </span>
                <span className="text-[11px] text-muted">{draft ? `${jobs.length} job(s)` : `${done}/${jobs.length}`}</span>
                <span className="text-muted" aria-hidden="true">{isOpen ? "▾" : "▸"}</span>
              </button>
              {isOpen && (
                <div className="grid gap-1 p-1.5">
                  {draft && it && (
                    <div className="flex justify-end">
                      <button type="button" className="cc-link text-accent" disabled={busy} onClick={() => setPanel({ kind: "item", key })}>Edit item</button>
                    </div>
                  )}
                  {panel?.kind === "item" && panel.key === key && it && (
                    <ItemForm item={it} busy={item.isPending} error={error} onCancel={() => setPanel(null)} onSave={(fields) => item.mutate({ key, fields })} />
                  )}
                  {jobs.map(row)}
                </div>
              )}
            </div>
          );
        })}
        {groupKeys.length > shown && (
          <button type="button" className="btn btn-secondary btn-sm justify-self-center" onClick={() => setShown((n) => n + PAGE)}>
            Show {Math.min(PAGE, groupKeys.length - shown)} more of {groupKeys.length - shown}
          </button>
        )}
      </div>

      {panel?.kind === "add" && (
        <AddJobForm items={items} tz={tz} busy={add.isPending} error={error} onCancel={() => setPanel(null)} onAdd={(job) => add.mutate(job)} />
      )}
      {panel?.kind === "schedule" && (
        <SchedulePanel plan={plan} tz={tz} busy={schedule.isPending} error={error} onCancel={() => setPanel(null)} onSave={(s) => schedule.mutate(s)} />
      )}
      {panel?.kind === "submit" && (
        <SubmitSheet plan={plan} tz={tz} busy={submit.isPending} error={error} onCancel={() => setPanel(null)} onConfirm={() => submit.mutate()} />
      )}
      {error && !panel && <p className="mb-0 mt-2 text-xs text-danger" role="alert">{error}</p>}

      <div className="mt-3 flex flex-wrap justify-end gap-2 border-t border-border pt-3">
        {draft ? (
          <>
            <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => setPanel({ kind: "add" })}>+ Add job</button>
            <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => setPanel({ kind: "schedule" })}>
              ⏰ {plan.mode === "parallel" ? `Several at once (${plan.concurrency ?? 3})` : plan.mode === "scheduled" ? "On a schedule" : "One after another"}
            </button>
            <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => control.mutate("cancel")}>Discard</button>
            <button type="button" className="btn btn-sm" disabled={busy || total === 0} onClick={() => setPanel({ kind: "submit" })} data-testid="review-submit">
              Review &amp; submit
            </button>
          </>
        ) : plan.status === "cancelled" || plan.status === "executed" ? (
          (counts.failed ?? 0) > 0 ? <button type="button" className="btn btn-sm" disabled={busy} onClick={() => control.mutate("retry-failed")}>Retry failed</button> : null
        ) : (
          <>
            {(counts.pending_approval ?? 0) > 0 && <button type="button" className="btn btn-sm" disabled={busy} onClick={() => approveAll.mutate()}>Approve all I can</button>}
            {(counts.failed ?? 0) > 0 && <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => control.mutate("retry-failed")}>Retry failed</button>}
            {plan.status === "paused" ? (
              <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => control.mutate("resume")}>Resume</button>
            ) : (
              <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => control.mutate("pause")}>Pause</button>
            )}
            <button type="button" className="btn btn-secondary btn-sm" disabled={busy}
                    onClick={() => window.confirm("Cancel the jobs that haven't run? Jobs already done are kept.") && control.mutate("cancel")}>Cancel</button>
          </>
        )}
      </div>
    </div>
  );
}
