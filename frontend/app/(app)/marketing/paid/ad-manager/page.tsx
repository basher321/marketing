"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { adsKeys, fetchPlatforms } from "@/lib/api/ads";
import type { Platform } from "@/lib/types/ads";

// Ad Manager (SPEC-FE-044): "+ New campaign" lands here. Pick a platform, then
// /marketing/paid/new?platform=<key> shows that platform's objectives. Platform
// marks are plain text (no third-party logo images). A platform that isn't
// connected can still be picked to build a draft.
function PlatformCard({ p }: { p: Platform }) {
  const steps = `${p.hierarchy.campaign} → ${p.hierarchy.group} → ${p.hierarchy.ad}`;
  return (
    <div className="card flex flex-col gap-2" data-testid={`platform-${p.key}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="text-[15px] font-semibold">{p.label}</div>
        <span className={`badge ${p.connected ? "badge-success" : "badge-neutral"}`}>
          {p.connected ? `Connected${p.account_name ? `: ${p.account_name}` : ""}` : "Not connected"}
        </span>
      </div>
      <div className="text-xs text-muted">Runs on {p.runs_on}</div>
      <div className="text-xs text-muted">{steps}</div>
      {!p.connected && (
        <div className="text-xs text-warn">
          <Link href="/integrations" className="underline">
            Connect in Integrations
          </Link>{" "}
          to publish. You can build a draft now.
        </div>
      )}
      {p.connected && p.publishing === "not_built" && (
        <div className="text-xs text-warn">Publishing to {p.label} isn&apos;t available yet; drafts are saved.</div>
      )}
      <div className="mt-auto pt-1">
        <Link href={`/marketing/paid/new?platform=${p.key}`} className="btn btn-sm">
          Create {p.label} campaign
        </Link>
      </div>
    </div>
  );
}

export default function AdManagerPage() {
  const platforms = useQuery({ queryKey: adsKeys.platforms, queryFn: fetchPlatforms });
  return (
    <div className="mx-auto max-w-[1000px]">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h1 className="page-title">Ad Manager</h1>
          <p className="page-subtitle mb-0">Choose where your ads will run. Each platform has its own objectives and steps.</p>
        </div>
        <Link href="/marketing/paid" className="btn btn-secondary">
          Cancel
        </Link>
      </div>
      {/* SPEC-FE-046: two ways to create a campaign. */}
      <div className="tabs mb-4" role="tablist" aria-label="How to create">
        <div role="tab" aria-selected className="tab active">
          Build manually
        </div>
        <Link role="tab" aria-selected={false} className="tab" href="/marketing/paid/ai/new" data-testid="mode-ai">
          Create with AI
        </Link>
        {/* SPEC-FE-055: every platform through the server's Zernio key. */}
        <Link role="tab" aria-selected={false} className="tab" href="/marketing/paid/zernio/new" data-testid="mode-zernio">
          Zernio (all platforms)
        </Link>
      </div>
      {platforms.isPending ? (
        <p className="text-[13px] text-muted">Loading platforms…</p>
      ) : platforms.isError ? (
        <p className="text-[13px] text-danger">{platforms.error.message}</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {platforms.data.platforms.map((p) => (
            <PlatformCard key={p.key} p={p} />
          ))}
        </div>
      )}
    </div>
  );
}
