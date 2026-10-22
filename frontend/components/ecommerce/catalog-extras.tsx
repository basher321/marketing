"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { errorText } from "@/components/organic/shared";
import { formatWhen } from "@/components/orders/status";
import { createCategory, ecommerceKeys, fetchCategories, renameCategory, saveBusinessType } from "@/lib/api/ecommerce";
import { fetchPayments, orderKeys, setPayment } from "@/lib/api/orders";
import { formatMoney } from "@/lib/format/money";
import type { BusinessType, EcommerceConfig } from "@/lib/types/ecommerce";
import type { PaymentStatus } from "@/lib/types/orders";

const INPUT = "rounded-md border border-border bg-panel px-3 py-2 text-[13.5px] text-text";

// Business type picker (SPEC-FE-075): the backend's suggestion and its reasons, or
// "Tell us what you sell". Only PUT /ecommerce/config confirms (manager+).
export function BusinessTypePicker({ config, compact = false }: { config: EcommerceConfig; compact?: boolean }) {
  const queryClient = useQueryClient();
  const [choice, setChoice] = useState<BusinessType>(config.suggestion.type ?? config.business_type);
  const save = useMutation({
    mutationFn: () => saveBusinessType(choice),
    onSuccess: (next) => queryClient.setQueryData(ecommerceKeys.config, next),
  });
  return (
    <div className={compact ? "" : "card mb-4"}>
      {!compact && (
        <>
          <h3 className="mt-0">{config.suggestion.type ? "Is this what you sell?" : "Tell us what you sell"}</h3>
          {config.suggestion.type ? (
            <p className="text-[13px] text-muted">
              We suggest <strong>{config.types.find((t) => t.key === config.suggestion.type)?.label}</strong> because:{" "}
              {config.suggestion.reasons.join(" ")} Confirm it or pick another; the tabs and product fields follow your choice.
            </p>
          ) : (
            <p className="text-[13px] text-muted">
              We couldn&apos;t tell from your data yet. Choose one; the tabs and product fields follow your choice.
            </p>
          )}
        </>
      )}
      <div className="my-3 grid gap-2" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))" }}>
        {config.types.map((t) => (
          <label
            key={t.key}
            className={`cursor-pointer rounded-md border p-3 text-[13px] ${choice === t.key ? "border-accent bg-accent-soft" : "border-border"}`}
          >
            <input
              type="radio"
              name="business-type"
              className="mr-2"
              checked={choice === t.key}
              onChange={() => setChoice(t.key)}
            />
            <strong>{t.label}</strong>
            <div className="mt-1 text-muted">{t.description}</div>
          </label>
        ))}
      </div>
      <button type="button" className="btn" disabled={save.isPending} onClick={() => save.mutate()}>
        {save.isPending ? "Saving…" : config.confirmed ? "Change business type" : "Confirm"}
      </button>
      {compact && <p className="mt-2 text-[12.5px] text-muted">Tabs change; no data is deleted.</p>}
      {save.isError && <p className="mt-2 text-danger">{errorText(save.error, "Ask a manager or the owner to choose the business type.")}</p>}
    </div>
  );
}

// Categories tab (SPEC-FE-075 / SPEC-BE-111 FR6): list, add, rename.
export function Categories() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ecommerceKeys.categories, queryFn: fetchCategories });
  const [name, setName] = useState("");
  const [editing, setEditing] = useState<{ id: string; name: string } | null>(null);
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ecommerceKeys.categories });
  const add = useMutation({ mutationFn: () => createCategory(name.trim()), onSuccess: () => { setName(""); refresh(); } });
  const rename = useMutation({
    mutationFn: (c: { id: string; name: string }) => renameCategory(c.id, c.name.trim()),
    onSuccess: () => { setEditing(null); refresh(); },
  });
  return (
    <>
      <form
        className="mb-4 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim()) add.mutate();
        }}
      >
        <input className={`${INPUT} w-64`} placeholder="New category name" maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
        <button type="submit" className="btn" disabled={!name.trim() || add.isPending}>+ Add category</button>
      </form>
      {add.isError && <p className="mb-2 text-danger">{errorText(add.error)}</p>}
      {rename.isError && <p className="mb-2 text-danger">{errorText(rename.error)}</p>}
      <div className="card" style={{ padding: 0 }}>
        <table>
          <thead><tr><th>Category</th><th>Products</th><th aria-label="Actions" /></tr></thead>
          <tbody>
            {query.isPending ? (
              <tr><td colSpan={3} className="text-muted">Loading…</td></tr>
            ) : query.isError ? (
              <tr><td colSpan={3} className="text-danger">{query.error.message}</td></tr>
            ) : query.data.length === 0 ? (
              <tr><td colSpan={3} className="text-muted">No categories yet</td></tr>
            ) : (
              query.data.map((c) => (
                <tr key={c.id}>
                  <td>
                    {editing?.id === c.id ? (
                      <input className={INPUT} aria-label="Category name" value={editing.name} onChange={(e) => setEditing({ id: c.id, name: e.target.value })} />
                    ) : (
                      c.name
                    )}
                  </td>
                  <td>{c.product_count}</td>
                  <td>
                    {editing?.id === c.id ? (
                      <button type="button" className="btn btn-sm" disabled={!editing.name.trim() || rename.isPending} onClick={() => rename.mutate(editing)}>Save</button>
                    ) : (
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditing({ id: c.id, name: c.name })}>Rename</button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

const PAY_LABEL: Record<string, string> = { unpaid: "Unpaid", paid: "Paid", cod: "Cash on delivery", refunded: "Refunded" };

// Payments tab (SPEC-FE-075 / SPEC-BE-111 FR7): orders by payment status, with
// "Mark paid" / "Refunded" and an optional reference (e.g. a bKash transaction id).
export function Payments() {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<PaymentStatus | null>(null);
  const [offset, setOffset] = useState(0);
  const query = useQuery({ queryKey: orderKeys.payments(status, offset), queryFn: () => fetchPayments(status, offset) });
  const mark = useMutation({
    mutationFn: (x: { id: string; to: PaymentStatus; reference?: string }) =>
      setPayment(x.id, { payment_status: x.to, ...(x.reference ? { reference: x.reference } : {}) }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: orderKeys.all }),
  });
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select
          aria-label="Filter by payment status"
          className={INPUT}
          value={status ?? ""}
          onChange={(e) => { setStatus((e.target.value || null) as PaymentStatus | null); setOffset(0); }}
        >
          <option value="">All payments</option>
          {Object.entries(PAY_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        {query.data && (
          <span className="text-[13px] text-muted">
            {Object.entries(query.data.sums).map(([k, v]) => `${PAY_LABEL[k] ?? k}: ${formatMoney(v, query.data.items[0]?.currency ?? "USD")}`).join(" · ")}
          </span>
        )}
      </div>
      {mark.isError && <p className="mb-2 text-danger">{errorText(mark.error)}</p>}
      <div className="card" style={{ padding: 0 }}>
        <table>
          <thead><tr><th>Order</th><th>Date</th><th>Customer</th><th>Method</th><th>Payment</th><th>Reference</th><th>Total</th><th aria-label="Actions" /></tr></thead>
          <tbody>
            {query.isPending ? (
              <tr><td colSpan={8} className="text-muted">Loading…</td></tr>
            ) : query.isError ? (
              <tr><td colSpan={8} className="text-danger">{query.error.message}</td></tr>
            ) : query.data.items.length === 0 ? (
              <tr><td colSpan={8} className="text-muted">No payments here</td></tr>
            ) : (
              query.data.items.map((p) => (
                <tr key={p.order_id}>
                  <td><a href={`/orders/${p.order_id}`} className="text-accent">#{p.order_number}</a></td>
                  <td>{formatWhen(p.placed_at)}</td>
                  <td>{p.customer_name ?? "Guest"}</td>
                  <td>{p.payment_method ?? "—"}</td>
                  <td>{PAY_LABEL[p.payment_status ?? "unpaid"] ?? p.payment_status}</td>
                  <td>{p.reference ?? "—"}</td>
                  <td>{formatMoney(p.total, p.currency)}</td>
                  <td className="flex gap-1">
                    {p.payment_status !== "paid" && (
                      <button
                        type="button"
                        className="btn btn-sm"
                        disabled={mark.isPending}
                        onClick={() => {
                          const reference = window.prompt("Payment reference (optional, e.g. bKash TrxID)") ?? undefined;
                          mark.mutate({ id: p.order_id, to: "paid", reference: reference?.trim() || undefined });
                        }}
                      >
                        Mark paid
                      </button>
                    )}
                    {p.payment_status === "paid" && (
                      <button type="button" className="btn btn-secondary btn-sm" disabled={mark.isPending} onClick={() => mark.mutate({ id: p.order_id, to: "refunded" })}>
                        Refunded
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {query.data && query.data.total > 25 && (
        <div className="mt-3 flex justify-end gap-2">
          <button type="button" className="btn btn-secondary btn-sm" disabled={offset === 0} onClick={() => setOffset((o) => o - 25)}>Prev</button>
          <button type="button" className="btn btn-secondary btn-sm" disabled={offset + 25 >= query.data.total} onClick={() => setOffset((o) => o + 25)}>Next</button>
        </div>
      )}
    </>
  );
}
