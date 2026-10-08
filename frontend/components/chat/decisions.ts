"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";

import { approvalKeys } from "@/lib/api/approvals";
import { dashboardKeys } from "@/lib/api/dashboard";

export type Decision = "pending" | "approved" | "rejected";
type DecisionMap = Record<string, Decision>;

/**
 * The shared approval_id -> decision map (approvalKeys.decisions), filled only
 * from real decision responses, so the chat plan card (SPEC-FE-009) and the
 * Pending Approvals panel (SPEC-FE-010) never disagree about one item. It has no
 * server fetch of its own (enabled: false); it's written with setQueryData.
 */
export function useDecisions(): DecisionMap {
  const { data } = useQuery<DecisionMap>({
    queryKey: approvalKeys.decisions,
    queryFn: () => ({}),
    initialData: {},
    staleTime: Infinity,
    enabled: false,
  });
  return data;
}

/** Record real decisions, then refetch the pending list and the Dashboard's per-engine counts. */
export function useRecordDecisions(): (decided: Record<string, Decision>) => void {
  const queryClient = useQueryClient();
  return (decided) => {
    queryClient.setQueryData<DecisionMap>(approvalKeys.decisions, (old) => ({ ...(old ?? {}), ...decided }));
    void queryClient.invalidateQueries({ queryKey: approvalKeys.pending });
    void queryClient.invalidateQueries({ queryKey: dashboardKeys.pendingCounts });
  };
}
