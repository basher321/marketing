"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";

import { OrganicHeader, StatusBadge, addDays, errorText, postTime, useCompanyTimezone, ymdIn } from "@/components/organic/shared";
import { cancelPost, fetchCalendar, organicKeys, reschedulePost, retryPost } from "@/lib/api/organic";
import type { Post } from "@/lib/types/organic";
import { PLATFORM_LABEL } from "@/lib/types/social";

const CHIP: Record<string, string> = {
  published: "border-success",
  failed: "border-danger",
  publishing: "border-warn",
  scheduled: "border-accent",
  pending: "border-border",
};

function weekStart(ymd: string): string {
  const d = new Date(`${ymd}T00:00:00Z`);
  const dow = (d.getUTCDay() + 6) % 7; // Monday = 0
  return addDays(ymd, -dow);
}

function PostDrawer({ post, onClose }: { post: Post; onClose: () => void }) {
  const queryClient = useQueryClient();
  const tz = post.timezone;
  const [date, setDate] = useState(post.local_time?.slice(0, 10) ?? "");
  const [time, setTime] = useState(post.local_time?.slice(11, 16) ?? "");
  const done = () => {
    void queryClient.invalidateQueries({ queryKey: ["organic"] });
    onClose();
  };
  const move = useMutation({ mutationFn: () => reschedulePost(post.id, `${date}T${time}`, tz), onSuccess: done });
  const cancel = useMutation({ mutationFn: () => cancelPost(post.id), onSuccess: done });
  const retry = useMutation({ mutationFn: () => retryPost(post.id), onSuccess: done });
  const err = move.error ?? cancel.error ?? retry.error;
  return (
    <aside className="card fixed bottom-0 right-0 top-0 z-30 w-full max-w-[380px] overflow-y-auto shadow-lg" role="dialog" aria-label="Post details" data-testid="post-drawer">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="m-0">{PLATFORM_LABEL[post.platform]} post</h3>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close">
          ✕
        </button>
      </div>
      <div className="mb-2 flex flex-wrap items-center gap-2 text-[13px]">
        <StatusBadge status={post.status} />
        <span>{postTime(post)}</span>
      </div>
      <p className="whitespace-pre-wrap text-[13px]">{post.excerpt}</p>
      {post.error_message && <p className="text-xs text-danger">{post.error_message}</p>}
      <div className="mb-3 flex flex-wrap gap-2">
        {post.external_url && (
          <a href={post.external_url} target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm no-underline">
            Open on {PLATFORM_LABEL[post.platform]} ↗
          </a>
        )}
        {post.content_id && (
          <Link href={`/marketing/organic/content/${post.content_id}`} className="btn btn-secondary btn-sm no-underline">
            Open editor
          </Link>
        )}
      </div>
      {(post.status === "scheduled" || post.status === "failed") && (
        <div className="card" style={{ padding: 10 }}>
          <div className="mb-1 text-[13px] font-semibold">Reschedule ({tz})</div>
          <div className="flex flex-wrap gap-2">
            <input type="date" aria-label="Date" value={date} onChange={(e) => setDate(e.target.value)} />
            <input type="time" aria-label="Time" value={time} onChange={(e) => setTime(e.target.value)} />
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            <button type="button" className="btn btn-sm" disabled={!date || !time || move.isPending} onClick={() => move.mutate()}>
              Reschedule
            </button>
            {post.status === "scheduled" && (
              <button type="button" className="btn btn-secondary btn-sm" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
                Cancel post
              </button>
            )}
            {post.status === "failed" && (
              <button type="button" className="btn btn-secondary btn-sm" disabled={retry.isPending} onClick={() => retry.mutate()}>
                Retry now
              </button>
            )}
          </div>
        </div>
      )}
      {err && <p className="mt-2 text-xs text-danger">{errorText(err)}</p>}
    </aside>
  );
}

// Content Calendar (SPEC-FE-050): month or week, in the company timezone; each
// post sits on its own local date. Data: GET /organic/calendar.
export default function CalendarPage() {
  const tz = useCompanyTimezone();
  const today = ymdIn(tz);
  const [view, setView] = useState<"month" | "week">("month");
  const [anchor, setAnchor] = useState(today);
  const [open, setOpen] = useState<Post | null>(null);
  const { from, to } = useMemo(() => {
    if (view === "week") {
      const s = weekStart(anchor);
      return { from: s, to: addDays(s, 6) };
    }
    const first = `${anchor.slice(0, 7)}-01`;
    const s = weekStart(first);
    return { from: s, to: addDays(s, 41) };
  }, [view, anchor]);
  const cal = useQuery({ queryKey: organicKeys.calendar(from, to), queryFn: () => fetchCalendar(from, to) });
  const month = anchor.slice(0, 7);
  const label = view === "week" ? `Week of ${from}` : new Date(`${anchor.slice(0, 7)}-01T00:00:00Z`).toLocaleDateString(undefined, { month: "long", year: "numeric", timeZone: "UTC" });
  const step = (dir: number) => {
    if (view === "week") setAnchor(addDays(anchor, 7 * dir));
    else {
      const d = new Date(`${anchor.slice(0, 7)}-01T00:00:00Z`);
      d.setUTCMonth(d.getUTCMonth() + dir);
      setAnchor(d.toISOString().slice(0, 10));
    }
  };
  return (
    <>
      <OrganicHeader title="Content Calendar" subtitle={`Every scheduled and published post, by day (${tz}).`} />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => step(-1)} aria-label="Previous">
          ←
        </button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => setAnchor(today)}>
          Today
        </button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => step(1)} aria-label="Next">
          →
        </button>
        <strong className="ml-2">{label}</strong>
        <div className="tabs m-0 ml-auto">
          {(["month", "week"] as const).map((v) => (
            <button key={v} type="button" className={view === v ? "tab active" : "tab"} onClick={() => setView(v)}>
              {v}
            </button>
          ))}
        </div>
      </div>
      {cal.isError && <p className="text-[13px] text-danger">{errorText(cal.error)}</p>}
      <div className="grid grid-cols-7 gap-1 text-[12px]" data-testid="calendar-grid">
        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => (
          <div key={d} className="px-1 text-muted">
            {d}
          </div>
        ))}
        {(cal.data?.days ?? []).map((day) => (
          <div
            key={day.date}
            className={`min-h-[96px] rounded-md border p-1 ${day.date === today ? "border-accent" : "border-border"} ${view === "month" && day.date.slice(0, 7) !== month ? "opacity-50" : ""}`}
            data-date={day.date}
          >
            <div className="mb-1 flex items-center justify-between">
              <span className="font-semibold">{Number(day.date.slice(8, 10))}</span>
              {day.date >= today && (
                <Link href="/marketing/organic/create" className="text-muted no-underline" title="Create a post" aria-label={`Create a post for ${day.date}`}>
                  +
                </Link>
              )}
            </div>
            {day.posts.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => setOpen(p)}
                className={`mb-1 block w-full truncate rounded border-l-4 bg-bg px-1 py-0.5 text-left ${CHIP[p.status] ?? "border-border"}`}
                title={`${PLATFORM_LABEL[p.platform]} · ${p.status} · ${p.excerpt}`}
              >
                {p.local_time?.slice(11, 16)} {PLATFORM_LABEL[p.platform]}
                {p.status === "failed" ? " ⚠" : p.status === "published" ? " ✓" : ""}
              </button>
            ))}
          </div>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted">
        {["scheduled", "publishing", "published", "failed"].map((s) => (
          <span key={s} className="flex items-center gap-1">
            <StatusBadge status={s} />
          </span>
        ))}
      </div>
      {open && <PostDrawer post={open} onClose={() => setOpen(null)} />}
    </>
  );
}
