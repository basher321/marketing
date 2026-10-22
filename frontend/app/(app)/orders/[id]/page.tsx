"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { use, useState } from "react";

import { errorText } from "@/components/organic/shared";
import {
  ConfirmationBadge,
  StageTracker,
  StatusBadge,
  actorText,
  formatWhen,
  statusLabel,
} from "@/components/orders/status";
import { customerKeys } from "@/lib/api/customers";
import { changeOrderStatus, fetchOrder, orderKeys, sendConfirmationSms } from "@/lib/api/orders";
import { formatMoney } from "@/lib/format/money";
import type { OrderDetail, OrderStatus } from "@/lib/types/orders";

const INPUT = "w-full rounded-md border border-border bg-panel px-3 py-2 text-[13.5px] text-text";

// Button text per target status (only `allowed_next` from the backend is shown).
const ACTION_LABEL: Record<string, string> = {
  confirmed: "Mark confirmed",
  processing: "Start processing",
  shipped: "Mark shipped",
  delivered: "Mark delivered",
  returned: "Mark returned",
  cancelled: "Cancel order",
  refunded: "Mark refunded",
};

function StatusActions({ order }: { order: OrderDetail }) {
  const queryClient = useQueryClient();
  const [target, setTarget] = useState<OrderStatus | null>(null);
  const [reason, setReason] = useState("");
  const [tracking, setTracking] = useState(order.tracking_number ?? "");
  const [trackingUrl, setTrackingUrl] = useState(order.tracking_url ?? "");
  const change = useMutation({
    mutationFn: (to: OrderStatus) =>
      changeOrderStatus(order.id, {
        to,
        ...(reason.trim() ? { reason: reason.trim() } : {}),
        ...(to === "shipped" && tracking.trim() ? { tracking_number: tracking.trim() } : {}),
        ...(to === "shipped" && trackingUrl.trim() ? { tracking_url: trackingUrl.trim() } : {}),
      }),
    onSuccess: (o) => {
      queryClient.setQueryData(orderKeys.detail(order.id), o);
      void queryClient.invalidateQueries({ queryKey: orderKeys.all });
      void queryClient.invalidateQueries({ queryKey: customerKeys.all });
      setTarget(null);
      setReason("");
    },
  });
  if (order.allowed_next.length === 0) {
    return <p className="text-muted">No further status changes are available for you on this order.</p>;
  }
  const needsReason = target === "cancelled" || target === "returned";
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        {order.allowed_next.map((to) => (
          <button
            key={to}
            type="button"
            className={to === "cancelled" || to === "returned" || to === "refunded" ? "btn btn-secondary" : "btn"}
            aria-pressed={target === to}
            onClick={() => setTarget(to)}
          >
            {ACTION_LABEL[to] ?? statusLabel(to)}
          </button>
        ))}
      </div>
      {target && (
        <form
          className="flex flex-col gap-2 rounded-md border border-border p-3"
          onSubmit={(e) => {
            e.preventDefault();
            change.mutate(target);
          }}
        >
          <p>
            Change to <StatusBadge status={target} />
          </p>
          {target === "shipped" && (
            <div className="grid grid-cols-2 gap-2">
              <input className={INPUT} placeholder="Tracking number" value={tracking} onChange={(e) => setTracking(e.target.value)} />
              <input className={INPUT} placeholder="Tracking link" value={trackingUrl} onChange={(e) => setTrackingUrl(e.target.value)} />
            </div>
          )}
          <textarea
            className={INPUT}
            rows={2}
            placeholder={needsReason ? "Reason (required)" : "Note (optional)"}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          {change.isError && <p className="text-danger">{errorText(change.error)}</p>}
          <div className="flex gap-2">
            <button type="submit" className="btn" disabled={change.isPending || (needsReason && !reason.trim())}>
              {change.isPending ? "Saving…" : "Confirm"}
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => setTarget(null)}>
              Back
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

function SmsCard({ order }: { order: OrderDetail }) {
  const queryClient = useQueryClient();
  const send = useMutation({
    mutationFn: () => sendConfirmationSms(order.id),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: orderKeys.detail(order.id) });
      void queryClient.invalidateQueries({ queryKey: orderKeys.all });
    },
  });
  const c = order.confirmation;
  const sms = [...(c.last_sms ? [c.last_sms] : []), ...c.replies].sort((a, b) => a.at.localeCompare(b.at));
  return (
    <div className="card">
      <div className="card-title">Customer confirmation (SMS)</div>
      <p className="mb-2">
        Reply position: <ConfirmationBadge state={c.state} />{" "}
        <span className="text-muted">({c.sms_count} SMS sent)</span>
      </p>
      {c.last_sms && (
        <p className="mb-2 text-[13px]">
          Last SMS: <strong>{c.last_sms.status}</strong> · {formatWhen(c.last_sms.at)}
          {c.last_sms.error && <span className="text-danger"> · {c.last_sms.error}</span>}
        </p>
      )}
      {sms.length > 0 && (
        <ul className="mb-3 flex flex-col gap-1 text-[13px]">
          {sms.map((m) => (
            <li key={m.id} className={m.direction === "inbound" ? "rounded-md bg-accent-soft px-2 py-1" : "px-2 py-1"}>
              <span className="text-muted">{m.direction === "inbound" ? "Customer" : "Sent"} · {formatWhen(m.at)}:</span> {m.body}
              {m.interpreted && <span className="text-muted"> ({m.interpreted})</span>}
            </li>
          ))}
        </ul>
      )}
      <button type="button" className="btn btn-secondary" disabled={!c.can_send || send.isPending} onClick={() => send.mutate()}>
        {send.isPending ? "Sending…" : c.sms_count ? "Send a follow-up SMS" : "Send confirmation SMS"}
      </button>
      {!c.can_send && c.send_blocked_reason && <p className="mt-2 text-[13px] text-muted">{c.send_blocked_reason}</p>}
      {send.isError && <p className="mt-2 text-danger">{errorText(send.error)}</p>}
    </div>
  );
}

// Order detail (SPEC-FE-073): items, totals, customer, stage tracker, status
// actions from `allowed_next`, the confirmation SMS and the status history.
export default function OrderPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const query = useQuery({ queryKey: orderKeys.detail(id), queryFn: () => fetchOrder(id), refetchInterval: 20_000 });
  if (query.isPending) return <p className="text-muted">Loading order…</p>;
  if (query.isError) return <p className="text-danger">Couldn&apos;t load this order: {query.error.message}</p>;
  const o = query.data;
  const money = (v: number) => formatMoney(v, o.currency);
  const addr = Object.values(o.shipping_address ?? {}).filter((v) => typeof v === "string" && v).join(", ");
  return (
    <>
      <p className="mb-2 text-[13px]">
        <Link href="/orders" className="text-accent">← Orders</Link>
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="page-title">Order #{o.order_number}</h1>
        <StatusBadge status={o.status} />
      </div>
      <p className="page-subtitle">
        Placed {formatWhen(o.placed_at)} · {o.channel} · {o.payment_method ?? "—"} · payment {o.payment_status ?? "—"}
      </p>
      <div className="card mb-4">
        <StageTracker status={o.status} history={o.status_history} />
      </div>
      <div className="grid-2">
        <div className="flex flex-col gap-4">
          <div className="card" style={{ padding: 0 }}>
            <table>
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Qty</th>
                  <th>Price</th>
                  <th>Total</th>
                </tr>
              </thead>
              <tbody>
                {o.items.map((it) => (
                  <tr key={it.id}>
                    <td>
                      {it.title ?? "—"} <span className="text-muted">{it.sku}{it.variant ? ` · ${it.variant}` : ""}</span>
                    </td>
                    <td>{it.quantity}</td>
                    <td>{money(it.unit_price)}</td>
                    <td>{money(it.line_total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="px-4 py-3 text-[13px]">
              {[["Subtotal", o.subtotal], ["Discount", -o.discount], ["Shipping", o.shipping], ["Tax", o.tax]].map(([l, v]) => (
                <div key={l as string} className="flex justify-between text-muted">
                  <span>{l}</span>
                  <span>{money(v as number)}</span>
                </div>
              ))}
              <div className="mt-1 flex justify-between font-semibold">
                <span>Total</span>
                <span>{money(o.total)}</span>
              </div>
            </div>
          </div>
          <div className="card">
            <div className="card-title">Change status</div>
            <StatusActions order={o} />
            {o.tracking_number && (
              <p className="mt-3 text-[13px]">
                Tracking: {o.tracking_url ? <a href={o.tracking_url} target="_blank" rel="noreferrer" className="text-accent">{o.tracking_number}</a> : o.tracking_number}
              </p>
            )}
          </div>
        </div>
        <div className="flex flex-col gap-4">
          <div className="card">
            <div className="card-title">Customer</div>
            {o.customer ? (
              <>
                <p className="font-semibold">
                  <Link href={`/customers/${o.customer.id}`} className="text-accent">{o.customer.name ?? o.customer.phone ?? o.customer.email}</Link>
                </p>
                <p className="text-[13px] text-muted">{[o.customer.phone, o.customer.email].filter(Boolean).join(" · ")}</p>
                {addr && <p className="mt-1 text-[13px]">{addr}</p>}
              </>
            ) : (
              <p className="text-muted">Guest</p>
            )}
            {o.notes && <p className="mt-2 text-[13px]">Note: {o.notes}</p>}
          </div>
          <SmsCard order={o} />
          <div className="card">
            <div className="card-title">Status history</div>
            <ul className="flex flex-col gap-2 text-[13px]">
              {o.status_history.map((e) => (
                <li key={e.id}>
                  <span className="text-muted">{formatWhen(e.at)}</span> · {e.from_status ? `${statusLabel(e.from_status)} → ` : ""}
                  <strong>{statusLabel(e.to_status)}</strong> · {actorText(e)}
                  {e.reason && <span className="text-muted"> — {e.reason}</span>}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </>
  );
}
