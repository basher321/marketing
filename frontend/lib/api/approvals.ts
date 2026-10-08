/**
 * approval_queue API (SPEC-FE-010) against the backend's
 * app/api/v1/approvals.py. This module is the ONLY place the frontend calls
 * /api/v1/approvals/*: the Command Chat plan card (SPEC-FE-009) and the
 * Pending Approvals panel both act on the same approval_queue rows (a plan
 * action's approval_id is an approval_queue id) and must share these calls.
 *
 * Deciding needs manager+ on the backend. An already-decided item -> 409,
 * another tenant's or a missing item -> 404 (both surface as ApiError).
 */
import type {
  ApprovalDecisionResult,
  GroupDecisionResult,
  PendingApprovalList,
} from "../types/approvals";
import { apiFetch } from "./client";

const BASE = "/api/v1/approvals";

/**
 * Shared TanStack Query key namespace for every approval_queue view. After
 * any approve/reject (panel or plan card), invalidate `approvalKeys.all` so
 * every approvals query refetches, and record the decision under
 * `approvalKeys.decisions` so both surfaces show the same real state.
 */
export const approvalKeys = {
  all: ["approvals"] as const,
  pending: ["approvals", "pending"] as const,
  /** Client-side map approval_id -> decision, filled only from real decision responses. */
  decisions: ["approvals", "decisions"] as const,
};

export function fetchPendingApprovals(): Promise<PendingApprovalList> {
  return apiFetch<PendingApprovalList>(`${BASE}/pending`);
}

export function approveApproval(approvalId: string): Promise<ApprovalDecisionResult> {
  return apiFetch<ApprovalDecisionResult>(`${BASE}/${approvalId}/approve`, { method: "POST" });
}

export function rejectApproval(approvalId: string, reason?: string): Promise<ApprovalDecisionResult> {
  return apiFetch<ApprovalDecisionResult>(`${BASE}/${approvalId}/reject`, {
    method: "POST",
    body: reason ? { reason } : undefined,
  });
}

/** Approve every still-pending item sharing subject_id (a plan's id, SPEC-FE-009). */
export function approveGroup(subjectId: string): Promise<GroupDecisionResult> {
  return apiFetch<GroupDecisionResult>(`${BASE}/groups/${subjectId}/approve`, { method: "POST" });
}

/** Reject every still-pending item sharing subject_id (a plan's id, SPEC-FE-009). */
export function rejectGroup(subjectId: string, reason?: string): Promise<GroupDecisionResult> {
  return apiFetch<GroupDecisionResult>(`${BASE}/groups/${subjectId}/reject`, {
    method: "POST",
    body: reason ? { reason } : undefined,
  });
}
