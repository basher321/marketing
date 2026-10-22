"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { use, useState } from "react";

import { errorText } from "@/components/organic/shared";
import { ConfirmationBadge, StatusBadge, actorText, formatWhen, statusLabel } from "@/components/orders/status";
import { customerKeys, fetchCustomer, updateCustomer } from "@/lib/api/customers";
import { formatMoney } from "@/lib/format/money";
import type { CustomerProfile } from "@/lib/types/customers";

const INPUT = "w-full rounded-md border border-border bg-panel px-3 py-2 text-[13.5px] text-text";

function ProfileEditor({ c, onDone }: { c: CustomerProfile; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [first, setFirst] = useState(c.first_name ?? "");
  const [last, setLast] = useState(c.last_name ?? "");
  const [phone, setPhone] = useState(c.phone ?? "");
  const [email, setEmail] = useState(c.email ?? "");
  const [line1, setLine1] = useState(c.address?.line1 ?? "");
  const [city, setCity] = useState(c.city ?? c.address?.city ?? "");
  const save = useMutation({
    mutationFn: () =>
      updateCustomer(c.id, {
        first_name: first.trim(),
        last_name: last.trim(),
        phone: phone.trim() || null,
        email: email.trim() || null,
        address: line1.trim() ? { line1: line1.trim(), ...(city.trim() ? { city: city.trim() } : {}) } : null,
        city: city.trim(),
      }),
    onSuccess: (rec) => {
      queryClient.setQueryData(customerKeys.record(c.id), rec);
      void queryClient.invalidateQueries({ queryKey: customerKeys.all });
      onDone();
    },
  });
  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <div className="grid grid-cols-2 gap-2">
        <input className={INPUT} aria-label="First name" placeholder="First name" value={first} onChange={(e) => setFirst(e.target.value)} />
        <input className={INPUT} aria-label="Last name" placeholder="Last name" value={last} onChange={(e) => setLast(e.target.value)} />
        <input className={INPUT} aria-label="Phone" placeholder="Phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
        <input className={INPUT} aria-label="Email" placeholder="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      </div>
      <input className={INPUT} aria-label="Address" placeholder="Address" value={line1} onChange={(e) => setLine1(e.target.value)} />
      <input className={INPUT} aria-label="City" placeholder="City" value={city} onChange={(e) => setCity(e.target.value)} />
      {save.isError && <p className="text-danger">{errorText(save.error)}</p>}
      <div className="flex gap-2">
        <button type="submit" className="btn" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save"}</button>
        <button type="button" className="btn btn-secondary" onClick={onDone}>Cancel</button>
      </div>
    </form>
  );
}

// Customer record (SPEC-FE-073 / SPEC-BE-109): profile, current order with its
// badge and SMS position, order history, status history, SMS and conversations.
export default function CustomerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [editing, setEditing] = useState(false);
  const query = useQuery({ queryKey: customerKeys.record(id), queryFn: () => fetchCustomer(id) });
  if (query.isPending) return <p className="text-muted">Loading customer…</p>;
  if (query.isError) return <p className="text-danger">Couldn&apos;t load this customer: {query.error.message}</p>;
  const { customer: c, current_order: current, orders, status_history: history, sms, conversations } = query.data;
  const address = [c.address?.line1, c.city ?? c.address?.city].filter(Boolean).join(", ");
  return (
    <>
      <p className="mb-2 text-[13px]">
        <Link href="/customers" className="text-accent">← Customers</Link>
      </p>
      <h1 className="page-title">{c.name ?? c.phone ?? c.email ?? "Customer"}</h1>
      <p className="page-subtitle">
        {c.order_count} order(s) · lifetime value {formatMoney(c.lifetime_value, c.currency)}
        {c.sms_opt_out && " · opted out of SMS"}
      </p>
      <div className="grid-2">
        <div className="flex flex-col gap-4">
          <div className="card">
            <div className="card-title flex items-center justify-between">
              <span>Profile</span>
              {!editing && (
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditing(true)}>Edit</button>
              )}
            </div>
            {editing ? (
              <ProfileEditor c={c} onDone={() => setEditing(false)} />
            ) : (
              <dl className="grid grid-cols-[110px_1fr] gap-y-1 text-[13.5px]">
                <dt className="text-muted">Phone</dt><dd>{c.phone ?? "—"}</dd>
                <dt className="text-muted">Email</dt><dd>{c.email ?? "—"}</dd>
                <dt className="text-muted">Address</dt><dd>{address || "—"}</dd>
                <dt className="text-muted">Customer since</dt><dd>{formatWhen(c.created_at)}</dd>
              </dl>
            )}
          </div>
          <div className="card">
            <div className="card-title">Current order</div>
            {current ? (
              <p>
                <Link href={`/orders/${current.id}`} className="font-semibold text-accent">#{current.order_number}</Link>{" "}
                <StatusBadge status={current.status} /> SMS: <ConfirmationBadge state={current.confirmation_state} />
              </p>
            ) : (
              <p className="text-muted">No open order.</p>
            )}
          </div>
          <div className="card" style={{ padding: 0 }}>
            <div className="card-title px-4 pt-4">Order history</div>
            <table>
              <thead>
                <tr><th>Order</th><th>Placed</th><th>Total</th><th>SMS</th><th>Status</th><th>Delivery</th></tr>
              </thead>
              <tbody>
                {orders.length === 0 ? (
                  <tr><td colSpan={6} className="text-muted">No orders yet</td></tr>
                ) : (
                  orders.map((o) => (
                    <tr key={o.id}>
                      <td><Link href={`/orders/${o.id}`} className="text-accent">#{o.order_number}</Link></td>
                      <td>{formatWhen(o.placed_at)}</td>
                      <td>{formatMoney(o.total, o.currency)}</td>
                      <td><ConfirmationBadge state={o.confirmation_state} /></td>
                      <td><StatusBadge status={o.status} /></td>
                      <td>{o.tracking_url ? <a href={o.tracking_url} target="_blank" rel="noreferrer" className="text-accent">{o.tracking_number}</a> : (o.tracking_number ?? "—")}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
        <div className="flex flex-col gap-4">
          <div className="card">
            <div className="card-title">Status history</div>
            {history.length === 0 ? (
              <p className="text-muted">Nothing yet.</p>
            ) : (
              <ul className="flex flex-col gap-1 text-[13px]">
                {history.map((e) => (
                  <li key={e.id}>
                    <span className="text-muted">{formatWhen(e.at)}</span> · #{e.order_number}:{" "}
                    {e.from_status ? `${statusLabel(e.from_status)} → ` : ""}<strong>{statusLabel(e.to_status)}</strong> · {actorText(e)}
                    {e.reason && <span className="text-muted"> — {e.reason}</span>}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="card">
            <div className="card-title">SMS confirmation history</div>
            {sms.length === 0 ? (
              <p className="text-muted">No SMS yet.</p>
            ) : (
              <ul className="flex flex-col gap-1 text-[13px]">
                {sms.map((m) => (
                  <li key={m.id} className={m.direction === "inbound" ? "rounded-md bg-accent-soft px-2 py-1" : "px-2 py-1"}>
                    <span className="text-muted">
                      {formatWhen(m.at)} · {m.direction === "inbound" ? "Customer" : `Sent (${m.status})`}
                      {m.order_number ? ` · #${m.order_number}` : ""}:
                    </span>{" "}
                    {m.body}
                    {m.interpreted && <span className="text-muted"> ({m.interpreted})</span>}
                    {m.error && <span className="text-danger"> · {m.error}</span>}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="card">
            <div className="card-title">Conversations</div>
            {conversations.length === 0 ? (
              <p className="text-muted">No conversations yet.</p>
            ) : (
              <ul className="flex flex-col gap-2 text-[13px]">
                {conversations.map((cv) => (
                  <li key={cv.id}>
                    <Link href={`/chat?tab=inbox&conv=${encodeURIComponent(`local:${cv.id}`)}`} className="text-accent">
                      {cv.channel} · {cv.topic ?? "Conversation"}
                    </Link>{" "}
                    <span className="text-muted">{cv.status} · {formatWhen(cv.last_message_at)}</span>
                    {cv.unread > 0 && <span className="badge badge-warn ml-1">{cv.unread} new</span>}
                    {cv.last_message && <div className="text-muted">{cv.last_message}</div>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
