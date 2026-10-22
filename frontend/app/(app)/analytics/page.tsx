"use client";

import { useEffect, useState } from "react";

import AdsReport from "@/components/analytics/ads-report";
import EngagementReport from "@/components/analytics/engagement-report";
import ProfitLoss from "@/components/analytics/profit-loss";
import RevenueChart from "@/components/analytics/revenue-chart";
import SalesSummaryCards from "@/components/analytics/sales-summary";
import ServiceReport from "@/components/analytics/service-report";
import TopProductsTable from "@/components/analytics/top-products-table";
import type { RangeKey } from "@/lib/types/analytics";

// SPEC-FE-074 adds Profit & Loss first (?tab=profit-loss links open it).
const TABS = ["Profit & Loss", "Sales", "Ads", "Engagement", "Customer Service"] as const;
type Tab = (typeof TABS)[number];

const RANGES: { key: RangeKey; label: string }[] = [
  { key: "7d", label: "7 days" },
  { key: "30d", label: "30 days" },
  { key: "90d", label: "90 days" },
];

// Title and subtitle copied from the reference mockup (SPEC-FE-002), plus the
// Sales tab's summary cards and Revenue by Day chart (SPEC-FE-019) and Top
// Products table (SPEC-FE-020). Ads, Engagement and Customer Service
// (SPEC-FE-035) have no mockup markup; they share one range selector
// (default 30 days). The Sales tab keeps its fixed 7-day view.
export default function AnalyticsPage() {
  const [tab, setTab] = useState<Tab>("Profit & Loss");
  const [range, setRange] = useState<RangeKey>("30d");
  useEffect(() => {
    const wanted = new URLSearchParams(window.location.search).get("tab");
    const match = TABS.find((t) => t.toLowerCase().replace(/ & | /g, "-") === wanted);
    if (match) setTab(match);
  }, []);

  return (
    <>
      <h1 className="page-title">{"Analytics"}</h1>
      <p className="page-subtitle">
        {"Real-time performance across sales, ads, engagement, and service."}
      </p>
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <div
            key={t}
            role="tab"
            aria-selected={tab === t}
            tabIndex={0}
            className={tab === t ? "tab active" : "tab"}
            onClick={() => setTab(t)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") setTab(t);
            }}
          >
            {t}
          </div>
        ))}
      </div>
      {tab !== "Sales" && tab !== "Profit & Loss" && (
        <div className="mb-4 flex items-center gap-1.5" role="group" aria-label="Date range">
          <span className="mr-1 text-[13px] text-muted">Range:</span>
          {RANGES.map((r) => (
            <button
              key={r.key}
              type="button"
              aria-pressed={range === r.key}
              className={range === r.key ? "btn btn-sm" : "btn btn-secondary btn-sm"}
              onClick={() => setRange(r.key)}
            >
              {r.label}
            </button>
          ))}
        </div>
      )}
      {tab === "Profit & Loss" && <ProfitLoss />}
      {tab === "Sales" && (
        <>
          <SalesSummaryCards />
          <RevenueChart />
          <TopProductsTable />
        </>
      )}
      {tab === "Ads" && <AdsReport range={range} />}
      {tab === "Engagement" && <EngagementReport range={range} />}
      {tab === "Customer Service" && <ServiceReport range={range} />}
    </>
  );
}
