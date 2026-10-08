/**
 * Workflows API: saved-workflows list (SPEC-FE-017 / SPEC-BE-014), detail +
 * dry-run Test Run (SPEC-FE-018 / SPEC-BE-034), and create / versioned edit /
 * enable / version history / restore (SPEC-FE-034 / SPEC-BE-049). Reads and
 * Test Run are open to any role; the other writes need manager+ (403).
 */
import type {
  WorkflowCatalog,
  WorkflowDetailV2,
  WorkflowListItem,
  WorkflowSave,
  WorkflowTestResult,
  WorkflowVersion,
} from "../types/workflows";
import { apiFetch } from "./client";

export const workflowKeys = {
  all: ["workflows"] as const,
  list: ["workflows", "list"] as const,
  catalog: ["workflows", "catalog"] as const,
};

export function fetchWorkflows(): Promise<WorkflowListItem[]> {
  return apiFetch<WorkflowListItem[]>("/api/v1/workflows");
}

// Workflow Builder canvas + Test Run (SPEC-FE-018, backend SPEC-BE-034).
export const workflowDetailKey = (id: string) => ["workflows", id, "detail"] as const;
export const workflowVersionsKey = (id: string) => ["workflows", id, "versions"] as const;

export function fetchWorkflow(id: string): Promise<WorkflowDetailV2> {
  return apiFetch<WorkflowDetailV2>(`/api/v1/workflows/${encodeURIComponent(id)}`);
}

/** Dry run: records a workflow run with simulated actions; no external call is made. */
export function testRunWorkflow(id: string): Promise<WorkflowTestResult> {
  return apiFetch<WorkflowTestResult>(`/api/v1/workflows/${encodeURIComponent(id)}/test`, {
    method: "POST",
    body: {},
  });
}

export function fetchWorkflowCatalog(): Promise<WorkflowCatalog> {
  return apiFetch<WorkflowCatalog>("/api/v1/workflows/catalog");
}

export function createWorkflow(body: WorkflowSave): Promise<WorkflowDetailV2> {
  return apiFetch<WorkflowDetailV2>("/api/v1/workflows", { method: "POST", body: { ...body } });
}

/** Saving an edit creates a new version; the response is that new version. */
export function updateWorkflow(id: string, body: WorkflowSave): Promise<WorkflowDetailV2> {
  return apiFetch<WorkflowDetailV2>(`/api/v1/workflows/${encodeURIComponent(id)}`, { method: "PUT", body: { ...body } });
}

export function setWorkflowEnabled(id: string, enabled: boolean): Promise<WorkflowDetailV2> {
  return apiFetch<WorkflowDetailV2>(`/api/v1/workflows/${encodeURIComponent(id)}/enabled`, { method: "PATCH", body: { enabled } });
}

export function fetchWorkflowVersions(id: string): Promise<WorkflowVersion[]> {
  return apiFetch<WorkflowVersion[]>(`/api/v1/workflows/${encodeURIComponent(id)}/versions`);
}

export function restoreWorkflowVersion(id: string, versionId: string): Promise<WorkflowDetailV2> {
  return apiFetch<WorkflowDetailV2>(
    `/api/v1/workflows/${encodeURIComponent(id)}/versions/${encodeURIComponent(versionId)}/restore`,
    { method: "POST" },
  );
}
