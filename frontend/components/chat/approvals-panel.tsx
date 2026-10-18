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

// Pending Approvals panel (SPEC-FE-010 behavior, SPEC-FE-061 look).
// Shares the approvals key namespace with the chat plan card (SPEC-FE-009).
export default function ApprovalsPanel({ collapsible = false }: { collapsible?: boolean } = {}) {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: approvalKeys.pending, queryFn: fetchPendingApprovals });
  const record = useRecordDecisions();
  const [error, setError] = useState<string | null>(null);
  // Below the chat history it folds away, open by default when something waits (SPEC-FE-066).
  const [openState, setOpenState] = useState<boolean | null>(null);
  const open = !collapsible || (openState ?? (query.data?.count ?? 0) > 0);

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
    <aside className="cc-approvals" aria-label="Pending approvals">
      <div className="flex items-center justify-between gap-2">
        {collapsible ? (
          <button type="button" className="cc-fold" aria-expanded={open} onClick={() => setOpenState(!open)}>
            <span aria-hidden="true">{open ? "▾" : "▸"}</span> Pending Approvals
          </button>
        ) : (
          <h3 className="m-0 text-sm font-semibold">Pending Approvals</h3>
        )}
        {query.data && query.data.count > 0 && <span className="cc-count">{query.data.count}</span>}
      </div>
      {open && (
      <>
      <p className="m-0 mt-1 text-[11.5px] text-muted">Changes and spending wait here for approval.</p>
      {query.isPending ? (
        <div className="mt-3 grid gap-2">
          <div className="cc-shimmer h-16" />
          <div className="cc-shimmer h-16" />
        </div>
      ) : query.isError ? (
        <p className="text-[13px] text-danger" role="alert">
          Failed to load approvals: {query.error.message}
        </p>
      ) : query.data.items.length === 0 ? (
        <div className="mt-6 grid justify-items-center gap-1 text-center text-[13px] text-muted">
          <span className="cc-card-icon h-10 w-10 text-lg" aria-hidden="true">
            ✓
          </span>
          Nothing pending
        </div>
      ) : (
        query.data.items.map((item) => (
          <div key={item.id} className="cc-approval">
            <div className="text-[13px] font-medium">{item.title}</div>
            {/* The engine label is the backend's (SPEC-BE-020); items of no engine
                (reply, plan, action) show only the time rather than a guessed label. */}
            <div className="mb-2 mt-1 flex flex-wrap items-center gap-1.5 text-[11.5px] text-muted">
              {item.engine && <span className="badge badge-neutral">{item.engine}</span>}
              {ago(item.requested_at)}
            </div>
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
      </>
      )}
    </aside>
  );
}
