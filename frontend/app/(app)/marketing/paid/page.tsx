"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Suspense, useState } from "react";

import { newTabHref } from "@/hooks/use-new-tab";
import AdsReport from "@/components/analytics/ads-report";
import { AdSetsList, AdsList } from "@/components/campaigns/paid-lists";
import CampaignWizard from "@/components/campaigns/wizard";
import ZernioCampaigns from "@/components/zernio/campaigns";
import { aiCampaignKeys, fetchRuns } from "@/lib/api/ai-campaigns";
import { fetchDrafts } from "@/lib/api/campaigns";
import { fetchCampaigns } from "@/lib/api/marketing";
import { formatMoney } from "@/lib/format/money";
import type { RangeKey } from "@/lib/types/analytics";

const STATUS_CLASS: Record<string, string> = {
  running: "badge badge-success",
  scheduled: "badge badge-neutral",
  paused: "badge badge-warn",
  draft: "badge badge-neutral",
};

function money(amount: number, currency: string): string {
  return formatMoney(amount, currency);
}

// Paid Marketing (SPEC-FE-049; formerly /campaigns, SPEC-FE-039): live campaigns with Meta's own status, real spend
// and ROAS (SPEC-BE-056), ad sets and ads across campaigns (SPEC-FE-051), drafts and the Ads report. "+ New campaign" opens the Ads
// Manager-style builder. A legacy wizard draft (?draft=) still opens in the
// old wizard so nothing in progress is lost.
const RUN_STATUS: Record<string, string> = {
  queued: "starting",
  running: "working",
  needs_input: "needs your answer",
  ready_for_review: "ready for review",
  publishing: "publishing",
  awaiting_approval: "waiting for approval",
  published: "published",
  failed: "failed",
  cancelled: "discarded",
};

// AI runs (SPEC-FE-046): recent "Create with AI" runs and where each one is.
function AIRuns() {
  const runs = useQuery({ queryKey: aiCampaignKeys.list, queryFn: fetchRuns });
  return (
    <div className="card" style={{ padding: 0 }}>
      <div className="flex items-center justify-between p-4">
        <span className="font-semibold">AI runs</span>
        <Link href={newTabHref("/marketing/paid/ai/new")} target="_blank" rel="noopener" className="btn btn-sm">
          Create with AI
        </Link>
      </div>
      {runs.isPending ? (
        <p className="m-0 px-4 pb-4 text-[13px] text-muted">Loading…</p>
      ) : runs.isError ? (
        <p className="m-0 px-4 pb-4 text-[13px] text-danger">{runs.error.message}</p>
      ) : runs.data.items.length === 0 ? (
        <p className="m-0 px-4 pb-4 text-[13px] text-muted">No AI runs yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Brief</th>
              <th>Platforms</th>
              <th>Status</th>
              <th>Started</th>
              <th>AI cost</th>
              <th aria-label="Open" />
            </tr>
          </thead>
          <tbody>
            {runs.data.items.map((r) => (
              <tr key={r.id}>
                <td className="max-w-[340px] truncate" title={r.prompt}>
                  {r.prompt}
                </td>
                <td>{r.platforms.join(", ")}</td>
                <td>{RUN_STATUS[r.status] ?? r.status}</td>
                <td>{new Date(r.created_at).toLocaleString()}</td>
                <td>{(r.cost_cents / 100).toFixed(2)} USD</td>
                <td>
                  <Link className="text-accent underline" href={`/marketing/paid/ai/${r.id}`}>
                    Open
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function AIBadge({ show }: { show: boolean }) {
  return show ? (
    <span className="badge badge-neutral ml-1" title="Created with AI">
      AI
    </span>
  ) : null;
}

// Paid Marketing tabs (SPEC-FE-051): one tab per Ads Manager level, kept in ?tab=.
const TABS = [
  { key: "campaigns", label: "Campaigns" },
  { key: "ad-sets", label: "Ad Sets" },
  { key: "ads", label: "Ads" },
  { key: "drafts", label: "Drafts" },
  { key: "analytics", label: "Analytics" },
  { key: "ai", label: "AI runs" },
  { key: "zernio", label: "Zernio" }, // SPEC-FE-055
] as const;
type TabKey = (typeof TABS)[number]["key"];
const RANGES: { key: RangeKey; label: string }[] = [
  { key: "7d", label: "7 days" },
  { key: "30d", label: "30 days" },
  { key: "90d", label: "90 days" },
];

function RangePicker({ range, setRange }: { range: RangeKey; setRange: (r: RangeKey) => void }) {
  return (
    <div className="mb-4 flex items-center gap-1.5" role="group" aria-label="Date range">
      <span className="mr-1 text-[13px] text-muted">Range:</span>
      {RANGES.map((r) => (
        <button key={r.key} type="button" aria-pressed={range === r.key} className={range === r.key ? "btn btn-sm" : "btn btn-secondary btn-sm"} onClick={() => setRange(r.key)}>
          {r.label}
        </button>
      ))}
    </div>
  );
}

function CampaignList() {
  const params = useSearchParams();
  const raw = params.get("tab");
  const tab: TabKey = TABS.some((t) => t.key === raw) ? (raw as TabKey) : "campaigns";
  const [range, setRange] = useState<RangeKey>("30d");
  return (
    <>
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h1 className="m-0 mb-1 text-[22px] font-bold">Paid Marketing</h1>
          <p className="m-0 text-muted">Campaign → Ad set → Ad, published to the connected ad platforms.</p>
        </div>
        <Link href={newTabHref("/marketing/paid/ad-manager")} target="_blank" rel="noopener" className="btn">
          + New campaign
        </Link>
      </div>
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <Link key={t.key} role="tab" aria-selected={tab === t.key} className={tab === t.key ? "tab active" : "tab"} href={t.key === "campaigns" ? "/marketing/paid" : `/marketing/paid?tab=${t.key}`}>
            {t.label}
          </Link>
        ))}
      </div>
      {(tab === "ad-sets" || tab === "ads" || tab === "analytics" || tab === "zernio") && <RangePicker range={range} setRange={setRange} />}
      {tab === "zernio" && <ZernioCampaigns range={range} />}
      {tab === "ai" && <AIRuns />}
      {tab === "campaigns" && <LiveCampaigns />}
      {tab === "drafts" && <Drafts />}
      {tab === "ad-sets" && <AdSetsList range={range} campaignId={params.get("campaign")} />}
      {tab === "ads" && <AdsList range={range} campaignId={params.get("campaign")} adSetId={params.get("ad_set")} />}
      {tab === "analytics" && <AdsReport range={range} />}
    </>
  );
}

function LiveCampaigns() {
  const live = useQuery({ queryKey: ["marketing", "campaigns"], queryFn: fetchCampaigns });
  const runs = useQuery({ queryKey: aiCampaignKeys.list, queryFn: fetchRuns });
  const aiIds = new Set((runs.data?.items ?? []).flatMap((r) => r.campaign_ids));
  return (
      <div className="card mb-4" style={{ padding: 0 }}>
        <div className="p-4 font-semibold">Live campaigns</div>
        {live.isPending ? (
          <p className="m-0 px-4 pb-4 text-[13px] text-muted">Loading…</p>
        ) : live.isError ? (
          <p className="m-0 px-4 pb-4 text-[13px] text-danger">{live.error.message}</p>
        ) : live.data.length === 0 ? (
          <p className="m-0 px-4 pb-4 text-[13px] text-muted">No running, scheduled or paused campaigns.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Status</th>
                <th>Objective</th>
                <th>Budget</th>
                <th>Spent</th>
                <th>ROAS</th>
                <th aria-label="Open" />
              </tr>
            </thead>
            <tbody>
              {live.data.map((c) => (
                <tr key={c.id}>
                  <td>
                    {c.name}
                    <AIBadge show={aiIds.has(c.id)} />
                  </td>
                  <td>
                    <span className={STATUS_CLASS[c.status] ?? "badge badge-neutral"}>{c.status}</span>
                    {c.effective_status && c.effective_status !== "ACTIVE" && c.effective_status !== "PAUSED" && (
                      <span className="ml-1 text-xs text-muted">{c.effective_status.replace(/_/g, " ").toLowerCase()}</span>
                    )}
                  </td>
                  <td>{c.objective === "conversions" ? "sales" : c.objective.replace(/_/g, " ")}</td>
                  <td>{money(c.budget, c.currency)}</td>
                  <td>{money(c.spent, c.currency)}</td>
                  <td title={c.roas === null ? "No imported purchase value yet" : undefined}>{c.roas === null ? "—" : c.roas.toFixed(2)}</td>
                  <td className="whitespace-nowrap">
                    {c.builder ? (
                      <Link className="text-accent underline" href={`/marketing/paid/${c.id}/edit`}>
                        Open
                      </Link>
                    ) : (
                      <span className="text-xs text-muted">wizard campaign</span>
                    )}
                    <Link className="ml-3 text-accent underline" href={`/marketing/paid?tab=ad-sets&campaign=${c.id}`}>
                      Ad sets
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
  );
}

function Drafts() {
  const drafts = useQuery({ queryKey: ["campaigns", "drafts"], queryFn: fetchDrafts });
  const runs = useQuery({ queryKey: aiCampaignKeys.list, queryFn: fetchRuns });
  const aiIds = new Set((runs.data?.items ?? []).flatMap((r) => r.campaign_ids));
  return (
      <div className="card" style={{ padding: 0 }}>
        <div className="p-4 font-semibold">Drafts</div>
        {drafts.isPending ? (
          <p className="m-0 px-4 pb-4 text-[13px] text-muted">Loading…</p>
        ) : drafts.isError ? (
          <p className="m-0 px-4 pb-4 text-[13px] text-danger">{drafts.error.message}</p>
        ) : drafts.data.length === 0 ? (
          <p className="m-0 px-4 pb-4 text-[13px] text-muted">No drafts.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Objective</th>
                <th>Waiting for approval</th>
                <th aria-label="Open" />
              </tr>
            </thead>
            <tbody>
              {drafts.data.map((d) => (
                <tr key={d.id}>
                  <td>
                    {d.name}
                    <AIBadge show={aiIds.has(d.id)} />
                  </td>
                  <td>{d.objective === "conversions" ? "sales" : d.objective.replace(/_/g, " ")}</td>
                  <td>{d.pending_approval_id ? "Yes" : "—"}</td>
                  <td>
                    <Link className="text-accent underline" href={d.builder ? `/marketing/paid/${d.id}/edit` : `/marketing/paid?draft=${d.id}`}>
                      Continue
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
  );
}

function CampaignsRouter() {
  const params = useSearchParams();
  return params.get("draft") ? <CampaignWizard /> : <CampaignList />;
}

export default function CampaignsPage() {
  return (
    <Suspense fallback={<p className="text-[13px] text-muted">Loading…</p>}>
      <CampaignsRouter />
    </Suspense>
  );
}
