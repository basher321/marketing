/**
 * Saved-workflows list types (SPEC-FE-017), mirroring the backend Pydantic
 * schema in app/schemas/workflow.py field for field.
 */

/** GET /api/v1/workflows — backend WorkflowListItem (SPEC-BE-014). */
export interface WorkflowListItem {
  id: string;
  name: string;
  /**
   * Raw live workflow_trigger_type enum value, e.g. "inventory_low" (the live
   * enum uses underscores, not the mockup's "inventory.low").
   */
  trigger_type: string;
  /** Length of the workflow's stored actions array, computed by the backend. */
  actions_count: number;
  /** workflow_runs with started_at in the last 7 days (UTC), computed by the backend. */
  runs_7d: number;
  /**
   * Backend label for the boolean workflows.enabled column (true -> "Enabled",
   * false -> "Paused"); the boolean itself is not returned.
   */
  status: "Enabled" | "Paused";
}

/** GET /api/v1/workflows/{id} — backend WorkflowDetail (SPEC-FE-018). Raw stored values. */
export interface WorkflowDetail {
  id: string;
  name: string;
  trigger_type: string;
  trigger_config: Record<string, unknown>;
  /** Raw condition text (never parsed server-side); null when the workflow has none. */
  condition_dsl: string | null;
  /** The stored actions array as-is; each is normally { type, ...config }. */
  actions: unknown[];
  status: "Enabled" | "Paused";
}

/** POST /api/v1/workflows/{id}/test — backend WorkflowTestResult (SPEC-BE-034, dry run). */
export interface WorkflowTestResult {
  workflow_run: {
    id: string;
    /** Live run_status: "succeeded" | "failed" for a finished dry run. */
    status: string;
    started_at: string;
    finished_at: string | null;
    error: string | null;
  };
  action_executions: {
    action_index: number;
    type: string;
    status: string;
    /** { simulated: true, message: "Dry run - no external call made" } */
    output: Record<string, unknown>;
  }[];
}

// ---- SPEC-FE-034 / SPEC-BE-049: editor, versions ----

/** Extra detail fields added by SPEC-BE-049. */
export interface WorkflowDetailV2 extends WorkflowDetail {
  description: string | null;
  version: number;
  /** false for a superseded (history) version. */
  is_current: boolean;
}

export interface WorkflowCatalogField {
  key: string;
  label: string;
  kind: "text" | "number" | "select" | "url";
  required: boolean;
  options: string[];
  help: string;
}

export interface WorkflowCatalogEntry {
  type: string;
  label: string;
  fields: WorkflowCatalogField[];
}

/** GET /api/v1/workflows/catalog — drives the editor's forms. */
export interface WorkflowCatalog {
  triggers: WorkflowCatalogEntry[];
  actions: WorkflowCatalogEntry[];
  condition_help: string;
  condition_examples: string[];
}

/** POST /api/v1/workflows and PUT /api/v1/workflows/{id} body. */
export interface WorkflowSave {
  name: string;
  description: string | null;
  trigger_type: string;
  trigger_config: Record<string, unknown>;
  condition_dsl: string | null;
  actions: { type: string; params: Record<string, unknown> }[];
  enabled?: boolean;
}

export interface WorkflowVersion {
  id: string;
  version: number;
  created_at: string;
  created_by_name: string | null;
  name: string;
  trigger_type: string;
  action_count: number;
  enabled: boolean;
  is_current: boolean;
}
