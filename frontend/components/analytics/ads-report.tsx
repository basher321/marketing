"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { analyticsKeys, fetchAdsReport } from "@/lib/api/analytics";
import { syncPlatformResults } from "@/lib/api/ads";
import { syncAllMetaResults } from "@/lib/api/meta";
import { ApiError } from "@/lib/types/common";
import type { AdsCampaignRow, RangeKey } from "@/lib/types/analytics";
import { formatMoney } from "@/lib/format/money";
import { formatNumber, formatPercent } from "@/lib/format/number";

// ---- Shared by the Ads / Engagement / Customer Service tabs (SPEC-FE-035) ----

export const CHANNEL_LABELS: Record<string, string> = {
  facebook: "Facebook", instagram: "Instagram", tiktok: "TikTok", whatsapp: "WhatsApp",
  messenger: "Messenger", email: "Email", sms: "SMS", web: "Web",
};

export function channelLabel(channel: string): string {
  return CHANNEL_LABELS[channel] ?? channel;
}

// Whole major units in the currency's own symbol (SPEC-FE-048): "৳48,320", "¥1,500".
export function money(amount: number, currency: string): string {
  return formatMoney(amount, currency, { whole: true });
}

export function pct(value: number): string {
  return formatPercent(value);
}

// "Sep 3" for a backend date. The dates are tenant-local calendar days sent as
// plain "YYYY-MM-DD", so they are parsed and labelled in UTC (no shift).
export function shortDate(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00Z`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

/** A stat tile in the mockup's .card style. `hint` explains a "—" value. */
export function Tile({ title, value, sub, hint }: { title: string; value: string; sub?: string; hint?: string }) {
  return (
    <div className="card" title={hint}>
      <p className="card-title">{title}</p>
      <p className={value === "—" ? "card-value text-muted" : "card-value"}>{value}</p>
      {sub && <p className="mt-1.5 text-xs text-muted">{sub}</p>}
      {hint && <p className="mt-1.5 text-xs text-muted">{hint}</p>}
    </div>
  );
}

/** Loading / error state for a whole tab; renders children once loaded. */
export function ReportStatus({
  query,
  what,
  children,
}: {
  query: { isPending: boolean; isError: boolean; error: Error | null };
  what: string;
  children: () => ReactNode;
}) {
  if (query.isPending)
    return (
      <div className="card" aria-busy="true">
        <p className="m-0 text-[13px] text-muted">Loading…</p>
      </div>
    );
  if (query.isError)
    return (
      <div className="card">
        <p className="m-0 text-[13px] text-danger" role="alert">
          Failed to load {what}: {query.error?.message}
        </p>
      </div>
    );
  return <>{children()}</>;
}

export const EMPTY = "No data in this period";

export type ChartSeries<T> = { key: keyof T & string; label: string; barClass: string; dotClass: string };

/**
 * Daily bar chart built from the mockup's .chart/.bar markup (no chart library,
 * like the Revenue by Day chart). One group of bars per day, one bar per series,
 * scaled to the largest value; all-zero data shows the empty message instead.
 * `today` marks that day in the axis; hover a bar for its exact value.
 */
export function BarChart<T extends { date: string }>({
  days,
  series,
  today,
  format = String,
}: {
  days: T[];
  series: ChartSeries<T>[];
  today?: string;
  format?: (value: number) => string;
}) {
  const value = (d: T, key: keyof T) => Number(d[key] ?? 0);
  const max = Math.max(0, ...days.flatMap((d) => series.map((s) => value(d, s.key))));
  if (max === 0) return <p className="m-0 text-[13px] text-muted">{EMPTY}</p>;
  const last = days.length - 1;
  const todayIndex = today ? days.findIndex((d) => d.date === today) : -1;
  return (
    <>
      <div className="chart" style={{ gap: days.length > 31 ? 2 : 6 }}>
        {days.map((d) => (
          <div key={d.date} className="flex h-full flex-1 items-end gap-px">
            {series.map((s) => (
              <div
                key={s.key}
                className={s.barClass}
                style={{ height: `${(value(d, s.key) / max) * 100}%` }}
                title={`${shortDate(d.date)} · ${s.label}: ${format(value(d, s.key))}`}
              />
            ))}
          </div>
        ))}
      </div>
      {/* Axis: first and last day; "Today" sits under its own day when the
          series runs past it (Engagement shows the next 7 days). */}
      <div className="relative flex justify-between text-xs text-muted">
        <span>{shortDate(days[0].date)}</span>
        {todayIndex > 0 && todayIndex < last && (
          <span
            className="absolute -translate-x-1/2"
            style={{ left: `${((todayIndex + 0.5) / days.length) * 100}%` }}
          >
            ▲ Today
          </span>
        )}
        <span>{todayIndex === last ? "Today" : shortDate(days[last].date)}</span>
      </div>
      {series.length > 1 && (
        <div className="chart-legend">
          {series.map((s) => (
            <span key={s.key}>
              <span className={`legend-dot ${s.dotClass}`} />
              {s.label}
            </span>
          ))}
        </div>
      )}
    </>
  );
}

// ---- Ads tab ----

// Same badges as Marketing › Active Campaigns.
const STATUS_BADGES: Record<string, { label: string; className: string }> = {
  running: { label: "Running", className: "badge badge-success" },
  paused: { label: "Paused", className: "badge badge-warn" },
  scheduled: { label: "Scheduled", className: "badge badge-neutral" },
};

// Pacing = lifetime spend vs where the budget should be by now (backend formula).
// Over 100% means spending ahead of schedule, so the bar turns amber.
function Pacing({ value }: { value: number | null }) {
  if (value === null)
    return (
      <span className="text-muted" title="Needs a budget and start/end dates">
        —
      </span>
    );
  return (
    <div className="min-w-[90px]">
      <span>{pct(value)}</span>
      <div className="mt-1 h-1 w-full rounded bg-border">
        <div
          className={`h-1 rounded ${value > 100 ? "bg-warn" : "bg-accent"}`}
          style={{ width: `${Math.min(value, 100)}%` }}
        />
      </div>
    </div>
  );
}

function CampaignRow({ c, currency }: { c: AdsCampaignRow; currency: string }) {
  const badge = STATUS_BADGES[c.status] ?? { label: c.status, className: "badge badge-neutral" };
  return (
    <tr>
      <td>{c.name}</td>
      <td>
        <span className={badge.className}>{badge.label}</span>
      </td>
      <td>{c.channels.map(channelLabel).join(", ") || "—"}</td>
      <td>{money(c.budget, currency)}</td>
      <td>{money(c.spend, currency)}</td>
      <td>
        <Pacing value={c.pacing_pct} />
      </td>
    </tr>
  );
}

const SOURCE_LABEL: Record<string, string> = {
  meta: "Meta", tiktok: "TikTok", google: "Google Ads / YouTube", linkedin: "LinkedIn", x: "X", snapchat: "Snapchat", pinterest: "Pinterest",
};

// "Source: Meta · last synced …" with Sync now (SPEC-FE-042); the backend
// throttles manual syncs to one per 5 minutes and says so.
function MetaSyncLine({ source }: { source: string | null | undefined }) {
  const queryClient = useQueryClient();
  const sync = useMutation({
    // Meta and the other ad platforms sync side by side. "Not connected" (409)
    // from one side is dropped when the other side worked.
    mutationFn: async () => {
      const [meta, others] = await Promise.allSettled([syncAllMetaResults(), syncPlatformResults()]);
      const ok = [meta, others].filter((r) => r.status === "fulfilled");
      const failed = [meta, others].flatMap((r) => (r.status === "rejected" ? [r.reason as unknown] : []));
      if (!ok.length) throw failed[0];
      const errors = [
        ...ok.flatMap((r) => (r.status === "fulfilled" ? r.value.errors : [])),
        ...failed.filter((e) => !(e instanceof ApiError && e.status === 409)).map((e) => ({ campaign_id: null, message: e instanceof Error ? e.message : String(e), at: "" })),
      ];
      return { last_sync_at: new Date().toISOString(), errors };
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["analytics"] }),
  });
  return (
    <p className="mb-3 mt-0 flex flex-wrap items-center gap-2 text-xs text-muted">
      {source ? `Source: ${source.split(", ").map((s) => SOURCE_LABEL[s] ?? s).join(", ")} (imported results)` : "No ad results imported for this period yet."}
      {sync.data && ` · last synced ${new Date(sync.data.last_sync_at).toLocaleTimeString()}`}
      <button type="button" className="btn btn-secondary btn-sm" disabled={sync.isPending} onClick={() => sync.mutate()}>
        {sync.isPending ? "Syncing…" : "Sync now"}
      </button>
      {sync.isError && <span className="text-danger">{sync.error.message}</span>}
      {sync.data && sync.data.errors.length > 0 && <span className="text-danger">{sync.data.errors[0].message}</span>}
    </p>
  );
}

// Analytics › Ads (SPEC-FE-035 + SPEC-FE-042): CTR, ROAS, impressions, reach,
// clicks and conversions come from imported Meta results (SPEC-BE-056); "—"
// with the backend's reason only when Meta reported none - never an estimate.
export default function AdsReport({ range }: { range: RangeKey }) {
  const query = useQuery({ queryKey: analyticsKeys.ads(range), queryFn: () => fetchAdsReport(range) });
  const count = (v: number | null | undefined) => (v === null || v === undefined ? "—" : formatNumber(v));

  return (
    <ReportStatus query={query} what="ads report">
      {() => {
        const r = query.data!;
        const t = r.totals;
        return (
          <>
            <MetaSyncLine source={t.source} />
            <div className="grid grid-cols-5 gap-4 max-[900px]:grid-cols-2">
              <Tile title={`Spend (${range})`} value={money(t.spend, r.currency)} />
              <Tile title="Active campaigns" value={String(t.active_campaigns)} />
              <Tile
                title="Budget used"
                value={t.budget_used_pct === null ? "—" : pct(t.budget_used_pct)}
                sub={t.budget_total ? `of ${money(t.budget_total, r.currency)}` : "No campaign budget"}
              />
              <Tile title="CTR" value={t.ctr === null ? "—" : pct(t.ctr)} hint={t.ctr === null ? t.missing_reason : undefined} />
              <Tile
                title="ROAS"
                value={t.roas === null ? "—" : `${formatNumber(t.roas)}x`}
                hint={t.roas === null ? t.missing_reason : undefined}
              />
            </div>
            <div className="mt-4 grid grid-cols-4 gap-4 max-[900px]:grid-cols-2">
              <Tile title="Impressions" value={count(t.impressions)} hint={t.impressions == null ? t.missing_reason : undefined} />
              <Tile title="Reach" value={count(t.reach)} hint={t.reach == null ? t.missing_reason : undefined} />
              <Tile title="Link clicks" value={count(t.clicks)} hint={t.clicks == null ? t.missing_reason : undefined} />
              <Tile title="Conversions" value={count(t.conversions)} hint={t.conversions == null ? t.missing_reason : undefined} />
            </div>
            <h2 className="section-title">Spend by Day</h2>
            <div className="card">
              <BarChart
                days={r.spend_by_day}
                series={[{ key: "spend", label: "Spend", barClass: "bar", dotClass: "bg-chart-1" }]}
                today={r.spend_by_day[r.spend_by_day.length - 1]?.date}
                format={(v) => money(v, r.currency)}
              />
            </div>
            <h2 className="section-title">Campaigns</h2>
            <div className="card overflow-x-auto">
              <table>
                <thead>
                  <tr>
                    <th>Campaign</th>
                    <th>Status</th>
                    <th>Channels</th>
                    <th>Budget</th>
                    <th>Spend ({range})</th>
                    <th>Pacing</th>
                  </tr>
                </thead>
                <tbody>
                  {r.campaigns.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="text-muted">
                        No running, scheduled or paused campaigns
                      </td>
                    </tr>
                  ) : (
                    r.campaigns.map((c) => <CampaignRow key={c.id} c={c} currency={r.currency} />)
                  )}
                </tbody>
              </table>
            </div>
          </>
        );
      }}
    </ReportStatus>
  );
}
