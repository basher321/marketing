"use client";

import { useQuery } from "@tanstack/react-query";

import {
  fetchCampaignMetrics,
  fetchCtr7d,
  fetchScheduledPostCount,
  marketingKeys,
} from "@/lib/api/marketing";

// Rounds to the mockup's one decimal ("3.8x", "2.4%") without padding, so an
// exact 0 renders as "0" rather than "0.0".
function oneDecimal(value: number): string {
  return String(Number(value.toFixed(1)));
}

type CardState = { isPending: boolean; isError: boolean };

function Card({
  title,
  state,
  value,
}: {
  title: string;
  state: CardState;
  value: () => string;
}) {
  return (
    <div className="card" aria-busy={state.isPending}>
      <p className="card-title">{title}</p>
      {state.isPending ? (
        <p className="card-value text-muted">…</p>
      ) : state.isError ? (
        <>
          <p className="card-value text-muted">—</p>
          <p className="mt-1.5 text-xs text-danger" role="alert">
            Failed to load
          </p>
        </>
      ) : (
        <p className="card-value">{value()}</p>
      )}
    </div>
  );
}

// Marketing page top row (SPEC-FE-012): the mockup's .grid-4 (4 columns, 16px
// gap, one column at <=900px) with the 4 cards in mockup order. Each card
// renders its own loading/error state from its own query; Active Campaigns and
// Avg. ROAS read the same query because the backend returns both numbers in one
// response (SPEC-BE-009).
export default function SummaryCards() {
  const campaign = useQuery({
    queryKey: marketingKeys.campaignMetrics,
    queryFn: fetchCampaignMetrics,
  });
  const posts = useQuery({
    queryKey: marketingKeys.scheduledPostCount,
    queryFn: fetchScheduledPostCount,
  });
  const ctr = useQuery({ queryKey: marketingKeys.ctr7d, queryFn: fetchCtr7d });

  return (
    <div className="grid grid-cols-4 gap-4 max-[900px]:grid-cols-1">
      <Card
        title="Active Campaigns"
        state={campaign}
        value={() => String(campaign.data!.active_campaigns)}
      />
      <Card
        title="Scheduled Posts"
        state={posts}
        value={() => String(posts.data!.pending)}
      />
      {/* No delta line (no week-over-week data). ROAS and CTR come from imported
          Meta results (SPEC-BE-056); "—" when nothing was imported (SPEC-FE-042). */}
      <Card
        title="Avg. ROAS"
        state={campaign}
        value={() => (campaign.data!.avg_roas === null ? "—" : `${oneDecimal(campaign.data!.avg_roas)}x`)}
      />
      <Card
        title="CTR (7d)"
        state={ctr}
        value={() => (ctr.data!.ctr_7d_pct === null ? "—" : `${oneDecimal(ctr.data!.ctr_7d_pct)}%`)}
      />
    </div>
  );
}
