"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import type { ReactNode } from "react";

import { newTabHref } from "@/hooks/use-new-tab";
import { fetchCampaigns, marketingKeys, marketingListKeys, setCampaignRunning } from "@/lib/api/marketing";
import { isRoleDenied } from "@/lib/types/common";
import type { CampaignListItem } from "@/lib/types/marketing";
import { formatMoney } from "@/lib/format/money";
import { formatNumber } from "@/lib/format/number";

const COLUMN_COUNT = 7;
const ALL_CHANNELS = ["facebook", "instagram", "tiktok", "whatsapp", "messenger", "email", "sms", "web"];
const SHORT: Record<string, string> = {
  facebook: "FB", instagram: "IG", tiktok: "TikTok", whatsapp: "WhatsApp",
  messenger: "Messenger", email: "Email", sms: "SMS", web: "Web",
};

// Badge per real campaign_status. running -> success ("Running", as the mockup).
// The mockup's "Optimizing" is not a live status; paused -> warn and scheduled ->
// neutral are the honest equivalents for the two other listed statuses.
const STATUS_BADGES: Record<string, { label: string; className: string }> = {
  running: { label: "Running", className: "badge badge-success" },
  paused: { label: "Paused", className: "badge badge-warn" },
  scheduled: { label: "Scheduled", className: "badge badge-neutral" },
};

function channels(list: string[]): string {
  if (list.length === ALL_CHANNELS.length && ALL_CHANNELS.every((c) => list.includes(c))) return "All";
  return list.map((c) => SHORT[c] ?? c).join(", ");
}

// "৳20,000 / 7d" (mockup), in the campaign's own currency (SPEC-FE-048).
function budget(c: CampaignListItem): string {
  const money = formatMoney(c.budget, c.currency, { whole: true });
  return c.duration_days === null ? money : `${money} / ${c.duration_days}d`;
}

function MessageRow({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <tr>
      <td colSpan={COLUMN_COUNT} className={className}>
        {children}
      </td>
    </tr>
  );
}

// Marketing "Active Campaigns" table (backend SPEC-BE-038), markup from the
// reference mockup. ROAS is always "—": the backend has no revenue data to
// compute it and never estimates one.
export default function CampaignsTable() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: marketingListKeys.campaigns, queryFn: fetchCampaigns });
  // Pause / Resume (SPEC-FE-032). Afterwards the list and the campaign metrics
  // (all under the "marketing" key prefix, shared with the Dashboard card) refetch.
  const toggle = useMutation({
    mutationFn: (c: CampaignListItem) => setCampaignRunning(c.id, c.status === "paused" ? "resume" : "pause"),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: marketingKeys.all }),
  });
  const toggleError =
    isRoleDenied(toggle.error)
      ? "Only managers and above can pause or resume campaigns."
      : toggle.error?.message;
  return (
    <>
      <h2 className="section-title">
        Active Campaigns
        {/* SPEC-FE-058: opens Ad Manager (where Paid's "+ New campaign" goes) in a new tab. */}
        <Link href={newTabHref("/marketing/paid/ad-manager")} target="_blank" rel="noopener" className="btn no-underline">
          + New Campaign
        </Link>
      </h2>
      <div className="card" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>Campaign</th>
              <th>Objective</th>
              <th>Channels</th>
              <th>Budget</th>
              <th>ROAS</th>
              <th>Status</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {query.isPending ? (
              <MessageRow className="text-muted">Loading campaigns…</MessageRow>
            ) : query.isError ? (
              <MessageRow className="text-danger">Failed to load campaigns: {query.error.message}</MessageRow>
            ) : query.data.length === 0 ? (
              <MessageRow className="text-muted">No active campaigns</MessageRow>
            ) : (
              query.data.map((c) => {
                const badge = STATUS_BADGES[c.status] ?? { label: c.status, className: "badge badge-neutral" };
                return (
                  <tr key={c.id}>
                    <td>{c.name}</td>
                    <td className="capitalize">{c.objective.replace("_", " ")}</td>
                    <td>{channels(c.channels)}</td>
                    <td>{budget(c)}</td>
                    <td>{c.roas === null ? "—" : <b>{formatNumber(c.roas)}x</b>}</td>
                    <td>
                      <span className={badge.className}>{badge.label}</span>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        disabled={toggle.isPending && toggle.variables?.id === c.id}
                        onClick={() => toggle.mutate(c)}
                      >
                        {c.status === "paused" ? "Resume" : "Pause"}
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
      {toggle.isError && (
        <p className="mb-0 mt-3 text-xs text-danger" role="alert">
          {toggleError}
        </p>
      )}
    </>
  );
}
