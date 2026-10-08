"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { approvalKeys, approveApproval, fetchPendingApprovals } from "@/lib/api/approvals";
import { ApiError } from "@/lib/types/common";

import { useRecordDecisions, type Decision } from "./decisions";

// "12 min ago" / "1h ago" (mockup), computed client-side from requested_at.
function ago(iso: string): string {
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60_000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  return `${Math.floor(minutes / 60)}h ago`;
}

// Pending Approvals panel (SPEC-FE-010), markup from the reference mockup.
// Shares the approvals key namespace with the chat plan card (SPEC-FE-009).
export default function ApprovalsPanel() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: approvalKeys.pending, queryFn: fetchPendingApprovals });
  const record = useRecordDecisions();
  const [error, setError] = useState<string | null>(null);

  const approve = useMutation({
    mutationFn: (id: string) => approveApproval(id),
    onMutate: () => setError(null),
    onSuccess: (res) => record({ [res.id]: res.decision as Decision }),
    onError: (err) => {
      setError(err instanceof Error ? err.message : String(err));
      // Already decided elsewhere (409) or gone (404): refresh the list.
      if (err instanceof ApiError && (err.status === 404 || err.status === 409)) {
        void queryClient.invalidateQueries({ queryKey: approvalKeys.pending });
      }
    },
  });

  return (
    <div className="approvals-panel">
      <h3 className="mt-0 text-sm">Pending Approvals{query.data ? ` (${query.data.count})` : ""}</h3>
      {query.isPending ? (
        <p className="text-[13px] text-muted">Loading approvals…</p>
      ) : query.isError ? (
        <p className="text-[13px] text-danger" role="alert">
          Failed to load approvals: {query.error.message}
        </p>
      ) : query.data.items.length === 0 ? (
        <p className="text-[13px] text-muted">Nothing pending</p>
      ) : (
        query.data.items.map((item) => (
          <div key={item.id} className="approval-item">
            <div className="approval-title">{item.title}</div>
            {/* The engine label is the backend's (SPEC-BE-020); items of no engine
                (reply, plan, action) show only the time rather than a guessed label. */}
            <div className="approval-meta">{item.engine ? `${item.engine} · ${ago(item.requested_at)}` : ago(item.requested_at)}</div>
            <div className="approval-buttons">
              {/* No detail view or endpoint exists for "View" yet: present but inert. */}
              <button type="button" className="btn btn-secondary btn-sm">
                View
              </button>
              <button
                type="button"
                className="btn btn-sm"
                disabled={approve.isPending}
                onClick={() => approve.mutate(item.id)}
              >
                Approve
              </button>
            </div>
          </div>
        ))
      )}
      {error && (
        <p className="mb-0 mt-2 text-xs text-danger" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
