"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { fetchLocaleOptions, fetchTenant, tenantKeys } from "@/lib/api/tenant";
import { ApiError, isRoleDenied } from "@/lib/types/common";
import type { PostStatus } from "@/lib/types/organic";
import { PLATFORM_LABEL, type SocialPlatform } from "@/lib/types/social";

// Organic Marketing (SPEC-FE-050) shared pieces: the section tab bar, status
// badges, error text, and the company-timezone helpers used by every
// schedule form. Nothing here invents data; it only formats backend values.

const SECTIONS = [
  { href: "/marketing/organic", label: "Dashboard" },
  { href: "/marketing/organic/create", label: "Create" },
  { href: "/marketing/organic/photo", label: "Photo Generation" },
  { href: "/marketing/organic/video", label: "Video Generation" },
  { href: "/marketing/organic/calendar", label: "Calendar" },
  { href: "/marketing/organic/history", label: "Published & History" },
  { href: "/marketing/organic/accounts", label: "Accounts" },
  { href: "/marketing/organic/analytics", label: "Analytics" },
  { href: "/marketing/organic/socialapi", label: "SocialAPI" }, // SPEC-FE-054
];

export function OrganicHeader({ title, subtitle, action }: { title: string; subtitle: string; action?: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <>
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <Link href="/marketing" className="text-xs text-muted underline">
            ← Marketing
          </Link>
          <h1 className="page-title">{title}</h1>
          <p className="page-subtitle mb-0">{subtitle}</p>
        </div>
        {action}
      </div>
      <nav className="tabs mb-4 overflow-x-auto" aria-label="Organic Marketing sections">
        {SECTIONS.map((s) => {
          const active = s.href === "/marketing/organic" ? pathname === s.href : pathname.startsWith(s.href);
          return (
            <Link key={s.href} href={s.href} className={active ? "tab active" : "tab"} aria-current={active ? "page" : undefined}>
              {s.label}
            </Link>
          );
        })}
      </nav>
    </>
  );
}

const POST_BADGE: Record<string, string> = {
  scheduled: "badge badge-neutral",
  pending: "badge badge-neutral",
  publishing: "badge badge-warn",
  published: "badge badge-success",
  failed: "badge badge-danger",
  cancelled: "badge badge-neutral",
  draft: "badge badge-neutral",
  needs_approval: "badge badge-warn",
  approved: "badge badge-success",
  archived: "badge badge-neutral",
  connected: "badge badge-success",
  missing_permissions: "badge badge-warn",
  expired: "badge badge-danger",
  error: "badge badge-danger",
  not_connected: "badge badge-neutral",
  succeeded: "badge badge-success",
  running: "badge badge-warn",
  queued: "badge badge-neutral",
};

export function StatusBadge({ status }: { status: PostStatus | string }) {
  return <span className={POST_BADGE[status] ?? "badge badge-neutral"}>{status.replace(/_/g, " ")}</span>;
}

export function PlatformTag({ platform }: { platform: SocialPlatform | string }) {
  return <span className="badge badge-neutral">{PLATFORM_LABEL[platform as SocialPlatform] ?? platform}</span>;
}

/** The backend's own message; 403 in plain words (the client doesn't know the user's role). */
export function errorText(err: unknown, forbidden = "Your role can't do this; ask a manager or the owner."): string {
  if (err instanceof ApiError) {
    if (isRoleDenied(err)) return forbidden;
    const detail = (err.body as { detail?: unknown } | undefined)?.detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d: { msg?: string; loc?: unknown[] }) => `${(d.loc ?? []).slice(1).join(".")}: ${(d.msg ?? "").replace(/^Value error, /, "")}`)
        .join(" ");
    }
  }
  return err instanceof Error ? err.message : String(err);
}

export function useCompanyTimezone(): string {
  const tenant = useQuery({ queryKey: tenantKeys.me, queryFn: fetchTenant, staleTime: 60_000 });
  return tenant.data?.timezone ?? "UTC";
}

/** A searchable timezone field (every IANA zone from the backend's list). */
export function TimezoneField({ id, value, onChange }: { id: string; value: string; onChange: (tz: string) => void }) {
  const options = useQuery({ queryKey: tenantKeys.localeOptions, queryFn: fetchLocaleOptions, staleTime: Infinity });
  return (
    <>
      <input id={id} list={`${id}-list`} value={value} onChange={(e) => onChange(e.target.value)} placeholder="e.g. Asia/Dhaka" autoComplete="off" />
      <datalist id={`${id}-list`}>
        {(options.data?.timezones ?? []).map((z) => (
          <option key={z.name} value={z.name}>
            {`(UTC${z.offset}) ${z.name}`}
          </option>
        ))}
      </datalist>
    </>
  );
}

/** "YYYY-MM-DD" for a date in a timezone. */
export function ymdIn(tz: string, at: Date = new Date()): string {
  try {
    return new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).format(at);
  } catch {
    return at.toISOString().slice(0, 10);
  }
}

export function addDays(ymd: string, days: number): string {
  const d = new Date(`${ymd}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** A post's time for people: its own local wall-clock time and zone. */
export function postTime(p: { local_time: string | null; timezone: string; scheduled_at: string }): string {
  if (p.local_time) {
    const [d, t] = p.local_time.split("T");
    const day = new Date(`${d}T00:00:00Z`).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
    return `${day} ${t?.slice(0, 5) ?? ""} (${p.timezone})`;
  }
  return new Date(p.scheduled_at).toLocaleString();
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="m-0 p-4 text-[13px] text-muted">{children}</p>;
}
