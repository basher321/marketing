"use client";

import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { analyticsKeys, fetchOrderMetrics } from "@/lib/api/analytics";
import { conversationKeys, fetchConversations } from "@/lib/api/conversations";
import { dashboardKeys, fetchAdSpendSummary, fetchRevenueSummary } from "@/lib/api/dashboard";
import type { InboxStatus } from "@/lib/types/conversations";
import { useCompanyCurrency } from "@/hooks/use-tenant";

import { money, oneDecimal, trend } from "./format";

// Inbox statuses where the customer is still waiting for a reply to go out:
// no reply yet (new), a draft awaiting approval (draft_ready), or handed to a
// human (escalated). Derived from the real inbox_status (SPEC-BE-007).
const AWAITING_REPLY: InboxStatus[] = ["new", "draft_ready", "escalated"];

function Card({
  title,
  isPending,
  isError,
  value,
  delta,
}: {
  title: string;
  isPending: boolean;
  isError: boolean;
  value: () => string;
  delta?: () => ReactNode;
}) {
  return (
    <div className="card" aria-busy={isPending}>
      <p className="card-title">{title}</p>
      {isPending ? (
        <p className="card-value text-muted">…</p>
      ) : isError ? (
        <>
          <p className="card-value text-muted">—</p>
          <p className="mt-1.5 text-xs text-danger" role="alert">
            Failed to load
          </p>
        </>
      ) : (
        <>
          <p className="card-value">{value()}</p>
          {delta?.()}
        </>
      )}
    </div>
  );
}

// Dashboard top row (SPEC-FE-005): 4 cards, each from its own real query.
export default function SummaryCards() {
  const currency = useCompanyCurrency();
  const revenue = useQuery({ queryKey: dashboardKeys.revenue24h, queryFn: fetchRevenueSummary });
  const orders = useQuery({ queryKey: analyticsKeys.orderMetrics, queryFn: fetchOrderMetrics });
  const adSpend = useQuery({ queryKey: dashboardKeys.adSpend24h, queryFn: fetchAdSpendSummary });
  const inbox = useQuery({ queryKey: conversationKeys.list, queryFn: fetchConversations });

  return (
    <div className="grid-4">
      <Card
        title="Revenue (24h)"
        isPending={revenue.isPending}
        isError={revenue.isError}
        value={() => money(revenue.data!.revenue_24h, currency)}
        delta={() => {
          const d = revenue.data!.revenue_24h_delta_pct;
          const t = trend(d);
          return (
            <p className={t.className}>
              {t.arrow}
              {oneDecimal(Math.abs(d))}% vs yesterday
            </p>
          );
        }}
      />
      {/* Value = orders placed in the last 24h. The mockup's "▲ 8 new since
          morning" line is omitted: no backend field counts orders since the
          start of the local day. */}
      <Card
        title="Orders"
        isPending={orders.isPending}
        isError={orders.isError}
        value={() => orders.data!.last_24h.toLocaleString("en-US")}
      />
      {/* "ROAS {x}x" comes from the same response (SPEC-BE-019 reuses SPEC-BE-009's
          value). No ROAS change exists, so the line carries no arrow. */}
      <Card
        title="Ad Spend"
        isPending={adSpend.isPending}
        isError={adSpend.isError}
        value={() => money(adSpend.data!.ad_spend_24h, currency)}
        delta={() => <p className="card-delta">ROAS {adSpend.data!.avg_roas === null ? "—" : `${oneDecimal(adSpend.data!.avg_roas)}x`}</p>}
      />
      <Card
        title="Open Conversations"
        isPending={inbox.isPending}
        isError={inbox.isError}
        value={() => String(inbox.data!.count)}
        delta={() => {
          const waiting = inbox.data!.items.filter((i) => AWAITING_REPLY.includes(i.inbox_status)).length;
          return <p className="card-delta">{waiting} awaiting reply</p>;
        }}
      />
    </div>
  );
}
