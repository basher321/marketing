"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Fragment, useState } from "react";

import { errorText } from "@/components/organic/shared";
import { deleteCampaign, fetchAnalytics, fetchCampaigns, setStatus, updateCampaign, zernioKeys } from "@/lib/api/zernio";
import { ApiError } from "@/lib/types/common";
import { formatMoney } from "@/lib/format/money";
import type { ZCampaignNode, ZMetrics, ZRange } from "@/lib/types/zernio";

// Paid Marketing › Zernio tab (SPEC-FE-055): this company's Zernio campaigns,
// read live (campaign → ad sets → ads) with Zernio's own numbers. A number
// Zernio didn't report shows "—", never an estimate.

const PLATFORMS: [string, string][] = [
  ["", "All platforms"],
  ["facebook", "Facebook"],
  ["instagram", "Instagram"],
  ["tiktok", "TikTok"],
  ["linkedin", "LinkedIn"],
  ["pinterest", "Pinterest"],
  ["twitter", "X (Twitter)"],
  ["googleads", "Google Ads"],
];
const STATUSES = ["", "active", "paused", "pending_review", "rejected", "completed", "cancelled", "error"];
const BADGE: Record<string, string> = {
  active: "badge badge-success",
  paused: "badge badge-warn",
  pending_review: "badge badge-neutral",
  rejected: "badge badge-danger",
  error: "badge badge-danger",
  completed: "badge badge-neutral",
  cancelled: "badge badge-neutral",
};
const TREE_LABEL: Record<string, string> = { google: "Google Ads", twitter: "X", facebook: "Facebook", instagram: "Instagram", tiktok: "TikTok", linkedin: "LinkedIn", pinterest: "Pinterest", openai: "ChatGPT" };

const dash = "—";
const num = (v: number | null | undefined) => (v === null || v === undefined ? dash : v.toLocaleString());
const pct = (v: number | null | undefined) => (v === null || v === undefined ? dash : `${v.toFixed(2)}%`);
const roas = (v: number | null | undefined) => (v === null || v === undefined ? dash : `${v.toFixed(2)}×`);
const money = (v: number | null | undefined, c: string | null) => (v === null || v === undefined ? dash : formatMoney(v, c));

function StatusPill({ status }: { status: string | null }) {
  return status ? <span className={BADGE[status] ?? "badge badge-neutral"}>{status.replace(/_/g, " ")}</span> : <span className="text-muted">{dash}</span>;
}

function MetricCells({ m, currency }: { m: ZMetrics | null; currency: string | null }) {
  return (
    <>
      <td>{money(m?.spend, currency)}</td>
      <td>{num(m?.impressions)}</td>
      <td>{num(m?.clicks)}</td>
      <td>{pct(m?.ctr)}</td>
      <td>{num(m?.conversions)}</td>
      <td>{roas(m?.roas)}</td>
    </>
  );
}

function Toggle({ level, id, status, onDone }: { level: "campaigns" | "ad-sets" | "ads"; id: string; status: string | null; onDone: (msg: string) => void }) {
  const qc = useQueryClient();
  const paused = status === "paused";
  const m = useMutation({
    mutationFn: () => setStatus(level, id, paused ? "resume" : "pause"),
    onSuccess: (r) => {
      onDone(r.message);
      void qc.invalidateQueries({ queryKey: zernioKeys.all });
    },
    onError: (e) => onDone(errorText(e)),
  });
  if (status !== "active" && status !== "paused") return null;
  return (
    <button type="button" className="btn btn-secondary btn-sm" disabled={m.isPending} onClick={() => m.mutate()}>
      {m.isPending ? "…" : paused ? "Resume" : "Pause"}
    </button>
  );
}

function EditForm({ c, onClose, onDone }: { c: ZCampaignNode; onClose: () => void; onDone: (msg: string) => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState(c.name ?? "");
  const [amount, setAmount] = useState(c.budget?.amount != null ? String(c.budget.amount) : "");
  const [type, setType] = useState<"daily" | "lifetime">(c.budget?.type === "lifetime" ? "lifetime" : "daily");
  const save = useMutation({
    mutationFn: () =>
      updateCampaign(c.id, {
        ...(name.trim() && name.trim() !== c.name ? { name: name.trim() } : {}),
        ...(amount && Number(amount) !== c.budget?.amount ? { budget: { amount, type } } : {}),
      }),
    onSuccess: () => {
      onDone("Saved.");
      onClose();
      void qc.invalidateQueries({ queryKey: zernioKeys.all });
    },
  });
  return (
    <div className="flex flex-wrap items-end gap-2 p-2 text-[13px]">
      <label>
        <span className="block text-xs text-muted">Name</span>
        <input value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label>
        <span className="block text-xs text-muted">Budget ({c.currency ?? ""})</span>
        <input type="number" min="0" step="0.01" className="w-32" value={amount} onChange={(e) => setAmount(e.target.value)} />
      </label>
      <select value={type} onChange={(e) => setType(e.target.value as "daily" | "lifetime")} aria-label="Budget type">
        <option value="daily">daily</option>
        <option value="lifetime">lifetime</option>
      </select>
      <button type="button" className="btn btn-sm" disabled={save.isPending} onClick={() => save.mutate()}>
        {save.isPending ? "Saving…" : "Save"}
      </button>
      <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
        Cancel
      </button>
      {save.isError && <span className="w-full text-xs text-danger">{errorText(save.error)}</span>}
    </div>
  );
}

function Analytics({ c, range, onClose }: { c: ZCampaignNode; range: ZRange; onClose: () => void }) {
  const meta = c.platform === "facebook" || c.platform === "instagram";
  const a = useQuery({ queryKey: zernioKeys.analytics(c.id, range), queryFn: () => fetchAnalytics(c.id, range, meta ? "age,gender,country" : null) });
  const max = Math.max(1, ...(a.data?.daily ?? []).map((d) => d.spend ?? 0));
  return (
    <div className="p-3" data-testid="zernio-analytics">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-semibold">Results · {c.name ?? c.id}</span>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
          Close
        </button>
      </div>
      {a.isPending && <p className="m-0 text-[13px] text-muted">Loading…</p>}
      {a.isError && <p className="m-0 text-[13px] text-danger">{errorText(a.error)}</p>}
      {a.data && (
        <>
          {a.data.backfill_pending && <p className="m-0 mb-2 text-xs text-warn">Zernio is still collecting results for this campaign.</p>}
          <div className="mb-3 flex flex-wrap gap-4 text-[13px]">
            <span>Spend {money(a.data.summary?.spend, a.data.currency)}</span>
            <span>Impressions {num(a.data.summary?.impressions)}</span>
            <span>Reach {num(a.data.summary?.reach)}</span>
            <span>Clicks {num(a.data.summary?.clicks)}</span>
            <span>CTR {pct(a.data.summary?.ctr)}</span>
            <span>CPC {money(a.data.summary?.cpc, a.data.currency)}</span>
            <span>Conversions {num(a.data.summary?.conversions)}</span>
            <span>ROAS {roas(a.data.summary?.roas)}</span>
          </div>
          {a.data.daily.length === 0 ? (
            <p className="m-0 text-xs text-muted">No daily results yet.</p>
          ) : (
            <div className="chart" aria-label="Daily spend">
              {a.data.daily.map((d) => (
                <div key={d.day} className="bar" title={`${d.day}: ${money(d.spend, a.data.currency)}`} style={{ height: `${Math.round(((d.spend ?? 0) / max) * 100)}%` }} />
              ))}
            </div>
          )}
          {a.data.breakdowns.length > 0 && (
            <table className="mt-3">
              <thead>
                <tr>
                  <th>Breakdown</th>
                  <th>Value</th>
                  <th>Spend</th>
                  <th>Impressions</th>
                  <th>Clicks</th>
                </tr>
              </thead>
              <tbody>
                {a.data.breakdowns.map((b, i) => (
                  <tr key={`${b.dimension}-${b.value}-${i}`}>
                    <td>{b.dimension}</td>
                    <td>{b.value}</td>
                    <td>{money(b.spend, a.data.currency)}</td>
                    <td>{num(b.impressions)}</td>
                    <td>{num(b.clicks)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}

export default function ZernioCampaigns({ range }: { range: ZRange }) {
  const qc = useQueryClient();
  const [platform, setPlatform] = useState("");
  const [status, setStatusFilter] = useState("");
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [panel, setPanel] = useState<{ id: string; kind: "edit" | "analytics" } | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const filters = { platform: platform || null, status: status || null, q: search || null, page, range };
  const list = useQuery({ queryKey: zernioKeys.campaigns(filters), queryFn: () => fetchCampaigns(filters) });
  const remove = useMutation({
    mutationFn: deleteCampaign,
    onSuccess: (r) => {
      setNote(r.deleted ? `Deleted${r.ad_count ? ` (${r.ad_count} ads)` : ""}.` : "Not deleted.");
      void qc.invalidateQueries({ queryKey: zernioKeys.all });
    },
    onError: (e) => setNote(errorText(e)),
  });

  if (list.isError && list.error instanceof ApiError && list.error.status === 503)
    return (
      <div className="card">
        <p className="m-0 text-[13px]">{errorText(list.error)}</p>
      </div>
    );
  return (
    <div className="card" style={{ padding: 0 }} data-testid="zernio-campaigns">
      <div className="flex flex-wrap items-center gap-2 p-4">
        <span className="mr-auto font-semibold">Zernio campaigns</span>
        <select value={platform} onChange={(e) => (setPlatform(e.target.value), setPage(1))} aria-label="Platform">
          {PLATFORMS.map(([k, label]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </select>
        <select value={status} onChange={(e) => (setStatusFilter(e.target.value), setPage(1))} aria-label="Status">
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s ? s.replace(/_/g, " ") : "Any status"}
            </option>
          ))}
        </select>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setSearch(q.trim());
            setPage(1);
          }}
        >
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search names or ids" aria-label="Search" />
        </form>
        <Link href="/marketing/paid/zernio/new" className="btn btn-sm">
          + New Zernio campaign
        </Link>
      </div>
      {note && <p className="m-0 px-4 pb-2 text-xs text-muted">{note}</p>}
      {list.data?.backfill_pending && <p className="m-0 px-4 pb-2 text-xs text-warn">Zernio is still collecting results; numbers may fill in shortly.</p>}
      {list.isPending ? (
        <p className="m-0 px-4 pb-4 text-[13px] text-muted">Loading…</p>
      ) : list.isError ? (
        <p className="m-0 px-4 pb-4 text-[13px] text-danger">{errorText(list.error)}</p>
      ) : list.data.items.length === 0 ? (
        <p className="m-0 px-4 pb-4 text-[13px] text-muted">
          No Zernio campaigns yet. <Link href="/marketing/paid/zernio/new" className="underline">Create one</Link>.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th>Campaign</th>
                <th>Status</th>
                <th>Budget</th>
                <th>Spend</th>
                <th>Impr.</th>
                <th>Clicks</th>
                <th>CTR</th>
                <th>Conv.</th>
                <th>ROAS</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {list.data.items.map((c) => (
                <Fragment key={c.id}>
                  <tr>
                    <td>
                      <button type="button" className="mr-1 text-muted" aria-label="Show ad sets" onClick={() => setOpen({ ...open, [c.id]: !open[c.id] })}>
                        {open[c.id] ? "▾" : "▸"}
                      </button>
                      <span className="font-medium">{c.name ?? c.id}</span>
                      <span className="block text-xs text-muted">
                        {TREE_LABEL[c.platform] ?? c.platform}
                        {c.objective ? ` · ${c.objective}` : ""}
                        {c.ad_account_name ? ` · ${c.ad_account_name}` : ""}
                      </span>
                    </td>
                    <td>
                      <StatusPill status={c.status} />
                      {c.review_status && c.review_status !== "approved" && <span className="block text-xs text-muted">{c.review_status.replace(/_/g, " ")}</span>}
                    </td>
                    <td>{c.budget?.amount != null ? `${formatMoney(c.budget.amount, c.currency)} ${c.budget.type ?? ""}` : dash}</td>
                    <MetricCells m={c.metrics} currency={c.currency} />
                    <td>
                      <div className="flex flex-wrap gap-1">
                        <Toggle level="campaigns" id={c.id} status={c.status} onDone={setNote} />
                        <button type="button" className="btn btn-secondary btn-sm" onClick={() => setPanel(panel?.id === c.id && panel.kind === "analytics" ? null : { id: c.id, kind: "analytics" })}>
                          Results
                        </button>
                        <button type="button" className="btn btn-secondary btn-sm" onClick={() => setPanel(panel?.id === c.id && panel.kind === "edit" ? null : { id: c.id, kind: "edit" })}>
                          Edit
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          disabled={remove.isPending}
                          onClick={() => window.confirm(`Delete "${c.name ?? c.id}" on ${TREE_LABEL[c.platform] ?? c.platform}, with its ad sets and ads?`) && remove.mutate(c.id)}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                  {panel?.id === c.id && (
                    <tr>
                      <td colSpan={10}>
                        {panel.kind === "edit" ? <EditForm c={c} onClose={() => setPanel(null)} onDone={setNote} /> : <Analytics c={c} range={range} onClose={() => setPanel(null)} />}
                      </td>
                    </tr>
                  )}
                  {open[c.id] &&
                    c.ad_sets.map((s) => (
                      <Fragment key={s.id}>
                        <tr className="text-[13px]">
                          <td className="pl-8">
                            Ad set · {s.name ?? s.id}
                          </td>
                          <td>
                            <StatusPill status={s.status} />
                          </td>
                          <td>{s.budget?.amount != null ? `${formatMoney(s.budget.amount, c.currency)} ${s.budget.type ?? ""}` : dash}</td>
                          <MetricCells m={s.metrics} currency={c.currency} />
                          <td>
                            <Toggle level="ad-sets" id={s.id} status={s.status} onDone={setNote} />
                          </td>
                        </tr>
                        {s.ads.map((a) => (
                          <tr key={a.id} className="text-[13px]">
                            <td className="pl-14">
                              Ad · {a.name ?? a.id}
                            </td>
                            <td>
                              <StatusPill status={a.status} />
                              {a.review_status && a.review_status !== "approved" && <span className="block text-xs text-muted">{a.review_status.replace(/_/g, " ")}</span>}
                            </td>
                            <td>{dash}</td>
                            <MetricCells m={a.metrics} currency={c.currency} />
                            <td>
                              <Toggle level="ads" id={a.id} status={a.status} onDone={setNote} />
                            </td>
                          </tr>
                        ))}
                      </Fragment>
                    ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {list.data && list.data.pages > 1 && (
        <div className="flex items-center justify-end gap-2 p-3 text-[13px]">
          <button type="button" className="btn btn-secondary btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            Previous
          </button>
          <span>
            Page {list.data.page} of {list.data.pages}
          </span>
          <button type="button" className="btn btn-secondary btn-sm" disabled={page >= list.data.pages} onClick={() => setPage(page + 1)}>
            Next
          </button>
        </div>
      )}
    </div>
  );
}
