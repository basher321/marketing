"use client";

import { useQuery } from "@tanstack/react-query";

import { analyticsKeys, fetchSalesSummary } from "@/lib/api/analytics";
import type { DailyRevenue } from "@/lib/types/analytics";

// "Sun".."Sat" for a backend date. The dates are UTC calendar days, so they
// are read and labelled in UTC (a local-time parse could shift the weekday).
function weekday(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00Z`).toLocaleDateString("en-US", {
    weekday: "short",
    timeZone: "UTC",
  });
}

// Bar height as a % of the series maximum. When every day is 0 there is no
// maximum to scale against; bars render at 0% (the .bar min-height keeps a
// 4px stub) instead of full height, so a zero-revenue week does not look like
// a full one. Equal non-zero days all render at 100%.
function heightPct(value: number, max: number): number {
  return max > 0 ? (value / max) * 100 : 0;
}

function Chart({ days }: { days: DailyRevenue[] }) {
  const max = Math.max(...days.map((d) => d.revenue));
  // The backend returns today (UTC) as the last entry, oldest -> newest.
  const todayIndex = days.length - 1;
  // Only today's bar is highlighted (chart-3). The mockup's chart-2 highlight on
  // two other bars has no rule behind it, so it is not reproduced.
  return (
    <>
      <div className="chart">
        {days.map((d, i) => (
          <div
            key={d.date}
            className={
              i === todayIndex ? "bar bg-gradient-to-b from-chart-3 to-emerald-300" : "bar"
            }
            style={{ height: `${heightPct(d.revenue, max)}%` }}
          />
        ))}
      </div>
      <div className="chart-legend">
        {days.map((d, i) => (
          <span key={d.date}>
            <span className={`legend-dot ${i === todayIndex ? "bg-chart-3" : "bg-chart-1"}`} />
            {i === todayIndex ? `${weekday(d.date)} (today)` : weekday(d.date)}
          </span>
        ))}
      </div>
    </>
  );
}

// Analytics Sales tab "Revenue by Day" (SPEC-FE-019), from the real
// revenue_by_day series in GET /api/v1/analytics/sales (shared query with the
// summary cards, so one request serves both).
export default function RevenueChart() {
  const sales = useQuery({ queryKey: analyticsKeys.sales, queryFn: fetchSalesSummary });

  return (
    <>
      <h2 className="section-title">
        Revenue by Day{" "}
        {/* Non-functional by design: chart narration is deferred - no backend
            narration endpoint exists yet, so this button has no handler. */}
        <button type="button" className="btn btn-ghost">
          Explain this ⓘ
        </button>
      </h2>
      <div className="card" aria-busy={sales.isPending}>
        {sales.isPending ? (
          <p className="m-0 text-[13px] text-muted">Loading…</p>
        ) : sales.isError ? (
          <p className="m-0 text-[13px] text-danger" role="alert">
            Failed to load revenue: {sales.error.message}
          </p>
        ) : sales.data.revenue_by_day.length === 0 ? (
          <p className="m-0 text-[13px] text-muted">Daily revenue breakdown not yet available</p>
        ) : (
          <Chart days={sales.data.revenue_by_day} />
        )}
      </div>
    </>
  );
}
