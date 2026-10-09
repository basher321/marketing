"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import {
  createWorkflow,
  fetchWorkflowCatalog,
  fetchWorkflowVersions,
  restoreWorkflowVersion,
  updateWorkflow,
  workflowKeys,
  workflowVersionsKey,
} from "@/lib/api/workflows";
import { ApiError, isRoleDenied } from "@/lib/types/common";
import type { WorkflowCatalogField, WorkflowDetailV2 } from "@/lib/types/workflows";

const FORBIDDEN = "Only managers and above can edit workflows.";

/** A readable message: 403 in plain words; FastAPI 422 field errors joined; else the backend's text. */
export function wfErrorText(err: Error): string {
  if (err instanceof ApiError) {
    if (isRoleDenied(err)) return FORBIDDEN;
    const detail = (err.body as { detail?: unknown } | undefined)?.detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d: { msg?: string; loc?: unknown[] }) => (d.msg ?? "").replace(/^Value error, /, ""))
        .filter(Boolean)
        .join(" ");
    }
  }
  return err.message;
}

/** Catalog labels for triggers / actions, shared with the canvas. */
export function useWorkflowCatalog() {
  return useQuery({ queryKey: workflowKeys.catalog, queryFn: fetchWorkflowCatalog, staleTime: Infinity });
}

function FieldInput({
  field,
  value,
  onChange,
  idPrefix,
}: {
  field: WorkflowCatalogField;
  value: unknown;
  onChange: (v: string) => void;
  idPrefix: string;
}) {
  const id = `${idPrefix}_${field.key}`;
  const text = value === undefined || value === null ? "" : String(value);
  return (
    <div className="form-row mb-2">
      <label htmlFor={id} className="text-xs">
        {field.label}
        {!field.required && <span className="font-normal text-muted"> (optional)</span>}
      </label>
      {field.kind === "select" ? (
        <select id={id} value={text} onChange={(e) => onChange(e.target.value)}>
          <option value="">{field.required ? "Choose…" : "—"}</option>
          {field.options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      ) : (
        <input id={id} type={field.kind === "number" ? "number" : field.kind === "url" ? "url" : "text"} value={text} onChange={(e) => onChange(e.target.value)} />
      )}
      {field.help && <span className="text-xs text-muted">{field.help}</span>}
    </div>
  );
}

type Step = { key: number; type: string; params: Record<string, unknown> };
let stepKey = 0;

function stepsFrom(detail?: WorkflowDetailV2): Step[] {
  const raw = detail?.actions ?? [];
  return raw.map((a) => {
    const { type, ...params } = (a && typeof a === "object" ? a : {}) as Record<string, unknown>;
    return { key: ++stepKey, type: typeof type === "string" ? type : "", params };
  });
}

// "+ New Workflow" / "Edit" (SPEC-FE-034): name, trigger (+ its config fields),
// optional condition, and an ordered list of actions (+ their params). Every
// form field comes from the backend catalog. Saving an edit creates a new
// version; the old one stays in Version History.
export function WorkflowEditor({
  existing,
  onSaved,
  onCancel,
}: {
  existing?: WorkflowDetailV2;
  onSaved: (d: WorkflowDetailV2) => void;
  onCancel: () => void;
}) {
  const queryClient = useQueryClient();
  const catalog = useWorkflowCatalog();
  const [name, setName] = useState(existing?.name ?? "");
  const [description, setDescription] = useState(existing?.description ?? "");
  const [triggerType, setTriggerType] = useState(existing?.trigger_type ?? "");
  const [triggerConfig, setTriggerConfig] = useState<Record<string, unknown>>(existing?.trigger_config ?? {});
  const [condition, setCondition] = useState(existing?.condition_dsl ?? "");
  const [steps, setSteps] = useState<Step[]>(() => (existing ? stepsFrom(existing) : [{ key: ++stepKey, type: "", params: {} }]));

  const save = useMutation({
    mutationFn: () => {
      const body = {
        name: name.trim(),
        description: description.trim() || null,
        trigger_type: triggerType,
        trigger_config: triggerConfig,
        condition_dsl: condition.trim() || null,
        actions: steps.map((s) => ({ type: s.type, params: s.params })),
      };
      return existing ? updateWorkflow(existing.id, body) : createWorkflow(body);
    },
    onSuccess: (d) => {
      void queryClient.invalidateQueries({ queryKey: workflowKeys.all });
      onSaved(d);
    },
  });

  if (catalog.isPending) return <div className="card">Loading editor…</div>;
  if (catalog.isError) return <div className="card text-danger">Failed to load the workflow catalog: {catalog.error.message}</div>;
  const trigger = catalog.data.triggers.find((t) => t.type === triggerType);
  const setStep = (key: number, patch: Partial<Step>) => setSteps((cur) => cur.map((s) => (s.key === key ? { ...s, ...patch } : s)));
  const move = (i: number, d: number) =>
    setSteps((cur) => {
      const next = [...cur];
      const [x] = next.splice(i, 1);
      next.splice(i + d, 0, x);
      return next;
    });

  return (
    <form
      className="card mb-4"
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <h3 className="mt-0">{existing ? `Edit “${existing.name}” (saves as v${existing.version + 1})` : "New workflow"}</h3>
      <div className="form-grid-2">
        <div className="form-row">
          <label htmlFor="wf_name">Name</label>
          <input id="wf_name" required maxLength={255} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor="wf_desc">Description (optional)</label>
          <input id="wf_desc" maxLength={2000} value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>
      </div>

      <div className="rounded-md border border-border p-3">
        <div className="wf-node-type mb-2">1 · Trigger — when should this run?</div>
        <div className="form-row mb-2">
          <label htmlFor="wf_trigger" className="text-xs">
            Trigger
          </label>
          <select
            id="wf_trigger"
            required
            value={triggerType}
            onChange={(e) => {
              setTriggerType(e.target.value);
              setTriggerConfig({});
            }}
          >
            <option value="">Choose a trigger…</option>
            {catalog.data.triggers.map((t) => (
              <option key={t.type} value={t.type}>
                {t.label}
              </option>
            ))}
          </select>
        </div>
        {trigger?.fields.map((f) => (
          <FieldInput key={f.key} field={f} idPrefix="wf_tc" value={triggerConfig[f.key]} onChange={(v) => setTriggerConfig((c) => ({ ...c, [f.key]: v }))} />
        ))}
      </div>

      <div className="mt-3 rounded-md border border-border p-3">
        <div className="wf-node-type mb-2">2 · Condition — only continue if… (optional)</div>
        <input id="wf_condition" className="w-full rounded-md border border-border bg-panel px-3 py-2 text-[13.5px] text-text" placeholder={catalog.data.condition_examples[0]} value={condition} onChange={(e) => setCondition(e.target.value)} />
        <p className="m-0 mt-1 text-xs text-muted">
          {catalog.data.condition_help} Examples: {catalog.data.condition_examples.map((x) => `“${x}”`).join(", ")}
        </p>
      </div>

      <div className="mt-3 rounded-md border border-border p-3">
        <div className="wf-node-type mb-2">3 · Actions — then do this, in order</div>
        {steps.map((s, i) => {
          const spec = catalog.data.actions.find((a) => a.type === s.type);
          return (
            <div key={s.key} className="mb-3 rounded-md bg-bg p-3" data-step={i + 1}>
              <div className="mb-2 flex items-center gap-2">
                <b className="text-[13px]">Step {i + 1}</b>
                <select
                  aria-label={`Step ${i + 1} action`}
                  className="flex-1 rounded-md border border-border bg-panel px-2 py-1.5 text-[13px] text-text"
                  required
                  value={s.type}
                  onChange={(e) => setStep(s.key, { type: e.target.value, params: {} })}
                >
                  <option value="">Choose an action…</option>
                  {catalog.data.actions.map((a) => (
                    <option key={a.type} value={a.type}>
                      {a.label}
                    </option>
                  ))}
                </select>
                <button type="button" className="btn btn-ghost btn-sm" aria-label={`Move step ${i + 1} up`} disabled={i === 0} onClick={() => move(i, -1)}>
                  ↑
                </button>
                <button type="button" className="btn btn-ghost btn-sm" aria-label={`Move step ${i + 1} down`} disabled={i === steps.length - 1} onClick={() => move(i, 1)}>
                  ↓
                </button>
                <button type="button" className="btn btn-ghost btn-sm text-danger" disabled={steps.length === 1} onClick={() => setSteps((cur) => cur.filter((x) => x.key !== s.key))}>
                  Remove
                </button>
              </div>
              {spec?.fields.map((f) => (
                <FieldInput key={f.key} field={f} idPrefix={`wf_s${i + 1}`} value={s.params[f.key]} onChange={(v) => setStep(s.key, { params: { ...s.params, [f.key]: v } })} />
              ))}
            </div>
          );
        })}
        <button type="button" className="btn btn-secondary btn-sm" disabled={steps.length >= 10} onClick={() => setSteps((cur) => [...cur, { key: ++stepKey, type: "", params: {} }])}>
          + Add step
        </button>
      </div>

      {save.isError && (
        <p className="mb-0 mt-3 text-xs text-danger" role="alert">
          {wfErrorText(save.error)}
        </p>
      )}
      <div className="mt-4 flex gap-2">
        <button type="submit" className="btn" disabled={save.isPending}>
          {save.isPending ? "Saving…" : existing ? "Save as new version" : "Create workflow"}
        </button>
        <button type="button" className="btn btn-secondary" disabled={save.isPending} onClick={onCancel}>
          Cancel
        </button>
      </div>
      {!existing && <p className="mb-0 mt-2 text-xs text-muted">New workflows start paused — enable them when you&apos;re ready.</p>}
    </form>
  );
}

// Version History (SPEC-FE-034): every saved version, newest first, with View
// (show that version on the canvas) and Restore (creates a new version).
export function VersionsPanel({
  workflowId,
  viewingId,
  onView,
  onRestored,
  onClose,
}: {
  workflowId: string;
  viewingId: string | null;
  onView: (versionId: string | null) => void;
  onRestored: (d: WorkflowDetailV2) => void;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const versions = useQuery({ queryKey: workflowVersionsKey(workflowId), queryFn: () => fetchWorkflowVersions(workflowId) });
  const restore = useMutation({
    mutationFn: (versionId: string) => restoreWorkflowVersion(workflowId, versionId),
    onSuccess: (d) => {
      void queryClient.invalidateQueries({ queryKey: workflowKeys.all });
      onRestored(d);
    },
  });
  return (
    <div className="card mb-4" data-testid="versions-panel">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="m-0">Version history</h3>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>
          Close
        </button>
      </div>
      {versions.isPending ? (
        <p className="text-[13px] text-muted">Loading versions…</p>
      ) : versions.isError ? (
        <p className="text-[13px] text-danger">Failed to load versions: {versions.error.message}</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Version</th>
              <th>Saved</th>
              <th>By</th>
              <th>Name</th>
              <th>Steps</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {versions.data.map((v) => (
              <tr key={v.id} data-version={v.version} className={viewingId === v.id ? "bg-accent-soft" : undefined}>
                <td>
                  v{v.version} {v.is_current && <span className="badge badge-success">current</span>}
                </td>
                <td>{new Date(v.created_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })}</td>
                <td>{v.created_by_name ?? "—"}</td>
                <td>{v.name}</td>
                <td>{v.action_count}</td>
                <td className="whitespace-nowrap text-right">
                  {!v.is_current && (
                    <>
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => onView(viewingId === v.id ? null : v.id)}>
                        {viewingId === v.id ? "Hide" : "View"}
                      </button>{" "}
                      <button
                        type="button"
                        className="btn btn-sm"
                        disabled={restore.isPending}
                        onClick={() => {
                          if (window.confirm(`Restore v${v.version}? It will be saved as a new version.`)) restore.mutate(v.id);
                        }}
                      >
                        Restore
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {restore.isError && (
        <p className="mb-0 mt-2 text-xs text-danger" role="alert">
          {wfErrorText(restore.error)}
        </p>
      )}
    </div>
  );
}
