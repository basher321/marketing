"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useMemo, useRef, useState } from "react";

import { errorText } from "@/components/organic/shared";
import SideSheet from "@/components/ui/side-sheet";
import { customerKeys, fetchCustomers } from "@/lib/api/customers";
import { createOrder, orderKeys } from "@/lib/api/orders";
import { fetchProducts, productKeys } from "@/lib/api/products";
import { formatMoney } from "@/lib/format/money";
import type { OrderCreate } from "@/lib/types/orders";

const INPUT = "w-full rounded-md border border-border bg-panel px-3 py-2 text-[13.5px] text-text";

type Line = { product_id: string; quantity: number; unit_price: string };

// New order (SPEC-FE-073 / SPEC-BE-107 FR3): find a customer or enter a new one,
// add product lines, discount / shipping / tax and payment. The preview is only a
// preview; the server calculates the real total. One Idempotency-Key per open form,
// so a double click never makes two orders.
export default function OrderForm({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const key = useRef(crypto.randomUUID());
  const products = useQuery({ queryKey: productKeys.list, queryFn: fetchProducts });
  const [search, setSearch] = useState("");
  const found = useQuery({
    queryKey: customerKeys.list(search, 0),
    queryFn: () => fetchCustomers(search, 6, 0),
    enabled: search.trim().length >= 2,
  });
  const [customerId, setCustomerId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [address, setAddress] = useState("");
  const [city, setCity] = useState("");
  const [lines, setLines] = useState<Line[]>([{ product_id: "", quantity: 1, unit_price: "" }]);
  const [discount, setDiscount] = useState("");
  const [shipping, setShipping] = useState("");
  const [tax, setTax] = useState("");
  const [paymentMethod, setPaymentMethod] = useState("COD");
  const [paymentStatus, setPaymentStatus] = useState<"unpaid" | "paid" | "cod">("cod");
  const [notes, setNotes] = useState("");

  const sellable = (products.data ?? []).filter((p) => p.status !== "archived");
  const byId = useMemo(() => Object.fromEntries(sellable.map((p) => [p.id, p])), [sellable]);
  const currency = sellable[0]?.currency ?? "USD";
  const num = (v: string) => (v.trim() === "" ? 0 : Number(v));
  const subtotal = lines.reduce((sum, l) => {
    const p = byId[l.product_id];
    const unit = l.unit_price.trim() ? Number(l.unit_price) : (p?.price ?? 0);
    return sum + (p ? unit * l.quantity : 0);
  }, 0);
  const preview = subtotal - num(discount) + num(shipping) + num(tax);

  const save = useMutation({
    mutationFn: () => {
      const addr = address.trim() ? { line1: address.trim(), ...(city.trim() ? { city: city.trim() } : {}) } : undefined;
      const body: OrderCreate = {
        customer: customerId
          ? { id: customerId }
          : {
              ...(name.trim() ? { name: name.trim() } : {}),
              ...(phone.trim() ? { phone: phone.trim() } : {}),
              ...(email.trim() ? { email: email.trim() } : {}),
              ...(addr ? { address: addr } : {}),
            },
        items: lines
          .filter((l) => l.product_id)
          .map((l) => ({
            product_id: l.product_id,
            quantity: l.quantity,
            ...(l.unit_price.trim() ? { unit_price: l.unit_price.trim() } : {}),
          })),
        ...(discount.trim() ? { discount: discount.trim() } : {}),
        ...(shipping.trim() ? { shipping: shipping.trim() } : {}),
        ...(tax.trim() ? { tax: tax.trim() } : {}),
        payment_method: paymentMethod.trim() || undefined,
        payment_status: paymentStatus,
        ...(notes.trim() ? { notes: notes.trim() } : {}),
        ...(addr ? { shipping_address: addr } : {}),
      };
      return createOrder(body, key.current);
    },
    onSuccess: (order) => {
      void queryClient.invalidateQueries({ queryKey: orderKeys.all });
      void queryClient.invalidateQueries({ queryKey: customerKeys.all });
      router.push(`/orders/${order.id}`);
    },
  });

  const canSave =
    (customerId || phone.trim() || email.trim()) && lines.some((l) => l.product_id && l.quantity > 0) && !save.isPending;

  return (
    <SideSheet title="New order" onClose={onClose} wide>
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (canSave) save.mutate();
        }}
      >
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 font-semibold">Customer</legend>
          {customerId ? (
            <div className="flex items-center justify-between rounded-md border border-border px-3 py-2">
              <span>{name || phone || email}</span>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setCustomerId(null)}>
                Change
              </button>
            </div>
          ) : (
            <>
              <input
                className={INPUT}
                placeholder="Find an existing customer (name, phone or email)"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              {found.data && found.data.length > 0 && (
                <ul className="rounded-md border border-border">
                  {found.data.map((c) => (
                    <li key={c.id}>
                      <button
                        type="button"
                        className="w-full px-3 py-2 text-left hover:bg-accent-soft"
                        onClick={() => {
                          setCustomerId(c.id);
                          setName([c.first_name, c.last_name].filter(Boolean).join(" "));
                          setPhone(c.phone ?? "");
                          setEmail(c.email ?? "");
                          setSearch("");
                        }}
                      >
                        {[c.first_name, c.last_name].filter(Boolean).join(" ") || "—"}{" "}
                        <span className="text-muted">{c.phone ?? c.email}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <p className="text-[12.5px] text-muted">Or a new customer (phone or email is required):</p>
              <div className="form-grid-2 grid grid-cols-2 gap-2">
                <input className={INPUT} placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
                <input className={INPUT} placeholder="Mobile number" value={phone} onChange={(e) => setPhone(e.target.value)} />
                <input className={INPUT} placeholder="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
                <input className={INPUT} placeholder="City" value={city} onChange={(e) => setCity(e.target.value)} />
              </div>
              <input className={INPUT} placeholder="Delivery address" value={address} onChange={(e) => setAddress(e.target.value)} />
            </>
          )}
        </fieldset>

        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 font-semibold">Items</legend>
          {products.isError && <p className="text-danger">Couldn&apos;t load products: {products.error.message}</p>}
          {lines.map((l, i) => (
            <div key={i} className="grid grid-cols-[1fr_70px_100px_auto] items-center gap-2">
              <select
                aria-label={`Product ${i + 1}`}
                className={INPUT}
                value={l.product_id}
                onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, product_id: e.target.value } : x)))}
              >
                <option value="">Choose a product…</option>
                {sellable.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title} · {p.sku} · {formatMoney(p.price, p.currency)}
                  </option>
                ))}
              </select>
              <input
                aria-label={`Quantity ${i + 1}`}
                className={INPUT}
                type="number"
                min={1}
                value={l.quantity}
                onChange={(e) =>
                  setLines(lines.map((x, j) => (j === i ? { ...x, quantity: Math.max(1, Number(e.target.value) || 1) } : x)))
                }
              />
              <input
                aria-label={`Price ${i + 1}`}
                className={INPUT}
                placeholder={byId[l.product_id] ? String(byId[l.product_id].price) : "Price"}
                inputMode="decimal"
                value={l.unit_price}
                onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, unit_price: e.target.value } : x)))}
              />
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                aria-label={`Remove line ${i + 1}`}
                disabled={lines.length === 1}
                onClick={() => setLines(lines.filter((_, j) => j !== i))}
              >
                ✕
              </button>
            </div>
          ))}
          <button
            type="button"
            className="btn btn-secondary btn-sm self-start"
            onClick={() => setLines([...lines, { product_id: "", quantity: 1, unit_price: "" }])}
          >
            + Add line
          </button>
        </fieldset>

        <div className="grid grid-cols-3 gap-2">
          <label className="text-[12.5px] text-muted">
            Discount
            <input className={INPUT} inputMode="decimal" value={discount} onChange={(e) => setDiscount(e.target.value)} />
          </label>
          <label className="text-[12.5px] text-muted">
            Shipping charge
            <input className={INPUT} inputMode="decimal" value={shipping} onChange={(e) => setShipping(e.target.value)} />
          </label>
          <label className="text-[12.5px] text-muted">
            Tax
            <input className={INPUT} inputMode="decimal" value={tax} onChange={(e) => setTax(e.target.value)} />
          </label>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label className="text-[12.5px] text-muted">
            Payment method
            <input className={INPUT} value={paymentMethod} onChange={(e) => setPaymentMethod(e.target.value)} />
          </label>
          <label className="text-[12.5px] text-muted">
            Payment status
            <select
              className={INPUT}
              value={paymentStatus}
              onChange={(e) => setPaymentStatus(e.target.value as "unpaid" | "paid" | "cod")}
            >
              <option value="cod">Cash on delivery</option>
              <option value="unpaid">Unpaid</option>
              <option value="paid">Paid</option>
            </select>
          </label>
        </div>
        <label className="text-[12.5px] text-muted">
          Notes
          <textarea className={INPUT} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>

        <div className="rounded-md border border-border px-3 py-2 text-[13px]">
          <div className="flex justify-between">
            <span>Total (preview)</span>
            <strong>{formatMoney(Math.max(preview, 0), currency)}</strong>
          </div>
          <p className="mt-1 text-muted">Calculated by the server on save.</p>
        </div>
        {save.isError && <p className="text-danger">{errorText(save.error)}</p>}
        <button type="submit" className="btn" disabled={!canSave}>
          {save.isPending ? "Saving…" : "Create order"}
        </button>
      </form>
    </SideSheet>
  );
}
