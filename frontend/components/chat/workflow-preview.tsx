"use client";

import { Fragment } from "react";

import { useWorkflowCatalog } from "@/components/workflows/workflow-editor";

// Mini trigger -> condition -> actions diagram for a chat-drafted workflow
// (SPEC-FE-041), using the visual builder's own node styles (.wf-node), so a
// chat draft looks exactly like it will on the Workflow Builder canvas.
function text(params: Record<string, unknown>): string {
  return Object.entries(params)
    .filter(([, v]) => v !== "" && v !== null && v !== undefined)
    .map(([k, v]) => `${k.replace(/_/g, " ")}: ${String(v)}`)
    .join(" · ");
}

export default function WorkflowPreview({ params }: { params: Record<string, unknown> }) {
  const catalog = useWorkflowCatalog();
  const trigger = String(params.trigger_type ?? "");
  const triggerLabel = catalog.data?.triggers.find((t) => t.type === trigger)?.label ?? trigger;
  const actions = Array.isArray(params.actions) ? (params.actions as { type?: string; params?: Record<string, unknown> }[]) : [];
  const condition = typeof params.condition_dsl === "string" ? params.condition_dsl : "";
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5 overflow-x-auto">
      <div className="wf-node wf-trigger">
        <div className="wf-node-type">Trigger</div>
        <div className="wf-node-title">{triggerLabel}</div>
        <div className="mt-1.5 break-words text-[11px] text-muted">{text((params.trigger_config as Record<string, unknown>) ?? {})}</div>
      </div>
      {condition && (
        <>
          <div className="wf-arrow">→</div>
          <div className="wf-node wf-condition">
            <div className="wf-node-type">Condition</div>
            <div className="wf-node-title">Only if</div>
            <div className="mt-1.5 break-words text-[11px] text-muted">{condition}</div>
          </div>
        </>
      )}
      {actions.map((a, i) => (
        <Fragment key={i}>
          <div className="wf-arrow">→</div>
          <div className="wf-node wf-action">
            <div className="wf-node-type">Action</div>
            <div className="wf-node-title">{catalog.data?.actions.find((x) => x.type === a.type)?.label ?? a.type}</div>
            <div className="mt-1.5 break-words text-[11px] text-muted">{text(a.params ?? {})}</div>
          </div>
        </Fragment>
      ))}
    </div>
  );
}
