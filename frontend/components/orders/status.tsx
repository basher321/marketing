"use client";

import type { ConfirmationState, OrderStatus, StatusEvent } from "@/lib/types/orders";

// Badge per live order_status (SPEC-FE-026, SPEC-FE-073): waiting -> neutral,
// being worked on -> warn, on its way / done -> success, cancelled / returned /
// refunded -> danger. An unknown value renders as plain text, never an invented badge.
export const STATUS_BADGES: Record<OrderStatus, { label: string; className: string }> = {
  pending: { label: "Placed", className: "badge badge-neutral" },
  awaiting_confirmation: { label: "Waiting for confirmation", className: "badge badge-warn" },
  confirmed: { label: "Confirmed", className: "badge badge-success" },
  processing: { label: "Processing", className: "badge badge-warn" },
  shipped: { label: "Shipped", className: "badge badge-success" },
  delivered: { label: "Delivered", className: "badge badge-success" },
  returned: { label: "Returned", className: "badge badge-danger" },
  cancelled: { label: "Cancelled", className: "badge badge-danger" },
  refunded: { label: "Refunded", className: "badge badge-danger" },
};

export function statusLabel(status: string): string {
  return STATUS_BADGES[status as OrderStatus]?.label ?? status;
}

export function StatusBadge({ status }: { status: string }) {
  const badge = STATUS_BADGES[status as OrderStatus];
  return badge ? <span className={badge.className}>{badge.label}</span> : <span>{status}</span>;
}

// The SMS reply position (SPEC-BE-107 FR7): text + colour, never colour alone.
const CONFIRMATION: Record<ConfirmationState, { label: string; className: string }> = {
  not_sent: { label: "SMS not sent", className: "badge badge-neutral" },
  waiting: { label: "Waiting", className: "badge badge-warn" },
  confirmed: { label: "Confirmed", className: "badge badge-success" },
  cancelled: { label: "Cancelled", className: "badge badge-danger" },
};

export function ConfirmationBadge({ state }: { state: ConfirmationState }) {
  const c = CONFIRMATION[state];
  return <span className={c.className}>{c.label}</span>;
}

// Stage tracker (SPEC-FE-073): Placed → SMS sent → Customer reply → Processing →
// Shipped → Delivered, with the Returned / Cancelled branches. A stage is done
// when the history reached it.
const STAGES: { key: string; label: string; reached: OrderStatus[] }[] = [
  { key: "placed", label: "Placed", reached: ["pending"] },
  { key: "sms", label: "SMS sent", reached: ["awaiting_confirmation"] },
  { key: "reply", label: "Confirmed", reached: ["confirmed"] },
  { key: "processing", label: "Processing", reached: ["processing"] },
  { key: "shipped", label: "Shipped", reached: ["shipped"] },
  { key: "delivered", label: "Delivered", reached: ["delivered"] },
];

export function StageTracker({ status, history }: { status: OrderStatus; history: StatusEvent[] }) {
  const seen = new Set<string>(history.map((e) => e.to_status));
  seen.add(status);
  const order: OrderStatus[] = ["pending", "awaiting_confirmation", "confirmed", "processing", "shipped", "delivered"];
  const furthest = Math.max(...order.map((s, i) => (seen.has(s) ? i : -1)));
  const branch = status === "cancelled" || status === "returned" || status === "refunded" ? status : null;
  return (
    <div>
      <ol className="flex flex-wrap items-center gap-2 text-[12.5px]" aria-label="Order stages">
        {STAGES.map((s, i) => {
          const done = i <= furthest;
          return (
            <li key={s.key} className="flex items-center gap-2">
              <span
                className={done ? "badge badge-success" : "badge badge-neutral"}
                aria-label={`${s.label}: ${done ? "done" : "not yet"}`}
              >
                {done ? "✓ " : ""}
                {s.label}
              </span>
              {i < STAGES.length - 1 && <span className="text-muted">→</span>}
            </li>
          );
        })}
      </ol>
      {branch && (
        <p className="mt-2 text-[13px]">
          <StatusBadge status={branch} /> <span className="text-muted">after {statusLabel(order[Math.max(furthest, 0)])}</span>
        </p>
      )}
    </div>
  );
}

export function actorText(e: StatusEvent): string {
  if (e.actor_type === "customer_sms") return "Customer by SMS";
  return e.actor_name ?? (e.actor_type === "system" ? "System" : "Someone");
}

// "Oct 21, 14:05" in the viewer's local time.
export function formatWhen(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
}
