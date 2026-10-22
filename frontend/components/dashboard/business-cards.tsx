"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { fetchProfitLoss, profitLossKey } from "@/lib/api/analytics";
import { fetchInboxConversations, inboxKeys } from "@/lib/api/inbox";
import { fetchScheduledPostCount, marketingKeys } from "@/lib/api/marketing";
import { fetchOrders, orderKeys } from "@/lib/api/orders";
import { fetchSocialAccounts, socialKeys } from "@/lib/api/social";
import { formatMoney } from "@/lib/format/money";
import type { InboxFilters } from "@/lib/types/inbox";

function Card({ href, title, value, sub, tone }: { href: string; title: string; value: string; sub?: string; tone?: "danger" | "success" }) {
  return (
    <Link href={href} className="card block no-underline hover:border-accent">
      <p className="card-title">{title}</p>
      <p className={`card-value ${value === "—" ? "text-muted" : tone === "danger" ? "text-danger" : tone === "success" ? "text-success" : ""}`}>{value}</p>
      {sub && <p className="mt-1.5 text-xs text-muted">{sub}</p>}
    </Link>
  );
}

const UNREAD: InboxFilters = { channel: "all", q: "", status: "", unread: true, mine: false };

// Dashboard business cards (SPEC-FE-078): each opens its page. Numbers are the
// backend's; a figure that can't be computed shows "—" with the reason.
export default function BusinessCards() {
  const accounts = useQuery({ queryKey: socialKeys.accounts, queryFn: fetchSocialAccounts, staleTime: 60_000 });
  const scheduled = useQuery({ queryKey: marketingKeys.scheduledPostCount, queryFn: fetchScheduledPostCount });
  const waitingParams = { status: "awaiting_confirmation" as const, q: "", limit: 1, offset: 0 };
  const pendingParams = { status: "pending" as const, q: "", limit: 1, offset: 0 };
  const waiting = useQuery({ queryKey: orderKeys.list(waitingParams), queryFn: () => fetchOrders(waitingParams) });
  const pending = useQuery({ queryKey: orderKeys.list(pendingParams), queryFn: () => fetchOrders(pendingParams) });
  const unread = useQuery({ queryKey: inboxKeys.list(UNREAD), queryFn: () => fetchInboxConversations(UNREAD) });
  const pl = useQuery({ queryKey: profitLossKey({ range: "mtd" }), queryFn: () => fetchProfitLoss({ range: "mtd" }) });

  const items = accounts.data?.items ?? [];
  const connected = items.filter((a) => a.status === "connected").length;
  const attention = items.filter((a) => a.status !== "connected" && a.status !== "not_connected").length;
  const unreadCount = unread.data ? unread.data.items.length : null;
  const r = pl.data;
  const money = (v: number) => (r ? formatMoney(v, r.currency) : "—");
  return (
    <>
      <div className="grid-3">
        <Card href="/marketing/organic/accounts" title="Connected accounts"
          value={accounts.isSuccess ? String(connected) : "—"}
          sub={attention ? `${attention} need attention` : accounts.isError ? "Couldn't load" : "Social accounts"} tone={attention ? "danger" : undefined} />
        <Card href="/marketing/organic/calendar" title="Scheduled posts" value={scheduled.data ? String(scheduled.data.pending) : "—"} sub="Waiting to publish" />
        <Card href="/chat?tab=inbox" title="Messages to answer"
          value={unreadCount === null ? "—" : `${unreadCount}${unread.data?.next_cursor ? "+" : ""}`}
          sub="Unread conversations" />
        <Card href="/orders?status=awaiting_confirmation" title="Waiting for confirmation" value={waiting.data ? String(waiting.data.total) : "—"} sub="Customer hasn't replied to the SMS" />
        <Card href="/orders?status=pending" title="New orders" value={pending.data ? String(pending.data.total) : "—"} sub="Placed, confirmation not sent" />
        <Card href="/analytics?tab=profit-loss" title={r && r.profit < 0 ? "Loss this month" : "Profit this month"}
          value={r ? `${r.profit < 0 ? "−" : ""}${money(Math.abs(r.profit))}` : "—"}
          sub={r ? `Sales ${money(r.revenue.net)} · costs ${money(r.costs.total)}${r.complete ? "" : " · incomplete costs"}` : pl.isError ? "Couldn't load" : undefined}
          tone={r ? (r.profit < 0 ? "danger" : "success") : undefined} />
      </div>
    </>
  );
}
