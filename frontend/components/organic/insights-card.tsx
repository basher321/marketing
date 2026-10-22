"use client";

import { useQuery } from "@tanstack/react-query";

import { PlatformTag, errorText } from "@/components/organic/shared";
import { fetchInsights, organicKeys } from "@/lib/api/organic";
import { formatNumber } from "@/lib/format/number";

const FORMAT_LABEL: Record<string, string> = { post: "single posts", reel: "reels", carousel: "carousels", video: "videos", story: "stories" };

// "What's working" (SPEC-FE-052 / SPEC-BE-081): lines computed by the backend
// from imported post results - never estimated here. The same numbers feed
// the AI copy prompts as guidance; nothing is changed automatically.
export default function InsightsCard({ days = 60 }: { days?: 30 | 60 | 90 }) {
  const insights = useQuery({ queryKey: organicKeys.insights(days), queryFn: () => fetchInsights(days) });
  const data = insights.data;
  return (
    <section className="card" data-testid="insights-card">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-semibold">What&apos;s working</span>
        <span className="text-xs text-muted">last {days} days</span>
      </div>
      {insights.isPending ? (
        <p className="m-0 text-[13px] text-muted">Loading…</p>
      ) : insights.isError ? (
        <p className="m-0 text-[13px] text-danger">{errorText(insights.error)}</p>
      ) : !data?.has_data ? (
        <p className="m-0 text-[13px] text-muted">{data?.reason}</p>
      ) : (
        <>
          <ul className="m-0 mb-3 pl-5 text-[13px]">
            {data.lines.map((l) => (
              <li key={l.text}>{l.text}</li>
            ))}
          </ul>
          <div className="mb-3 grid gap-2 sm:grid-cols-2">
            {data.platforms.map((p) => (
              <div key={p.platform} className="rounded-md border border-border p-2 text-xs">
                <div className="mb-1 flex items-center gap-1.5">
                  <PlatformTag platform={p.platform} />
                  <span className="text-muted">
                    {p.posts_with_results} posts · {formatNumber(p.avg_engagement_rate)}% avg
                  </span>
                </div>
                <div>
                  Best hours ({data.timezone}): {p.best_hours.length ? p.best_hours.map((h) => h.label).join(", ") : "—"}
                </div>
                <div>Best format: {p.best_format ? `${FORMAT_LABEL[p.best_format.post_format] ?? p.best_format.post_format} (${formatNumber(p.best_format.avg_engagement_rate)}%)` : "—"}</div>
              </div>
            ))}
          </div>
          {data.top_posts.length > 0 && (
            <>
              <div className="mb-1 text-xs font-semibold">Top posts</div>
              <table>
                <tbody>
                  {data.top_posts.map((t) => (
                    <tr key={t.post_id}>
                      <td>
                        <PlatformTag platform={t.platform} />
                      </td>
                      <td className="max-w-[260px] truncate text-xs" title={t.excerpt}>
                        {t.excerpt}
                      </td>
                      <td className="whitespace-nowrap text-xs">{formatNumber(t.engagement_rate)}%</td>
                      <td className="text-xs">
                        {t.external_url && (
                          <a href={t.external_url} target="_blank" rel="noreferrer" className="text-accent underline">
                            Open ↗
                          </a>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </>
      )}
    </section>
  );
}
