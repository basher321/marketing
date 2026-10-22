"use client";

import { useQuery } from "@tanstack/react-query";

import { analyticsKeys, fetchOrderMetrics, fetchSalesSummary } from "@/lib/api/analytics";
import { useCompanyCurrency } from "@/hooks/use-tenant";
import { formatMoney } from "@/lib/format/money";
import { formatNumber } from "@/lib/format/number";

// Money is shown as whole units with thousands separators, like the mockup's
// "312,480". The analytics response carries no currency, so the company
// currency's symbol is used (SPEC-FE-048); with none loaded yet, just the number.
function money(value: number, currency: string | null): string {
  return formatMoney(value, currency, { whole: true });
}

// Delta arrow/color follow the sign of the real comparison value (SPEC-FE-019
// rule 2): > 0 -> ".up ▲", < 0 -> ".down ▼", 0 -> no arrow and no color.
// The magnitude is shown without its sign, as the mockup does ("▼ 0.3%").
function Delta({ value, suffix }: { value: number; suffix: string }) {
  const text = `${formatNumber(Math.abs(value))}${suffix}`;
  if (value > 0) return <p className="card-delta up">▲ {text}</p>;
  if (value < 0) return <p className="card-delta down">▼ {text}</p>;
  return <p className="card-delta text-muted">{text}</p>;
}

type CardState = { isPending: boolean; isError: boolean };

function Card({
  title,
  state,
  value,
  delta,
}: {
  title: string;
  state: CardState;
  value: () => string;
  delta?: () => { value: number; suffix: string };
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
        <>
          <p className="card-value">{value()}</p>
          {delta && <Delta {...delta()} />}
        </>
      )}
    </div>
  );
}

// Analytics Sales tab summary row (SPEC-FE-019): the mockup's .grid-4 (4
// columns, 16px gap, one column at <=900px) with the 4 cards in mockup order.
export default function SalesSummaryCards() {
  const currency = useCompanyCurrency();
  const sales = useQuery({ queryKey: analyticsKeys.sales, queryFn: fetchSalesSummary });
  const orders = useQuery({ queryKey: analyticsKeys.orderMetrics, queryFn: fetchOrderMetrics });

  return (
    <div className="grid grid-cols-4 gap-4 max-[900px]:grid-cols-1">
      <Card
        title="Revenue (7d)"
        state={sales}
        value={() => money(sales.data!.revenue_7d, currency)}
        delta={() => ({ value: sales.data!.revenue_7d_delta_pct, suffix: "%" })}
      />
      {/* Value and comparison both from GET /orders/metrics (last_7d and
          last_7d_delta_pct), the same SPEC-BE-006 computation behind
          SalesSummary.orders_7d, so the count and its delta come from one response. */}
      <Card
        title="Orders (7d)"
        state={orders}
        value={() => String(orders.data!.last_7d)}
        delta={() => ({ value: orders.data!.last_7d_delta_pct, suffix: "%" })}
      />
      {/* No delta line: no backend response carries a previous-period AOV, so the
          mockup's "▲ ৳12" comparison cannot be reproduced from real data. */}
      <Card title="AOV" state={sales} value={() => money(sales.data!.aov_7d, currency)} />
      {/* The delta is a change in percentage points (refund_rate_7d_delta_pp),
          shown with the mockup's "%" suffix. */}
      <Card
        title="Refund Rate"
        state={sales}
        value={() => `${formatNumber(sales.data!.refund_rate_7d_pct)}%`}
        delta={() => ({ value: sales.data!.refund_rate_7d_delta_pp, suffix: "%" })}
      />
    </div>
  );
}
