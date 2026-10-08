"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, type ReactNode } from "react";

import { wfErrorText } from "@/components/workflows/workflow-editor";
import { fetchWorkflows, setWorkflowEnabled, workflowDetailKey, workflowKeys } from "@/lib/api/workflows";
import type { WorkflowListItem } from "@/lib/types/workflows";

const COLUMN_COUNT = 5;

function MessageRow({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <tr>
      <td colSpan={COLUMN_COUNT} className={className}>
        {children}
      </td>
    </tr>
  );
}

// The backend maps the boolean workflows.enabled to the label "Enabled" /
// "Paused" (SPEC-BE-014); those are its only two values. SPEC-FE-034 makes the
// badge a toggle (click does not select the row).
function StatusToggle({ workflow }: { workflow: WorkflowListItem }) {
  const queryClient = useQueryClient();
  const toggle = useMutation({
    mutationFn: () => setWorkflowEnabled(workflow.id, workflow.status !== "Enabled"),
    onSuccess: (d) => {
      queryClient.setQueryData(workflowDetailKey(d.id), d);
      void queryClient.invalidateQueries({ queryKey: workflowKeys.list });
    },
  });
  return (
    <>
      <button
        type="button"
        title={workflow.status === "Enabled" ? "Click to pause" : "Click to enable"}
        className={`badge cursor-pointer border-none ${workflow.status === "Enabled" ? "badge-success" : "badge-warn"}`}
        disabled={toggle.isPending}
        onClick={(e) => {
          e.stopPropagation();
          toggle.mutate();
        }}
      >
        {workflow.status}
      </button>
      {toggle.isError && (
        <div className="text-xs text-danger" role="alert">
          {wfErrorText(toggle.error)}
        </div>
      )}
    </>
  );
}

export type SavedWorkflowsTableProps = {
  selectedId: string | null;
  onSelect: (id: string | null) => void;
};

// Workflows page "Saved Workflows" table (SPEC-FE-017). Rows are rendered in
// the order the backend returns them; every cell is a real response field.
// SPEC-FE-018 adds row selection (a reasoned master-detail reading, as in
// SPEC-FE-013): clicking a row drives the canvas; the first row is the default.
export default function SavedWorkflowsTable({ selectedId, onSelect }: SavedWorkflowsTableProps) {
  const workflows = useQuery({ queryKey: workflowKeys.list, queryFn: fetchWorkflows });
  const data = workflows.data;
  useEffect(() => {
    if (!data) return;
    if (!data.some((w) => w.id === selectedId)) onSelect(data[0]?.id ?? null);
    // Only when the list changes; onSelect is the page's stable state setter.
  }, [data]);

  let body: ReactNode;
  if (workflows.isPending) {
    body = <MessageRow className="text-muted">Loading…</MessageRow>;
  } else if (workflows.isError) {
    body = (
      <MessageRow className="text-danger">
        <span role="alert">Failed to load workflows: {workflows.error.message}</span>
      </MessageRow>
    );
  } else if (workflows.data.length === 0) {
    body = <MessageRow className="text-muted">No workflows yet</MessageRow>;
  } else {
    body = workflows.data.map((w) => {
      const cell = w.id === selectedId ? "bg-accent-soft" : undefined;
      return (
        <tr
          key={w.id}
          tabIndex={0}
          aria-selected={w.id === selectedId}
          className="cursor-pointer"
          onClick={() => onSelect(w.id)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onSelect(w.id);
            }
          }}
        >
          <td className={cell}>{w.name}</td>
          {/* Raw trigger_type exactly as returned (e.g. "inventory_low"), not prose. */}
          <td className={cell}>{w.trigger_type}</td>
          <td className={cell}>{String(w.actions_count)}</td>
          <td className={cell}>{String(w.runs_7d)}</td>
          <td className={cell}>
            <StatusToggle workflow={w} />
          </td>
        </tr>
      );
    });
  }

  return (
    <>
      <h2 className="section-title">Saved Workflows</h2>
      <div className="card" style={{ padding: 0 }} aria-busy={workflows.isPending}>
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Trigger</th>
              <th>Actions</th>
              <th>Runs (7d)</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>{body}</tbody>
        </table>
      </div>
    </>
  );
}
