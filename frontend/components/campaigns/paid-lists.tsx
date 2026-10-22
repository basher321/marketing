"use client";

import Link from "next/link";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";

import { errorText } from "@/components/campaigns/builder/tree";
import { fetchAds, fetchAdSets, paidKeys, setPaidStatus } from "@/lib/api/paid";
import { formatMoney } from "@/lib/format/money";
import type { RangeKey } from "@/lib/types/analytics";
import { PAID_PLATFORM_LABEL, type PaidListQuery, type PaidPlatform, type PaidResults } from "@/lib/types/paid";
import { formatNumber } from "@/lib/format/number";

const PAGE_SIZE = 50;
const STATUSES = ["draft", "scheduled", "running", "paused", "completed", "failed"];
const STATUS_CLASS: Record<string, string> = {
  running: "badge badge-success",
  scheduled: "badge badge-neutral",
  paused: "badge badge-warn",
  failed: "badge badge-danger",
  draft: "badge badge-neutral",
};
const PER_CAMPAIGN = "This platform reports results per campaign.";

// Ad Sets and Ads across every campaign (SPEC-FE-051 / SPEC-BE-079). All data
// and every Pause/Resume goes through the backend; nothing is simulated.

function useDebounced(value: string, ms = 300): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

function StatusCell({ status, effective, extra }: { status: string; effective: string | null; extra?: string | null }) {
  return (
    <>
      <span className={STATUS_CLASS[status] ?? "badge badge-neutral"}>{status}</span>
      {effective && !["ACTIVE", "PAUSED"].includes(effective) && (
        <span className="ml-1 text-xs text-muted">{effective.replace(/_/g, " ").toLowerCase()}</span>
      )}
      {extra && (
        <div className="max-w-[220px] truncate text-xs text-danger" title={extra}>
          {extra}
        </div>
      )}
    </>
  );
}

function ResultCells({ r, currency }: { r: PaidResults; currency: string }) {
  const title = r.results_level === "campaign" ? PER_CAMPAIGN : r.spend === null ? "No imported results in this period" : undefined;
  return (
    <>
      <td title={title}>{r.spend === null ? "—" : formatMoney(r.spend, currency)}</td>
      <td title={title}>{r.ctr === null ? "—" : `${formatNumber(r.ctr)}%`}</td>
    </>
  );
}

function PauseResume({ level, id, status }: { level: "ad-sets" | "ads"; id: string; status: string }) {
  const queryClient = useQueryClient();
  const resume = status === "paused";
  const allowed = resume || status === "running" || status === "scheduled";
  const toggle = useMutation({
    mutationFn: () => setPaidStatus(level, id, resume),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: paidKeys.all }),
  });
  if (!allowed) return null;
  return (
    <>
      <button type="button" className="btn btn-secondary btn-sm" disabled={toggle.isPending} onClick={() => toggle.mutate()}>
        {toggle.isPending ? "…" : resume ? "Resume" : "Pause"}
      </button>
      {toggle.isError && (
        <div className="max-w-[220px] text-xs text-danger" role="alert">
          {errorText(toggle.error)}
        </div>
      )}
    </>
  );
}

function Filters({
  platforms,
  platform,
  setPlatform,
  status,
  setStatus,
  search,
  setSearch,
  chips,
}: {
  platforms: string[];
  platform: string;
  setPlatform: (v: string) => void;
  status: string;
  setStatus: (v: string) => void;
  search: string;
  setSearch: (v: string) => void;
  chips: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 p-4">
      <select aria-label="Platform" value={platform} onChange={(e) => setPlatform(e.target.value)}>
        <option value="">All platforms</option>
        {platforms.map((p) => (
          <option key={p} value={p}>
            {PAID_PLATFORM_LABEL[p as PaidPlatform] ?? p}
          </option>
        ))}
      </select>
      <select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
        <option value="">All statuses</option>
        {STATUSES.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
      <input type="search" aria-label="Search by name" placeholder="Search by name" value={search} maxLength={100} onChange={(e) => setSearch(e.target.value)} />
      {chips}
    </div>
  );
}

function Pager({ page, count, setPage }: { page: number; count: number; setPage: (p: number) => void }) {
  if (count <= PAGE_SIZE) return null;
  const from = (page - 1) * PAGE_SIZE + 1;
  const to = Math.min(page * PAGE_SIZE, count);
  return (
    <div className="flex items-center justify-end gap-2 p-4 text-[13px]">
      <span className="text-muted">
        {from}–{to} of {count}
      </span>
      <button type="button" className="btn btn-secondary btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
        Previous
      </button>
      <button type="button" className="btn btn-secondary btn-sm" disabled={to >= count} onClick={() => setPage(page + 1)}>
        Next
      </button>
    </div>
  );
}

// The platform filter offers every platform the company can have rows on.
const ALL_PLATFORMS = Object.keys(PAID_PLATFORM_LABEL);

function useListState(range: RangeKey, scope: { campaign_id?: string; ad_set_id?: string }) {
  const [platform, setPlatform] = useState("");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const q = useDebounced(search.trim());
  useEffect(() => setPage(1), [platform, status, q, range, scope.campaign_id, scope.ad_set_id]);
  const query: PaidListQuery = { platform, status, q, range, page, page_size: PAGE_SIZE, ...scope };
  return { platform, setPlatform, status, setStatus, search, setSearch, page, setPage, query };
}

function Chip({ label, href }: { label: string; href: string }) {
  return (
    <span className="badge badge-neutral">
      {label}{" "}
      <Link href={href} className="ml-1 text-inherit no-underline" aria-label={`Clear ${label}`}>
        ✕
      </Link>
    </span>
  );
}

function budgetText(budget: number | null, type: string | null, currency: string): string {
  if (type === "campaign") return "campaign budget";
  if (budget === null) return "—";
  return `${formatMoney(budget, currency)}${type === "lifetime" ? " lifetime" : "/day"}`;
}

function schedule(start: string | null, end: string | null): string {
  if (!start && !end) return "—";
  const d = (v: string | null) => (v ? new Date(v).toLocaleDateString() : "…");
  return `${d(start)} → ${end ? d(end) : "ongoing"}`;
}

export function AdSetsList({ range, campaignId }: { range: RangeKey; campaignId: string | null }) {
  const s = useListState(range, campaignId ? { campaign_id: campaignId } : {});
  const list = useQuery({ queryKey: paidKeys.adSets(s.query), queryFn: () => fetchAdSets(s.query), placeholderData: keepPreviousData });
  return (
    <div className="card" style={{ padding: 0 }}>
      <Filters
        platforms={ALL_PLATFORMS}
        platform={s.platform}
        setPlatform={s.setPlatform}
        status={s.status}
        setStatus={s.setStatus}
        search={s.search}
        setSearch={s.setSearch}
        chips={campaignId && <Chip label="One campaign" href="/marketing/paid?tab=ad-sets" />}
      />
      {list.isPending ? (
        <p className="m-0 px-4 pb-4 text-[13px] text-muted">Loading…</p>
      ) : list.isError ? (
        <p className="m-0 px-4 pb-4 text-[13px] text-danger">{errorText(list.error)}</p>
      ) : list.data.items.length === 0 ? (
        <p className="m-0 px-4 pb-4 text-[13px] text-muted">
          No ad sets yet. <Link href="/marketing/paid/ad-manager" className="text-accent underline">Create a campaign</Link> to add one.
        </p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table data-testid="ad-sets-table">
              <thead>
                <tr>
                  <th>Ad set</th>
                  <th>Platform</th>
                  <th>Status</th>
                  <th>Budget</th>
                  <th>Schedule</th>
                  <th>Performance goal</th>
                  <th>Ads</th>
                  <th>Spend</th>
                  <th>CTR</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((g) => (
                  <tr key={g.id}>
                    <td>
                      <div className="font-medium">{g.name}</div>
                      <div className="text-xs text-muted">{g.campaign_name}</div>
                    </td>
                    <td>{PAID_PLATFORM_LABEL[g.platform]}</td>
                    <td>
                      <StatusCell status={g.status} effective={g.effective_status} extra={g.last_error} />
                    </td>
                    <td className="whitespace-nowrap">{budgetText(g.budget, g.budget_type, g.currency)}</td>
                    <td className="whitespace-nowrap text-xs">{schedule(g.starts_at, g.ends_at)}</td>
                    <td className="text-xs">{g.performance_goal ? g.performance_goal.replace(/_/g, " ").toLowerCase() : "—"}</td>
                    <td>
                      <Link className="text-accent underline" href={`/marketing/paid?tab=ads&ad_set=${g.id}`}>
                        {g.ads_count}
                      </Link>
                    </td>
                    <ResultCells r={g} currency={g.currency} />
                    <td className="whitespace-nowrap">
                      <div className="flex flex-wrap items-start gap-1">
                        {g.platform !== "wizard" && (
                          <Link className="btn btn-secondary btn-sm no-underline" href={`/marketing/paid/${g.campaign_id}/edit`}>
                            Open
                          </Link>
                        )}
                        {g.platform !== "wizard" && <PauseResume level="ad-sets" id={g.id} status={g.status} />}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager page={s.page} count={list.data.count} setPage={s.setPage} />
        </>
      )}
    </div>
  );
}

export function AdsList({ range, campaignId, adSetId }: { range: RangeKey; campaignId: string | null; adSetId: string | null }) {
  const scope: { campaign_id?: string; ad_set_id?: string } = {};
  if (campaignId) scope.campaign_id = campaignId;
  if (adSetId) scope.ad_set_id = adSetId;
  const s = useListState(range, scope);
  const list = useQuery({ queryKey: paidKeys.ads(s.query), queryFn: () => fetchAds(s.query), placeholderData: keepPreviousData });
  return (
    <div className="card" style={{ padding: 0 }}>
      <Filters
        platforms={ALL_PLATFORMS}
        platform={s.platform}
        setPlatform={s.setPlatform}
        status={s.status}
        setStatus={s.setStatus}
        search={s.search}
        setSearch={s.setSearch}
        chips={
          <>
            {campaignId && <Chip label="One campaign" href="/marketing/paid?tab=ads" />}
            {adSetId && <Chip label="One ad set" href="/marketing/paid?tab=ads" />}
          </>
        }
      />
      {list.isPending ? (
        <p className="m-0 px-4 pb-4 text-[13px] text-muted">Loading…</p>
      ) : list.isError ? (
        <p className="m-0 px-4 pb-4 text-[13px] text-danger">{errorText(list.error)}</p>
      ) : list.data.items.length === 0 ? (
        <p className="m-0 px-4 pb-4 text-[13px] text-muted">
          No ads yet. <Link href="/marketing/paid/ad-manager" className="text-accent underline">Create a campaign</Link> to add one.
        </p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table data-testid="ads-table">
              <thead>
                <tr>
                  <th aria-label="Creative" />
                  <th>Ad</th>
                  <th>Platform</th>
                  <th>Status</th>
                  <th>CTA</th>
                  <th>Destination</th>
                  <th>Spend</th>
                  <th>CTR</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((a) => (
                  <tr key={a.id}>
                    <td>
                      {a.thumbnail_url ? (
                        <img src={a.thumbnail_url} alt="" className="h-10 w-10 rounded object-cover" />
                      ) : (
                        <div className="h-10 w-10 rounded bg-accent-soft" aria-hidden />
                      )}
                    </td>
                    <td className="max-w-[280px]">
                      <div className="font-medium">{a.name}</div>
                      {a.headline && <div className="truncate text-xs">{a.headline}</div>}
                      <div className="truncate text-xs text-muted">
                        {a.ad_set_name} › {a.campaign_name}
                      </div>
                    </td>
                    <td>{PAID_PLATFORM_LABEL[a.platform]}</td>
                    <td>
                      <StatusCell status={a.status} effective={a.effective_status} extra={a.review_feedback ?? a.last_error} />
                    </td>
                    <td className="text-xs">{a.call_to_action ? a.call_to_action.replace(/_/g, " ").toLowerCase() : "—"}</td>
                    <td className="max-w-[180px] truncate text-xs" title={a.destination_url ?? undefined}>
                      {a.destination_url ?? "—"}
                    </td>
                    <ResultCells r={a} currency={a.currency} />
                    <td className="whitespace-nowrap">
                      <div className="flex flex-wrap items-start gap-1">
                        {a.platform !== "wizard" && (
                          <Link className="btn btn-secondary btn-sm no-underline" href={`/marketing/paid/${a.campaign_id}/edit`}>
                            Open
                          </Link>
                        )}
                        {a.platform !== "wizard" && <PauseResume level="ads" id={a.id} status={a.status} />}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager page={s.page} count={list.data.count} setPage={s.setPage} />
        </>
      )}
    </div>
  );
}
