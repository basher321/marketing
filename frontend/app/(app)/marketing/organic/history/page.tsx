"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Empty, OrganicHeader, PlatformTag, StatusBadge, errorText, postTime } from "@/components/organic/shared";
import { fetchHistory, organicKeys, retryPost } from "@/lib/api/organic";
import { PLATFORM_LABEL, PLATFORMS } from "@/lib/types/social";

// Published Content / History (SPEC-FE-050): published, failed and cancelled
// posts with the platform's link or error; failed posts can be retried.
export default function HistoryPage() {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState("");
  const [platform, setPlatform] = useState("");
  const [page, setPage] = useState(1);
  const history = useQuery({ queryKey: organicKeys.history(status, platform, page), queryFn: () => fetchHistory(status, platform, page) });
  const retry = useMutation({ mutationFn: (id: string) => retryPost(id), onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["organic"] }) });
  const pages = history.data ? Math.max(1, Math.ceil(history.data.count / 25)) : 1;
  return (
    <>
      <OrganicHeader title="Published Content & History" subtitle="What went out, what failed and why." />
      <div className="mb-3 flex flex-wrap gap-2">
        <select aria-label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">All</option>
          <option value="published">Published</option>
          <option value="failed">Failed</option>
          <option value="cancelled">Cancelled</option>
        </select>
        <select aria-label="Platform" value={platform} onChange={(e) => { setPlatform(e.target.value); setPage(1); }}>
          <option value="">All platforms</option>
          {PLATFORMS.map((p) => (
            <option key={p} value={p}>
              {PLATFORM_LABEL[p]}
            </option>
          ))}
        </select>
      </div>
      <div className="card" style={{ padding: 0 }}>
        {history.isPending ? (
          <Empty>Loading…</Empty>
        ) : history.isError ? (
          <p className="m-0 p-4 text-[13px] text-danger">{errorText(history.error)}</p>
        ) : history.data.items.length === 0 ? (
          <Empty>No posts yet.</Empty>
        ) : (
          <table data-testid="history-table">
            <thead>
              <tr>
                <th>Platform</th>
                <th>Post</th>
                <th>Status</th>
                <th>When</th>
                <th>Result</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {history.data.items.map((p) => (
                <tr key={p.id}>
                  <td>
                    <PlatformTag platform={p.platform} />
                  </td>
                  <td className="max-w-[280px] truncate text-xs" title={p.excerpt}>
                    {p.content_id ? <Link href={`/marketing/organic/content/${p.content_id}`}>{p.excerpt || p.title || "post"}</Link> : p.excerpt}
                  </td>
                  <td>
                    <StatusBadge status={p.status} />
                  </td>
                  <td className="whitespace-nowrap text-xs">{p.published_at ? new Date(p.published_at).toLocaleString() : postTime(p)}</td>
                  <td className="max-w-[260px] text-xs">
                    {p.external_url ? (
                      <a href={p.external_url} target="_blank" rel="noreferrer" className="text-accent underline">
                        Open ↗
                      </a>
                    ) : p.error_message ? (
                      <span className="text-danger">{p.error_message}</span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>
                    {p.status === "failed" && (
                      <button type="button" className="btn btn-secondary btn-sm" disabled={retry.isPending} onClick={() => retry.mutate(p.id)}>
                        Retry
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {retry.isError && <p className="text-xs text-danger">{errorText(retry.error)}</p>}
      {pages > 1 && (
        <div className="mt-3 flex items-center gap-2 text-[13px]">
          <button type="button" className="btn btn-secondary btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            ←
          </button>
          Page {page} of {pages}
          <button type="button" className="btn btn-secondary btn-sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>
            →
          </button>
        </div>
      )}
    </>
  );
}
