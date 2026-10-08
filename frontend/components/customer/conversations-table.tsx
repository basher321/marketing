"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";

import { conversationKeys, fetchConversations } from "@/lib/api/conversations";
import type { InboxItem, InboxStatus } from "@/lib/types/conversations";

const COLUMN_COUNT = 5;

// Mockup channel labels ("IG DM", "WhatsApp", "Messenger", "Email") for the live
// channel_type values; the rest use their plain names.
export const CHANNEL_LABELS: Record<string, string> = {
  instagram: "IG DM",
  whatsapp: "WhatsApp",
  messenger: "Messenger",
  email: "Email",
  facebook: "Facebook",
  tiktok: "TikTok",
  sms: "SMS",
  web: "Web",
};

// Badge per real inbox_status (backend SPEC-BE-007). The mockup's three:
// draft_ready -> warn, auto_replied -> success, escalated -> danger. new and
// replied have no mockup badge; they get the neutral badge (decided in
// SPEC-BE-007), never an invented color.
const STATUS_BADGES: Record<InboxStatus, { label: string; className: string }> = {
  draft_ready: { label: "Draft ready", className: "badge badge-warn" },
  auto_replied: { label: "Auto-replied", className: "badge badge-success" },
  escalated: { label: "Escalated", className: "badge badge-danger" },
  new: { label: "New", className: "badge badge-neutral" },
  replied: { label: "Replied", className: "badge badge-neutral" },
};

/**
 * The mockup shows "Sarah A.": first name + last initial. The backend returns
 * the full name, or an email/phone fallback, which is shown unchanged.
 */
export function displayCustomer(name: string | null): string {
  if (!name) return "—";
  if (name.includes("@") || /^[+\d]/.test(name)) return name;
  const parts = name.trim().split(/\s+/);
  return parts.length > 1 ? `${parts[0]} ${parts[parts.length - 1][0]}.` : parts[0];
}

export function channelLabel(channel: string): string {
  return CHANNEL_LABELS[channel] ?? channel;
}

// "{n}m" under 60 minutes, "{n}h" from 60 minutes (mockup format), computed
// client-side from the customer's latest message time.
function waitingLabel(since: string | null, now: number): string {
  if (!since) return "—";
  const minutes = Math.max(0, Math.floor((now - new Date(since).getTime()) / 60_000));
  return minutes < 60 ? `${minutes}m` : `${Math.floor(minutes / 60)}h`;
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

export type ConversationsTableProps = {
  selectedId: string | null;
  onSelect: (item: InboxItem | null) => void;
};

// Open Conversations card (SPEC-FE-013), markup from the reference mockup.
// Selection is a reasoned UI interpretation of the mockup's two-panel layout:
// clicking a row selects it for the AI Reply Draft panel (SPEC-FE-014), and the
// first row is selected by default (or again if the selected one leaves the list).
export default function ConversationsTable({ selectedId, onSelect }: ConversationsTableProps) {
  const query = useQuery({ queryKey: conversationKeys.list, queryFn: fetchConversations });
  // Re-render every minute so the Waiting column stays current.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(timer);
  }, []);

  const items = query.data?.items;
  useEffect(() => {
    if (!items) return;
    const current = items.find((i) => i.id === selectedId);
    if (current) {
      onSelect(current); // keep the panel's name/channel in sync after a refetch
    } else {
      onSelect(items[0] ?? null);
    }
    // Runs only when the list data changes; onSelect is the page's stable state setter.
  }, [items]);

  return (
    <div className="card" style={{ padding: 0 }}>
      <div className="border-b border-border px-[18px] py-[14px] font-semibold">
        Open Conversations{query.data ? ` (${query.data.count})` : ""}
      </div>
      <table>
        <thead>
          <tr>
            <th>Customer</th>
            <th>Channel</th>
            <th>Topic</th>
            <th>Waiting</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {query.isPending ? (
            <MessageRow className="text-muted">Loading conversations…</MessageRow>
          ) : query.isError ? (
            <MessageRow className="text-danger">
              Failed to load conversations: {query.error.message}
            </MessageRow>
          ) : query.data.items.length === 0 ? (
            <MessageRow className="text-muted">No open conversations</MessageRow>
          ) : (
            query.data.items.map((c) => {
              const selected = c.id === selectedId;
              const badge = STATUS_BADGES[c.inbox_status];
              const cell = selected ? "bg-accent-soft" : undefined;
              return (
                <tr
                  key={c.id}
                  tabIndex={0}
                  aria-selected={selected}
                  className="cursor-pointer"
                  onClick={() => onSelect(c)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelect(c);
                    }
                  }}
                >
                  <td className={cell}>{displayCustomer(c.customer_name)}</td>
                  <td className={cell}>{channelLabel(c.channel)}</td>
                  <td className={cell}>{c.topic ?? "—"}</td>
                  <td className={cell}>{waitingLabel(c.waiting_since, now)}</td>
                  <td className={cell}>
                    <span className={badge.className}>{badge.label}</span>
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
