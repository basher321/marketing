"use client";

import { useQuery } from "@tanstack/react-query";

import { dashboardKeys, fetchRecentActivity } from "@/lib/api/dashboard";
import type { ActivityItem } from "@/lib/types/dashboard";

// Dot color from the backend's real `kind` (SPEC-BE-022): success -> green,
// warning -> amber, info -> the default accent (as the mockup's plain dots).
const DOT_COLORS: Record<ActivityItem["kind"], string | undefined> = {
  success: "var(--success)",
  warning: "var(--warn)",
  info: undefined,
};

// "2 min ago" / "1 hour ago" / "3 hours ago" (mockup granularity).
function relativeTime(iso: string, now: number): string {
  const minutes = Math.max(0, Math.floor((now - new Date(iso).getTime()) / 60_000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours} hour${hours === 1 ? "" : "s"} ago`;
}

// Dashboard "Recent Activity" (SPEC-FE-007). Items render in the backend's
// order, which SPEC-BE-022 guarantees is most recent first. Message text is
// plain: the API carries no emphasis markers, so the mockup's bolded entities
// can't be reproduced without inventing which words to bold.
export default function RecentActivity() {
  const query = useQuery({ queryKey: dashboardKeys.activity, queryFn: fetchRecentActivity });
  const now = Date.now();

  return (
    <div className="card">
      {query.isPending ? (
        <p className="m-0 text-[13px] text-muted">Loading activity…</p>
      ) : query.isError ? (
        <p className="m-0 text-[13px] text-danger" role="alert">
          Failed to load activity: {query.error.message}
        </p>
      ) : query.data.items.length === 0 ? (
        <p className="m-0 text-[13px] text-muted">No recent activity</p>
      ) : (
        query.data.items.map((item) => (
          <div key={item.id} className="timeline-item">
            <div className="timeline-dot" style={DOT_COLORS[item.kind] ? { background: DOT_COLORS[item.kind] } : undefined} />
            <div>
              <div className="timeline-time">{relativeTime(item.occurred_at, now)}</div>
              <div className="timeline-body">{item.message}</div>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
