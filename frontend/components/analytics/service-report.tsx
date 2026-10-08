"use client";

import { useQuery } from "@tanstack/react-query";

import { analyticsKeys, fetchServiceReport } from "@/lib/api/analytics";
import type { RangeKey } from "@/lib/types/analytics";

import { BarChart, EMPTY, ReportStatus, Tile, channelLabel, pct } from "./ads-report";

function minutes(value: number): string {
  return value < 60 ? `${Number(value.toFixed(1))} min` : `${Number((value / 60).toFixed(1))} h`;
}

function hours(value: number): string {
  return value < 48 ? `${Number(value.toFixed(1))} h` : `${Number((value / 24).toFixed(1))} d`;
}

// Analytics › Customer Service (SPEC-FE-035, backend SPEC-BE-050), for
// conversations created in the range. A null average has nothing to average
// (e.g. no resolved conversations) and shows "—" with that reason.
export default function ServiceReport({ range }: { range: RangeKey }) {
  const query = useQuery({ queryKey: analyticsKeys.service(range), queryFn: () => fetchServiceReport(range) });

  return (
    <ReportStatus query={query} what="customer service report">
      {() => {
        const r = query.data!;
        const c = r.conversations;
        return (
          <>
            <div className="grid grid-cols-3 gap-4 max-[900px]:grid-cols-2">
              <Tile
                title={`Conversations (${range})`}
                value={String(c.total)}
                sub={`${c.open} open · ${c.pending} pending · ${c.resolved} resolved · ${c.escalated} escalated`}
              />
              <Tile
                title="Avg first response"
                value={r.first_response_minutes_avg === null ? "—" : minutes(r.first_response_minutes_avg)}
                hint={r.first_response_minutes_avg === null ? "No replied conversations in this period" : undefined}
              />
              <Tile
                title="Avg resolution time"
                value={r.resolution_hours_avg === null ? "—" : hours(r.resolution_hours_avg)}
                hint={
                  r.resolution_hours_avg === null
                    ? c.resolved > 0
                      ? "No resolution time is recorded for these resolved conversations"
                      : "No resolved conversations in this period"
                    : undefined
                }
              />
              <Tile
                title="CSAT"
                value={r.csat_avg === null ? "—" : r.csat_avg.toFixed(2)}
                sub={`${r.csat_responses} ${r.csat_responses === 1 ? "response" : "responses"}`}
                hint={r.csat_avg === null ? "No customer ratings in this period" : undefined}
              />
              <Tile
                title="AI reply share"
                value={r.replies.ai_share_pct === null ? "—" : pct(r.replies.ai_share_pct)}
                sub={`${r.replies.ai} AI · ${r.replies.agent} agent replies sent`}
                hint={r.replies.ai_share_pct === null ? "No replies sent in this period" : undefined}
              />
              <Tile
                title="Deflection"
                value={r.deflection_pct === null ? "—" : pct(r.deflection_pct)}
                sub="Resolved without an agent message"
                hint={r.deflection_pct === null ? "No resolved conversations in this period" : undefined}
              />
            </div>
            <h2 className="section-title">New vs Resolved by Day</h2>
            <div className="card">
              <BarChart
                days={r.by_day}
                series={[
                  { key: "new", label: "New", barClass: "bar", dotClass: "bg-chart-1" },
                  { key: "resolved", label: "Resolved", barClass: "bar bg-none bg-chart-3", dotClass: "bg-chart-3" },
                ]}
                today={r.by_day[r.by_day.length - 1]?.date}
              />
              {/* "Resolved" is bucketed by resolved_at; conversations marked
                  resolved without one can't be placed on a day. */}
              {c.resolved > 0 && r.by_day.every((d) => d.resolved === 0) && (
                <p className="mb-0 mt-2 text-xs text-muted">
                  Resolved bars need a resolution time, which isn&apos;t recorded for these conversations.
                </p>
              )}
            </div>
            <h2 className="section-title">By Channel</h2>
            <div className="card overflow-x-auto">
              <table>
                <thead>
                  <tr>
                    <th>Channel</th>
                    <th>Conversations</th>
                    <th>Resolved</th>
                    <th>Resolved %</th>
                  </tr>
                </thead>
                <tbody>
                  {r.by_channel.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="text-muted">
                        {EMPTY}
                      </td>
                    </tr>
                  ) : (
                    r.by_channel.map((ch) => (
                      <tr key={ch.channel}>
                        <td>{channelLabel(ch.channel)}</td>
                        <td>{ch.total}</td>
                        <td>{ch.resolved}</td>
                        <td>{pct((ch.resolved / ch.total) * 100)}</td>
                      </tr>
                    ))
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
