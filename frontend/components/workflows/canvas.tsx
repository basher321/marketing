"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useState } from "react";

import { VersionsPanel, WorkflowEditor, useWorkflowCatalog, wfErrorText } from "@/components/workflows/workflow-editor";
import { fetchWorkflow, setWorkflowEnabled, testRunWorkflow, workflowDetailKey, workflowKeys } from "@/lib/api/workflows";
import type { WorkflowCatalog, WorkflowDetailV2 } from "@/lib/types/workflows";

function paramsText(params: Record<string, unknown>): string {
  return Object.entries(params)
    .filter(([, v]) => v !== "" && v !== null && v !== undefined)
    .map(([k, v]) => `${k.replace(/_/g, " ")}: ${String(v)}`)
    .join(" · ");
}

function Node({ kind, title, subtitle }: { kind: "trigger" | "condition" | "action"; title: string; subtitle: string }) {
  const label = { trigger: "Trigger", condition: "Condition", action: "Action" }[kind];
  return (
    <div className={`wf-node wf-${kind}`}>
      <div className="wf-node-type">{label}</div>
      <div className="wf-node-title">{title}</div>
      {subtitle && <div className="mt-1.5 break-words text-[11px] text-muted">{subtitle}</div>}
    </div>
  );
}

function Flow({ detail, catalog }: { detail: WorkflowDetailV2; catalog?: WorkflowCatalog }) {
  const tLabel = catalog?.triggers.find((t) => t.type === detail.trigger_type)?.label ?? detail.trigger_type;
  return (
    <>
      <Node kind="trigger" title={tLabel} subtitle={paramsText(detail.trigger_config)} />
      {detail.condition_dsl && (
        <>
          <div className="wf-arrow">→</div>
          <Node kind="condition" title="Only if" subtitle={detail.condition_dsl} />
        </>
      )}
      {detail.actions.map((a, i) => {
        const { type, ...params } = (a && typeof a === "object" ? a : {}) as Record<string, unknown>;
        const label = catalog?.actions.find((x) => x.type === type)?.label ?? (typeof type === "string" ? type : "(no type)");
        return (
          <Fragment key={i}>
            <div className="wf-arrow">→</div>
            <Node kind="action" title={label} subtitle={paramsText(params)} />
          </Fragment>
        );
      })}
    </>
  );
}

type Mode = { kind: "view" } | { kind: "new" } | { kind: "edit" } | { kind: "versions" };

// Workflow Builder (SPEC-FE-018, made fully functional by SPEC-FE-034):
// + New Workflow, Edit (saves a new version), Enable/Disable, Test Run (dry
// run, result shown right under the toolbar), and Version History with View /
// Restore. The canvas shows the selected workflow, or an older version being viewed.
export default function WorkflowCanvas({
  workflowId,
  onSelect,
}: {
  workflowId: string | null;
  onSelect: (id: string) => void;
}) {
  const queryClient = useQueryClient();
  const catalog = useWorkflowCatalog();
  const [mode, setMode] = useState<Mode>({ kind: "view" });
  const [viewingId, setViewingId] = useState<string | null>(null);
  const detail = useQuery({
    queryKey: workflowDetailKey(workflowId ?? "none"),
    queryFn: () => fetchWorkflow(workflowId!),
    enabled: workflowId !== null,
  });
  const viewing = useQuery({
    queryKey: workflowDetailKey(viewingId ?? "none"),
    queryFn: () => fetchWorkflow(viewingId!),
    enabled: viewingId !== null,
  });
  const run = useMutation({
    mutationFn: () => testRunWorkflow(workflowId!),
    // A test run adds a workflow_runs row, so Runs (7d) in the table changes.
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: workflowKeys.list }),
  });
  const toggle = useMutation({
    mutationFn: () => setWorkflowEnabled(workflowId!, detail.data?.status !== "Enabled"),
    onSuccess: (d) => {
      queryClient.setQueryData(workflowDetailKey(d.id), d);
      void queryClient.invalidateQueries({ queryKey: workflowKeys.list });
    },
  });
  const openSaved = (d: WorkflowDetailV2) => {
    queryClient.setQueryData(workflowDetailKey(d.id), d);
    setViewingId(null);
    setMode({ kind: "view" });
    run.reset();
    onSelect(d.id);
  };

  const shown = viewingId && viewing.data ? viewing.data : detail.data;
  const actionLabel = (type: string) => catalog.data?.actions.find((a) => a.type === type)?.label ?? type;

  return (
    <>
      <div className="mb-4 flex flex-wrap gap-2">
        <button type="button" className="btn" onClick={() => setMode({ kind: "new" })}>
          + New Workflow
        </button>
        <button type="button" className="btn btn-secondary" disabled={!detail.data} onClick={() => setMode({ kind: "edit" })}>
          Edit
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={workflowId === null || run.isPending}
          onClick={() => {
            setViewingId(null);
            run.mutate();
          }}
        >
          {run.isPending ? "Running…" : "Test Run"}
        </button>
        <button type="button" className="btn btn-secondary" disabled={!detail.data || toggle.isPending} onClick={() => toggle.mutate()}>
          {detail.data?.status === "Enabled" ? "Disable" : "Enable"}
        </button>
        <button type="button" className="btn btn-secondary" disabled={!detail.data} onClick={() => setMode(mode.kind === "versions" ? { kind: "view" } : { kind: "versions" })}>
          Version History
        </button>
      </div>
      {toggle.isError && (
        <p className="mb-3 mt-0 text-xs text-danger" role="alert">
          {wfErrorText(toggle.error)}
        </p>
      )}

      {mode.kind === "new" && <WorkflowEditor key="new" onSaved={openSaved} onCancel={() => setMode({ kind: "view" })} />}
      {mode.kind === "edit" && detail.data && (
        <WorkflowEditor key={`edit-${detail.data.id}`} existing={detail.data} onSaved={openSaved} onCancel={() => setMode({ kind: "view" })} />
      )}
      {mode.kind === "versions" && workflowId && (
        <VersionsPanel
          workflowId={workflowId}
          viewingId={viewingId}
          onView={setViewingId}
          onRestored={openSaved}
          onClose={() => {
            setViewingId(null);
            setMode({ kind: "view" });
          }}
        />
      )}

      {(run.isPending || run.isError || run.data) && (
        <div className="card mb-4" data-testid="test-run-result">
          <h3 className="mt-0 text-sm">
            Test run{detail.data ? ` of “${detail.data.name}” v${detail.data.version}` : ""} — dry run, nothing was sent
          </h3>
          {run.isPending ? (
            <p className="m-0 text-[13px] text-muted">Running…</p>
          ) : run.isError ? (
            <p className="m-0 text-[13px] text-danger" role="alert">
              {wfErrorText(run.error)}
            </p>
          ) : run.data ? (
            <>
              <p className="m-0 mb-2 text-[13px]">
                <span className={`badge ${run.data.workflow_run.status === "succeeded" ? "badge-success" : "badge-danger"}`}>
                  {run.data.workflow_run.status === "succeeded" ? "Passed" : "Failed"}
                </span>{" "}
                {run.data.workflow_run.status === "succeeded"
                  ? `All ${run.data.action_executions.length} step(s) would run.`
                  : run.data.workflow_run.error}
              </p>
              <ol className="m-0 pl-5 text-[13px]">
                {run.data.action_executions.map((x) => (
                  <li key={x.action_index}>
                    {actionLabel(x.type)} — <span className="text-success">simulated OK</span>
                  </li>
                ))}
              </ol>
            </>
          ) : null}
        </div>
      )}

      {viewingId && viewing.data && (
        <p className="mb-2 mt-0 text-[13px]">
          <span className="badge badge-warn">Viewing v{viewing.data.version} (read-only)</span>{" "}
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setViewingId(null)}>
            Back to current
          </button>
        </p>
      )}
      {shown && !viewingId && (
        <p className="mb-2 mt-0 text-[13px] text-muted">
          <b className="text-text">{shown.name}</b> · v{shown.version} ·{" "}
          <span className={`badge ${shown.status === "Enabled" ? "badge-success" : "badge-warn"}`}>{shown.status}</span>
          {shown.description && <> · {shown.description}</>}
        </p>
      )}
      <div className="workflow-canvas">
        {workflowId === null ? (
          <span className="text-[13px] text-muted">No workflow selected — create one with “+ New Workflow”.</span>
        ) : detail.isPending ? (
          <span className="text-[13px] text-muted">Loading workflow…</span>
        ) : detail.isError ? (
          <span className="text-[13px] text-danger" role="alert">
            Failed to load workflow: {detail.error.message}
          </span>
        ) : shown ? (
          <Flow detail={shown} catalog={catalog.data} />
        ) : null}
      </div>
    </>
  );
}
