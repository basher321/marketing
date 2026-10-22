"use client";

import { useQuery } from "@tanstack/react-query";

import { analyticsKeys, fetchEngagementReport } from "@/lib/api/analytics";
import type { RangeKey } from "@/lib/types/analytics";

import { BarChart, EMPTY, ReportStatus, Tile, channelLabel } from "./ads-report";
import { formatNumber } from "@/lib/format/number";

const PIPELINE = [
  { key: "draft", label: "Draft" },
  { key: "pending_approval", label: "Pending approval" },
  { key: "approved", label: "Approved" },
  { key: "published", label: "Published" },
] as const;

// Analytics › Engagement (SPEC-FE-035, backend SPEC-BE-050). Post counts come
// from scheduled_posts, the pipeline from content_assets. Likes, comments,
// shares and reach are "—": no post engagement is imported yet.
export default function EngagementReport({ range }: { range: RangeKey }) {
  const query = useQuery({
    queryKey: analyticsKeys.engagement(range),
    queryFn: () => fetchEngagementReport(range),
  });

  return (
    <ReportStatus query={query} what="engagement report">
      {() => {
        const r = query.data!;
        // posts_by_day = the window plus the next 7 days, so today is 8th from the end.
        const today = r.posts_by_day[r.posts_by_day.length - 8]?.date;
        return (
          <>
            <div className="grid grid-cols-4 gap-4 max-[900px]:grid-cols-2">
              <Tile title={`Published (${range})`} value={String(r.posts.published)} />
              <Tile title="Scheduled" value={String(r.posts.scheduled)} sub="Upcoming, any date" />
              <Tile title="Pending" value={String(r.posts.pending)} sub="Waiting to be scheduled" />
              <Tile title={`Failed (${range})`} value={String(r.posts.failed)} />
            </div>
            <h2 className="section-title">Posts by Day</h2>
            <div className="card">
              <BarChart
                days={r.posts_by_day}
                series={[
                  { key: "published", label: "Published", barClass: "bar", dotClass: "bg-chart-1" },
                  {
                    key: "scheduled",
                    label: "Scheduled / pending",
                    barClass: "bar bg-none bg-chart-3",
                    dotClass: "bg-chart-3",
                  },
                ]}
                today={today}
              />
            </div>
            <div className="mt-4 grid grid-cols-2 gap-4 max-[900px]:grid-cols-1">
              <div>
                <h2 className="section-title">By Channel</h2>
                <div className="card overflow-x-auto">
                  <table>
                    <thead>
                      <tr>
                        <th>Channel</th>
                        <th>Published ({range})</th>
                        <th>Scheduled / pending</th>
                      </tr>
                    </thead>
                    <tbody>
                      {r.posts_by_channel.length === 0 ? (
                        <tr>
                          <td colSpan={3} className="text-muted">
                            {EMPTY}
                          </td>
                        </tr>
                      ) : (
                        r.posts_by_channel.map((c) => (
                          <tr key={c.channel}>
                            <td>{channelLabel(c.channel)}</td>
                            <td>{c.published}</td>
                            <td>{c.scheduled}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
              <div>
                <h2 className="section-title">Content Pipeline</h2>
                <div className="card">
                  <div className="flex flex-wrap items-center gap-2">
                    {PIPELINE.map((s, i) => (
                      <div key={s.key} className="flex items-center gap-2">
                        {i > 0 && <span className="text-muted">→</span>}
                        <div className="rounded-md border border-border px-3 py-2 text-center">
                          <div className="text-[20px] font-bold">{r.content[s.key]}</div>
                          <div className="text-xs text-muted">{s.label}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                  <p className="mb-0 mt-3 text-xs text-muted">All content assets, current status.</p>
                </div>
              </div>
            </div>
            <h2 className="section-title">Engagement</h2>
            <div className="grid grid-cols-4 gap-4 max-[900px]:grid-cols-2">
              <Tile title="Likes" value={r.likes === null ? "—" : formatNumber(r.likes)} />
              <Tile title="Comments" value={r.comments === null ? "—" : formatNumber(r.comments)} />
              <Tile title="Shares" value={r.shares === null ? "—" : formatNumber(r.shares)} />
              <Tile title="Reach" value={r.reach === null ? "—" : formatNumber(r.reach)} />
            </div>
            {[r.likes, r.comments, r.shares, r.reach].some((v) => v === null) && (
              <p className="mb-0 mt-2 text-xs text-muted">{r.missing_reason}</p>
            )}
          </>
        );
      }}
    </ReportStatus>
  );
}
