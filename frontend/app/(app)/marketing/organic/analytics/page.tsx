"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { BarChart, Tile } from "@/components/analytics/ads-report";
import InsightsCard from "@/components/organic/insights-card";
import { Empty, OrganicHeader, PlatformTag, errorText } from "@/components/organic/shared";
import { fetchOrganicReport, importOrganicResults, organicKeys } from "@/lib/api/organic";
import { formatNumber } from "@/lib/format/number";

const fmt = (v: number | null | undefined) => (v === null || v === undefined ? "—" : formatNumber(v));

// Organic Analytics (SPEC-FE-050 / SPEC-BE-078): imported post results only.
// A metric a platform didn't give shows "—", never an estimate.
export default function OrganicAnalyticsPage() {
  const queryClient = useQueryClient();
  const [range, setRange] = useState("30d");
  const report = useQuery({ queryKey: organicKeys.report(range), queryFn: () => fetchOrganicReport(range) });
  const sync = useMutation({ mutationFn: importOrganicResults, onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["organic", "report"] }) });
  const r = report.data;
  const hint = r?.missing_reason ?? undefined;
  return (
    <>
      <OrganicHeader
        title="Organic Analytics"
        subtitle="Results of your published posts, by platform."
        action={
          <div className="flex items-center gap-2">
            <select aria-label="Range" value={range} onChange={(e) => setRange(e.target.value)}>
              <option value="7d">Last 7 days</option>
              <option value="30d">Last 30 days</option>
              <option value="90d">Last 90 days</option>
            </select>
            <button type="button" className="btn btn-secondary btn-sm" disabled={sync.isPending} onClick={() => sync.mutate()}>
              {sync.isPending ? "Importing…" : "Import now"}
            </button>
          </div>
        }
      />
      {sync.isError && <p className="text-xs text-danger">{errorText(sync.error)}</p>}
      {sync.data && sync.data.errors.length > 0 && <p className="text-xs text-warn">{sync.data.errors.join(" · ")}</p>}
      {report.isError && <p className="text-[13px] text-danger">{errorText(report.error)}</p>}
      {r && (
        <>
          <p className="m-0 mb-3 text-xs text-muted">
            {r.posts_published} post(s) published · last import {r.last_import_at ? new Date(r.last_import_at).toLocaleString() : "never"}
            {r.missing_reason ? ` · ${r.missing_reason}` : ""}
          </p>
          <div className="mb-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Tile title="Impressions / views" value={fmt(r.totals.impressions)} hint={r.totals.impressions === null ? hint : undefined} />
            <Tile title="Engagements" value={fmt(r.totals.engagements)} sub="likes + comments + shares + saves" />
            <Tile title="Engagement rate" value={r.engagement_rate === null ? "—" : `${r.engagement_rate}%`} />
            <Tile title="Video views" value={fmt(r.totals.video_views)} />
          </div>
          <div className="card mb-4">
            <h3 className="mt-0">Posts and engagement by day</h3>
            <BarChart
              days={r.daily.map((d) => ({ date: d.date, posts: d.posts, engagements: d.engagements ?? 0 }))}
              series={[
                { key: "posts", label: "Posts", barClass: "bar", dotClass: "" },
                { key: "engagements", label: "Engagements", barClass: "bar bg-chart-2", dotClass: "" },
              ]}
            />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="card" style={{ padding: 0 }}>
              <div className="p-4 font-semibold">By platform</div>
              <table>
                <thead>
                  <tr>
                    <th>Platform</th>
                    <th>Posts</th>
                    <th>Impressions</th>
                    <th>Engagements</th>
                    <th>Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {r.by_platform.map((p) => (
                    <tr key={p.platform}>
                      <td>
                        <PlatformTag platform={p.platform} />
                      </td>
                      <td>{p.posts_published}</td>
                      <td>{fmt(p.impressions)}</td>
                      <td>{fmt(p.engagements)}</td>
                      <td>{p.engagement_rate === null ? "—" : `${p.engagement_rate}%`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="card" style={{ padding: 0 }}>
              <div className="p-4 font-semibold">Top posts</div>
              {r.top_posts.length === 0 ? (
                <Empty>No results imported for this period.</Empty>
              ) : (
                <table>
                  <tbody>
                    {r.top_posts.map((t) => (
                      <tr key={t.post_id}>
                        <td>
                          <PlatformTag platform={t.platform} />
                        </td>
                        <td className="max-w-[220px] truncate text-xs" title={t.excerpt}>
                          {t.external_url ? (
                            <a href={t.external_url} target="_blank" rel="noreferrer">
                              {t.excerpt || "post"}
                            </a>
                          ) : (
                            t.excerpt
                          )}
                        </td>
                        <td className="text-xs">{formatNumber(t.engagements)} eng.</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </>
      )}
      <div className="mt-4">
        {/* SPEC-FE-052: the backend's minimum insight window is 30 days, so 7d shows 30. */}
        <InsightsCard days={range === "90d" ? 90 : 30} />
      </div>
    </>
  );
}
