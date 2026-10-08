"use client";

import { useEffect, useState } from "react";

import WorkflowCanvas from "@/components/workflows/canvas";
import SavedWorkflowsTable from "@/components/workflows/saved-workflows-table";

// Workflow Builder: title/subtitle from the reference mockup (SPEC-FE-002), the
// canvas + Test Run (SPEC-FE-018) for the workflow selected in the Saved
// Workflows table (SPEC-FE-017), plus New / Edit / Enable / Version History
// (SPEC-FE-034). The selection is lifted here; saving selects the new version.
export default function WorkflowsPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Deep link from Command Chat (SPEC-FE-041): /workflows?open=<id>.
  useEffect(() => {
    const open = new URLSearchParams(window.location.search).get("open");
    if (open) setSelectedId(open);
  }, []);
  return (
    <>
      <h1 className="m-0 mb-1 text-[22px] font-bold">{"Workflow Builder"}</h1>
      <p className="m-0 mb-5 text-muted">{"Compose triggers, conditions, and actions visually."}</p>
      <WorkflowCanvas workflowId={selectedId} onSelect={setSelectedId} />
      <SavedWorkflowsTable selectedId={selectedId} onSelect={setSelectedId} />
    </>
  );
}
