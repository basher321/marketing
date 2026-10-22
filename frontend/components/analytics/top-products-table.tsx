"use client";

import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { analyticsKeys, fetchTopProducts } from "@/lib/api/analytics";
import { useCompanyCurrency } from "@/hooks/use-tenant";
import { formatMoney } from "@/lib/format/money";
import { formatNumber } from "@/lib/format/number";

const COLUMN_COUNT = 4;

function MessageRow({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <tr>
      <td colSpan={COLUMN_COUNT} className={className}>
        {children}
      </td>
    </tr>
  );
}

// Comma-grouped whole units, as in the mockup ("৳147,730"). The backend returns
// no currency with this value, so the company currency's symbol is used
// (SPEC-FE-048); cents are rounded away as in the mockup.
function revenue(value: number, currency: string | null): string {
  return formatMoney(value, currency, { whole: true });
}

// Trend from the real signed trend_pct: > 0 -> ".up ▲", < 0 -> ".down ▼",
// exactly 0 -> "0%" with no arrow and no color. The magnitude keeps the
// backend's one decimal, dropping a trailing ".0" ("24%", "12.5%").
function TrendCell({ value }: { value: number }) {
  const text = `${formatNumber(Math.abs(value))}%`;
  if (value > 0) return <td className="up">▲ {text}</td>;
  if (value < 0) return <td className="down">▼ {text}</td>;
  return <td>{text}</td>;
}

// Analytics Sales tab "Top Products" table (SPEC-FE-020). Rows are rendered in
// the order the backend returns them (its own revenue-desc ranking), with no
// client-side sort.
export default function TopProductsTable() {
  const currency = useCompanyCurrency();
  const products = useQuery({ queryKey: analyticsKeys.topProducts, queryFn: fetchTopProducts });

  let body: ReactNode;
  if (products.data !== undefined) {
    // Rows already loaded stay visible if a background refetch fails.
    body =
      products.data.length === 0 ? (
        <MessageRow className="text-muted">No product data yet</MessageRow>
      ) : (
        products.data.map((p) => (
          <tr key={p.product_id}>
            <td>{p.product}</td>
            <td>{String(p.units_sold)}</td>
            <td>{revenue(p.revenue, currency)}</td>
            <TrendCell value={p.trend_pct} />
          </tr>
        ))
      );
  } else if (products.isError) {
    body = (
      <MessageRow className="text-danger">
        <span role="alert">Failed to load top products: {products.error.message}</span>
      </MessageRow>
    );
  } else {
    body = <MessageRow className="text-muted">Loading…</MessageRow>;
  }

  return (
    <>
      <h2 className="section-title">Top Products</h2>
      <div className="card" style={{ padding: 0 }} aria-busy={products.isPending}>
        <table>
          <thead>
            <tr>
              <th>Product</th>
              <th>Units Sold</th>
              <th>Revenue</th>
              <th>Trend</th>
            </tr>
          </thead>
          <tbody>{body}</tbody>
        </table>
      </div>
    </>
  );
}
