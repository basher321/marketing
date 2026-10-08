/**
 * approval_queue types (SPEC-FE-010), mirroring the backend's
 * app/schemas/approval.py field for field. Datetimes are ISO-8601 strings.
 */

/** One row of GET /api/v1/approvals/pending (SPEC-BE-025). */
export interface PendingApprovalItem {
  id: string;
  subject_type: string;
  /** Backend-built display title, e.g. "Campaign: …"; render as-is. */
  title: string;
  /** SPEC-BE-020's engine label; null for subject types mapped to no engine (reply, plan, action). */
  engine: string | null;
  requested_at: string;
  elapsed_seconds: number;
}

/** GET /api/v1/approvals/pending: newest first; count === items.length. */
export interface PendingApprovalList {
  count: number;
  items: PendingApprovalItem[];
}

/** POST /api/v1/approvals/{id}/approve|reject (SPEC-BE-024). */
export interface ApprovalDecisionResult {
  id: string;
  subject_type: string;
  subject_id: string;
  title: string;
  decision: string;
  decided_by: string | null;
  decided_at: string | null;
  reason: string | null;
}

/** POST /api/v1/approvals/groups/{subject_id}/approve|reject (SPEC-BE-024). */
export interface GroupDecisionResult {
  subject_id: string;
  decision: string;
  decided_count: number;
  decided_ids: string[];
}
