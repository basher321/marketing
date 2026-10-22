"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { analyticsKeys, fetchOrderMetrics } from "@/lib/api/analytics";
import { conversationKeys, fetchConversations } from "@/lib/api/conversations";
import {
  dashboardKeys,
  fetchAdSpendSummary,
  fetchCsMetrics,
  fetchLowStock,
  fetchPendingCounts,
} from "@/lib/api/dashboard";
import { fetchCampaignMetrics, fetchScheduledPostCount, marketingKeys } from "@/lib/api/marketing";
import { fetchWorkflows, workflowKeys } from "@/lib/api/workflows";
import { formatNumber } from "@/lib/format/number";


// One metric row with its own loading ("—") / error state, so one failed
// query never blanks its siblings (SPEC-FE-006 rule 9).
function Metric<T>({
  label,
  query,
  render,
}: {
  label: string;
  query: UseQueryResult<T>;
  render: (data: T) => string;
}) {
  return (
    <div className="engine-metric">
      <span className="engine-metric-label">{label}</span>
      {query.isPending ? (
        <b className="text-muted">—</b>
      ) : query.isError ? (
        <b className="text-danger" title={query.error.message}>
          !
        </b>
      ) : (
        <b>{render(query.data)}</b>
      )}
    </div>
  );
}

function EngineCard({ name, children }: { name: string; children: React.ReactNode }) {
  return (
    <div className="engine-card">
      <div className="engine-header">
        <div className="engine-name">{name}</div>
        {/* Intentionally static, exactly as the mockup: no backend computes an
            engine health/status value (pending a future engine-health spec). */}
        <span>
          <span className="status-dot" /> Active
        </span>
      </div>
      {children}
    </div>
  );
}

// "2m 14s" (mockup) from the backend's raw seconds; null (no data) -> "—".
function duration(seconds: number | null): string {
  if (seconds === null) return "—";
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

// Dashboard "Automation Engines" (SPEC-FE-006). Queries shared with the summary
// cards and other pages use the same key, so they are fetched once.
export default function EngineCards() {
  const workflows = useQuery({ queryKey: workflowKeys.list, queryFn: fetchWorkflows });
  const orders = useQuery({ queryKey: analyticsKeys.orderMetrics, queryFn: fetchOrderMetrics });
  const lowStock = useQuery({ queryKey: dashboardKeys.lowStock, queryFn: fetchLowStock });
  const pending = useQuery({ queryKey: dashboardKeys.pendingCounts, queryFn: fetchPendingCounts });
  const campaigns = useQuery({ queryKey: marketingKeys.campaignMetrics, queryFn: fetchCampaignMetrics });
  const posts = useQuery({ queryKey: marketingKeys.scheduledPostCount, queryFn: fetchScheduledPostCount });
  const adSpend = useQuery({ queryKey: dashboardKeys.adSpend24h, queryFn: fetchAdSpendSummary });
  const inbox = useQuery({ queryKey: conversationKeys.list, queryFn: fetchConversations });
  const cs = useQuery({ queryKey: dashboardKeys.csMetrics, queryFn: fetchCsMetrics });

  return (
    <div className="grid-3">
      <EngineCard name="E-Commerce">
        {/* Tenant-wide enabled workflows: workflows are not tagged by engine. */}
        <Metric label="Active workflows" query={workflows} render={(d) => String(d.filter((w) => w.status === "Enabled").length)} />
        <Metric label="Orders (24h)" query={orders} render={(d) => d.last_24h.toLocaleString("en-US")} />
        <Metric label="Low-stock alerts" query={lowStock} render={(d) => String(d.length)} />
        <Metric label="Pending approvals" query={pending} render={(d) => String(d.ecommerce)} />
      </EngineCard>
      <EngineCard name="Marketing">
        <Metric label="Active campaigns" query={campaigns} render={(d) => String(d.active_campaigns)} />
        <Metric label="Scheduled posts" query={posts} render={(d) => String(d.pending)} />
        {/* Same cached value as the Ad Spend card's ROAS line. */}
        <Metric label="Avg. ROAS" query={adSpend} render={(d) => (d.avg_roas === null ? "—" : `${formatNumber(d.avg_roas)}x`)} />
        <Metric label="Pending approvals" query={pending} render={(d) => String(d.marketing)} />
      </EngineCard>
      <EngineCard name="Customer Service">
        <Metric label="Open threads" query={inbox} render={(d) => String(d.count)} />
        <Metric label="Avg. response" query={cs} render={(d) => duration(d.avg_response_seconds)} />
        <Metric label="Deflection rate" query={cs} render={(d) => (d.deflection_rate_pct === null ? "—" : `${formatNumber(d.deflection_rate_pct)}%`)} />
        <Metric label="CSAT (7d)" query={cs} render={(d) => (d.csat_7d === null ? "—" : `${formatNumber(d.csat_7d)}/5`)} />
      </EngineCard>
    </div>
  );
}
