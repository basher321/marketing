"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { BarChart, ReportStatus, Tile, channelLabel } from "@/components/analytics/ads-report";
import { errorText } from "@/components/organic/shared";
import { statusLabel } from "@/components/orders/status";
import { analyticsKeys, fetchProfitLoss, fetchProfitLossCsv, profitLossKey, type PLQuery } from "@/lib/api/analytics";
import { createExpense, deleteExpense, expenseKeys, fetchExpenses } from "@/lib/api/expenses";
import { formatMoney } from "@/lib/format/money";
import type { PLRange, ProfitLoss as PL } from "@/lib/types/analytics";
import type { ExpenseCategory } from "@/lib/types/expenses";

const INPUT = "rounded-md border border-border bg-panel px-3 py-2 text-[13.5px] text-text";
const RANGES: { key: PLRange; label: string }[] = [
  { key: "7d", label: "7 days" },
  { key: "30d", label: "30 days" },
  { key: "90d", label: "90 days" },
  { key: "mtd", label: "This month" },
  { key: "ytd", label: "This year" },
];
const CATEGORY_LABEL: Record<ExpenseCategory, string> = { shipping: "Shipping (couriers)", operating: "Operating", other: "Other" };

function delta(v: number | null): string | undefined {
  if (v === null) return "No earlier period to compare";
  return `${v > 0 ? "+" : ""}${v}% vs previous period`;
}

function Breakdown({ r }: { r: PL }) {
  const m = (v: number) => formatMoney(v, r.currency);
  const rows: [string, number][] = [
    ["Product cost", r.costs.product],
    ...r.costs.ad_spend.by_platform.map((p): [string, number] => [`Ads · ${channelLabel(p.platform)}`, p.amount]),
    ["Shipping expenses", r.costs.shipping],
    ["Operating", r.costs.operating],
    ["Other", r.costs.other],
  ];
  const max = Math.max(1, ...rows.map(([, v]) => v));
  return (
    <div className="card">
      <p className="card-title">Cost breakdown</p>
      <ul className="flex flex-col gap-2 text-[13px]">
        {rows.map(([label, v]) => (
          <li key={label}>
            <div className="flex justify-between">
              <span>{label}</span>
              <span>{m(v)}</span>
            </div>
            <div className="h-1.5 rounded bg-accent-soft">
              <div className="h-1.5 rounded bg-chart-2" style={{ width: `${(v / max) * 100}%` }} />
            </div>
          </li>
        ))}
        {r.costs.ad_spend.unavailable.map((u) => (
          <li key={u.platform} className="flex justify-between text-muted">
            <span>Ads · {channelLabel(u.platform)}</span>
            <span title={u.reason}>—</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 flex justify-between font-semibold">
        <span>Total costs</span>
        <span>{m(r.costs.total)}</span>
      </p>
    </div>
  );
}

function Expenses({ from, to, currency }: { from: string; to: string; currency: string }) {
  const queryClient = useQueryClient();
  const list = useQuery({ queryKey: expenseKeys.list(from, to), queryFn: () => fetchExpenses(from, to) });
  const [category, setCategory] = useState<ExpenseCategory>("operating");
  const [amount, setAmount] = useState("");
  const [day, setDay] = useState(to);
  const [description, setDescription] = useState("");
  const [vendor, setVendor] = useState("");
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: expenseKeys.all });
    void queryClient.invalidateQueries({ queryKey: [...analyticsKeys.all, "profit-loss"] });
  };
  const add = useMutation({
    mutationFn: () => createExpense({ category, amount: amount.trim(), incurred_on: day, description: description.trim(), ...(vendor.trim() ? { vendor: vendor.trim() } : {}) }),
    onSuccess: () => { setAmount(""); setDescription(""); setVendor(""); refresh(); },
  });
  const remove = useMutation({ mutationFn: (id: string) => deleteExpense(id), onSuccess: refresh });
  return (
    <div className="card">
      <p className="card-title">Expenses in this period</p>
      <form
        className="mb-3 flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (amount.trim() && description.trim()) add.mutate();
        }}
      >
        <select aria-label="Category" className={INPUT} value={category} onChange={(e) => setCategory(e.target.value as ExpenseCategory)}>
          {Object.entries(CATEGORY_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        <input aria-label="Amount" className={`${INPUT} w-28`} inputMode="decimal" placeholder="Amount" value={amount} onChange={(e) => setAmount(e.target.value)} />
        <input aria-label="Date" className={INPUT} type="date" value={day} max={to} onChange={(e) => setDay(e.target.value)} />
        <input aria-label="Description" className={`${INPUT} w-48`} placeholder="What for" value={description} onChange={(e) => setDescription(e.target.value)} />
        <input aria-label="Vendor" className={`${INPUT} w-36`} placeholder="Vendor (optional)" value={vendor} onChange={(e) => setVendor(e.target.value)} />
        <button type="submit" className="btn" disabled={add.isPending || !amount.trim() || !description.trim()}>+ Add expense</button>
      </form>
      {add.isError && <p className="mb-2 text-danger">{errorText(add.error, "Only managers and owners can record expenses.")}</p>}
      {remove.isError && <p className="mb-2 text-danger">{errorText(remove.error, "Only managers and owners can delete expenses.")}</p>}
      <p className="mb-2 text-[12.5px] text-muted">Product costs come from your products, so don&apos;t enter them here (they would count twice).</p>
      {list.isPending ? (
        <p className="text-muted">Loading…</p>
      ) : list.isError ? (
        <p className="text-danger">{list.error.message}</p>
      ) : list.data.items.length === 0 ? (
        <p className="text-muted">No expenses recorded in this period.</p>
      ) : (
        <table>
          <thead><tr><th>Date</th><th>Category</th><th>Description</th><th>Vendor</th><th>Amount</th><th aria-label="Actions" /></tr></thead>
          <tbody>
            {list.data.items.map((x) => (
              <tr key={x.id}>
                <td>{x.incurred_on}</td>
                <td>{CATEGORY_LABEL[x.category]}</td>
                <td>{x.description}</td>
                <td>{x.vendor ?? "—"}</td>
                <td>{formatMoney(x.amount, x.currency || currency)}</td>
                <td>
                  <button type="button" className="btn btn-secondary btn-sm" disabled={remove.isPending}
                    onClick={() => { if (window.confirm("Delete this expense?")) remove.mutate(x.id); }}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// Analytics → Profit & Loss (SPEC-FE-074 / SPEC-BE-110): sales, costs and the
// result from stored records only. Missing costs and unavailable ad spend are
// named, never shown as 0.
export default function ProfitLoss() {
  const [range, setRange] = useState<PLRange>("30d");
  const [custom, setCustom] = useState<{ from: string; to: string } | null>(null);
  const [draft, setDraft] = useState({ from: "", to: "" });
  const q: PLQuery = custom ?? { range };
  const query = useQuery({ queryKey: profitLossKey(q), queryFn: () => fetchProfitLoss(q) });
  const csv = useMutation({
    mutationFn: () => fetchProfitLossCsv(q),
    onSuccess: (text) => {
      const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = query.data ? `profit-loss_${query.data.period.from}_${query.data.period.to}.csv` : "profit-loss.csv";
      a.click();
      URL.revokeObjectURL(a.href);
    },
  });
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-1.5" role="group" aria-label="Date range">
        <span className="mr-1 text-[13px] text-muted">Range:</span>
        {RANGES.map((r) => (
          <button key={r.key} type="button" aria-pressed={!custom && range === r.key}
            className={!custom && range === r.key ? "btn btn-sm" : "btn btn-secondary btn-sm"}
            onClick={() => { setCustom(null); setRange(r.key); }}>
            {r.label}
          </button>
        ))}
        <input aria-label="From" type="date" className={INPUT} value={draft.from} onChange={(e) => setDraft({ ...draft, from: e.target.value })} />
        <input aria-label="To" type="date" className={INPUT} value={draft.to} onChange={(e) => setDraft({ ...draft, to: e.target.value })} />
        <button type="button" className="btn btn-secondary btn-sm" disabled={!draft.from || !draft.to} onClick={() => setCustom({ ...draft })}>Apply</button>
        <button type="button" className="btn btn-secondary btn-sm ml-auto" disabled={csv.isPending || !query.data} onClick={() => csv.mutate()}>
          {csv.isPending ? "Preparing…" : "Download CSV"}
        </button>
      </div>
      {csv.isError && <p className="mb-2 text-danger">{errorText(csv.error)}</p>}
      <ReportStatus query={query} what="profit & loss">
        {() => {
          const r = query.data!;
          const m = (v: number) => formatMoney(v, r.currency);
          const loss = r.profit < 0;
          return (
            <>
              {r.missing_cost.lines > 0 && (
                <div className="card mb-4 border-warn" role="status">
                  ⚠ {r.missing_cost.lines} order line(s) worth {m(r.missing_cost.revenue)} have no product cost, so profit is
                  overstated until you set costs. <Link href="/ecommerce?tab=products" className="text-accent">Set product costs →</Link>
                </div>
              )}
              {r.costs.ad_spend.unavailable.map((u) => (
                <div key={u.platform} className="card mb-4" role="status">ℹ {u.reason}</div>
              ))}
              {r.costs.ad_spend.excluded_currency.length > 0 && (
                <div className="card mb-4" role="status">
                  ℹ Ad spend in another currency isn&apos;t converted and is left out:{" "}
                  {r.costs.ad_spend.excluded_currency.map((x) => `${channelLabel(x.platform)} ${formatMoney(x.amount, x.currency)}`).join(", ")}.
                </div>
              )}
              <p className="mb-3 text-[13px] text-muted">{r.period.from} to {r.period.to} · compared with {r.previous_period.from} to {r.previous_period.to}</p>
              <div className="grid-3 mb-4">
                <Tile title="Sales total" value={m(r.revenue.net)} sub={`${r.revenue.order_count} order(s) · products ${m(r.revenue.sales)} + shipping charged ${m(r.revenue.shipping_charged)}`} hint={delta(r.delta_pct.revenue)} />
                <Tile title="Total costs" value={m(r.costs.total)} sub={`Product ${m(r.costs.product)} · ads ${m(r.costs.ad_spend.total)}`} />
                <Tile
                  title={loss ? "Loss" : "Profit"}
                  value={`${loss ? "−" : ""}${m(Math.abs(r.profit))}`}
                  sub={`${loss ? "▼ Loss" : "▲ Profit"} · margin ${r.margin === null ? "—" : `${r.margin}%`}${r.complete ? "" : " · incomplete"}`}
                  hint={delta(r.delta_pct.profit)}
                />
              </div>
              <div className="grid-2 mb-4">
                <div className="card">
                  <p className="card-title">Revenue vs costs by day</p>
                  <BarChart
                    days={r.by_day}
                    format={m}
                    series={[
                      { key: "net_revenue", label: "Net revenue", barClass: "bar", dotClass: "bg-chart-1" },
                      { key: "costs", label: "Costs", barClass: "bar bg-none bg-chart-3", dotClass: "bg-chart-3" },
                    ]}
                  />
                </div>
                <Breakdown r={r} />
              </div>
              <div className="grid-2 mb-4">
                <div className="card" style={{ padding: 0 }}>
                  <p className="card-title px-4 pt-4">By product</p>
                  <table>
                    <thead><tr><th>Product</th><th>Units</th><th>Revenue</th><th>Cost</th></tr></thead>
                    <tbody>
                      {r.by_product.length === 0 ? (
                        <tr><td colSpan={4} className="text-muted">No sales in this period</td></tr>
                      ) : r.by_product.map((p) => (
                        <tr key={`${p.sku}-${p.title}`}>
                          <td>{p.title ?? "—"} <span className="text-muted">{p.sku}</span></td>
                          <td>{p.units}</td>
                          <td>{m(p.revenue)}</td>
                          <td>{p.cost === null ? <span className="text-muted">no cost set</span> : m(p.cost)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="card" style={{ padding: 0 }}>
                  <p className="card-title px-4 pt-4">Not counted as sales</p>
                  <table>
                    <thead><tr><th>Status</th><th>Orders</th><th>Value</th></tr></thead>
                    <tbody>
                      {Object.entries(r.not_sales).map(([s, v]) => (
                        <tr key={s}><td>{statusLabel(s)}</td><td>{v.count}</td><td>{m(v.value)}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <details className="card mb-4">
                <summary className="cursor-pointer font-semibold">How this is calculated</summary>
                <ol className="mt-2 list-decimal pl-5 text-[13px]">
                  {r.rules.map((rule) => <li key={rule} className="mb-1">{rule}</li>)}
                </ol>
              </details>
              <Expenses from={r.period.from} to={r.period.to} currency={r.currency} />
            </>
          );
        }}
      </ReportStatus>
    </>
  );
}
