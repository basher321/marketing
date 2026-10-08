"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { Tile } from "@/components/analytics/ads-report";
import InsightsCard from "@/components/organic/insights-card";
import { Empty, OrganicHeader, PlatformTag, StatusBadge, errorText, postTime } from "@/components/organic/shared";
import { fetchContents, fetchOrganicReport, fetchSummary, organicKeys } from "@/lib/api/organic";
import { fetchSocialAccounts, socialKeys } from "@/lib/api/social";

// Organic Marketing dashboard (SPEC-FE-050): KPIs, the upcoming queue, posts
// waiting for approval, connected accounts and recent history - all from the
// backend (GET /organic/summary, /organic/contents, /social/accounts,
// /analytics/organic).
export default function OrganicDashboard() {
  const summary = useQuery({ queryKey: organicKeys.summary, queryFn: fetchSummary, refetchInterval: 60_000 });
  const report = useQuery({ queryKey: organicKeys.report("30d"), queryFn: () => fetchOrganicReport("30d") });
  const accounts = useQuery({ queryKey: socialKeys.accounts, queryFn: fetchSocialAccounts });
  const awaiting = useQuery({ queryKey: organicKeys.contents("needs_approval", ""), queryFn: () => fetchContents("needs_approval") });
  const s = summary.data;
  return (
    <>
      <OrganicHeader
        title="Organic Marketing"
        subtitle="Write or generate posts, adapt them per platform, schedule, publish and track — without ad spend."
        action={
          <div className="flex flex-wrap gap-2">
            <Link href="/marketing/organic/create?mode=manual" className="btn btn-secondary no-underline">
              Create post
            </Link>
            <Link href="/marketing/organic/create?mode=ai" className="btn no-underline">
              Create with AI
            </Link>
          </div>
        }
      />
      {summary.isError && <p className="text-[13px] text-danger">{errorText(summary.error)}</p>}
      {s && !s.scheduler.running && (
        <p className="m-0 mb-3 rounded-md bg-accent-soft p-2 text-xs" data-testid="scheduler-stopped">
          The scheduler isn&apos;t running in this backend process, so scheduled posts won&apos;t go out until it is (SCHEDULER_ENABLED).
        </p>
      )}
      <div className="mb-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Tile title="Scheduled · next 7 days" value={s ? String(s.scheduled_next_7d) : "…"} />
        <Tile title="Published · 30 days" value={s ? String(s.published_30d) : "…"} />
        <Tile title="Failed · needs attention" value={s ? String(s.failed_open) : "…"} sub={s && s.failed_open > 0 ? "See Published & History" : undefined} />
        <Tile
          title="Engagements · 30 days"
          value={report.data?.totals.engagements == null ? "—" : report.data.totals.engagements.toLocaleString()}
          hint={report.data?.missing_reason ?? undefined}
        />
      </div>
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { href: "/marketing/organic/create?mode=manual", t: "Write a post", d: "Caption, media, platforms, schedule." },
          { href: "/marketing/organic/create?mode=ai", t: "Create with AI", d: "From a prompt; you review before it goes out." },
          { href: "/marketing/organic/photo", t: "Generate a photo", d: "Product or lifestyle images." },
          { href: "/marketing/organic/video", t: "Generate a video", d: "Short clips for Reels and TikTok." },
        ].map((a) => (
          <Link key={a.href} href={a.href} className="card block text-inherit no-underline hover:border-accent">
            <div className="font-semibold">{a.t} →</div>
            <p className="m-0 text-xs text-muted">{a.d}</p>
          </Link>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card" style={{ padding: 0 }}>
          <div className="flex items-center justify-between p-4">
            <span className="font-semibold">Upcoming</span>
            <Link href="/marketing/organic/calendar" className="text-xs text-accent underline">
              Calendar
            </Link>
          </div>
          {!s ? (
            <Empty>Loading…</Empty>
          ) : s.upcoming.length === 0 ? (
            <Empty>Nothing scheduled.</Empty>
          ) : (
            <table>
              <tbody>
                {s.upcoming.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <PlatformTag platform={p.platform} />
                    </td>
                    <td className="whitespace-nowrap text-xs">{postTime(p)}</td>
                    <td className="max-w-[220px] truncate text-xs" title={p.excerpt}>
                      {p.content_id ? (
                        <Link href={`/marketing/organic/content/${p.content_id}`} className="text-inherit">
                          {p.excerpt || p.title}
                        </Link>
                      ) : (
                        p.excerpt
                      )}
                    </td>
                    <td>
                      <StatusBadge status={p.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
        <section className="card" style={{ padding: 0 }}>
          <div className="p-4 font-semibold">Waiting for approval {s ? `(${s.awaiting_approval})` : ""}</div>
          {awaiting.data && awaiting.data.items.length > 0 ? (
            <table>
              <tbody>
                {awaiting.data.items.slice(0, 6).map((c) => (
                  <tr key={c.id}>
                    <td className="max-w-[260px] truncate text-xs">
                      <Link href={`/marketing/organic/content/${c.id}`}>{c.title || c.excerpt}</Link>
                    </td>
                    <td className="text-xs">{c.platforms.join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty>Nothing waiting.</Empty>
          )}
        </section>
        <InsightsCard days={60} />
        <section className="card">
          <div className="mb-2 flex items-center justify-between">
            <span className="font-semibold">Connected accounts</span>
            <Link href="/marketing/organic/accounts" className="text-xs text-accent underline">
              Manage
            </Link>
          </div>
          <div className="flex flex-wrap gap-2">
            {(accounts.data?.items ?? []).map((a) => (
              <div key={a.platform} className="flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-xs">
                <strong>{a.label}</strong>
                <StatusBadge status={a.status} />
              </div>
            ))}
          </div>
        </section>
        <section className="card" style={{ padding: 0 }}>
          <div className="flex items-center justify-between p-4">
            <span className="font-semibold">Recent</span>
            <Link href="/marketing/organic/history" className="text-xs text-accent underline">
              History
            </Link>
          </div>
          {s && s.recent.length > 0 ? (
            <table>
              <tbody>
                {s.recent.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <PlatformTag platform={p.platform} />
                    </td>
                    <td className="max-w-[220px] truncate text-xs">{p.excerpt}</td>
                    <td>
                      <StatusBadge status={p.status} />
                    </td>
                    <td className="text-xs">
                      {p.external_url ? (
                        <a href={p.external_url} target="_blank" rel="noreferrer" className="text-accent underline">
                          Open ↗
                        </a>
                      ) : (
                        <span className="text-danger" title={p.error_message ?? ""}>
                          {p.error_message ? "error" : ""}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty>Nothing published yet.</Empty>
          )}
        </section>
      </div>
    </>
  );
}
