"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";

import { channelLabel } from "@/components/customer/conversations-table";
import { fetchOrders, orderKeys } from "@/lib/api/orders";
import { ORDER_STATUSES, type OrderListItem, type OrderStatus } from "@/lib/types/orders";
import { formatMoney } from "@/lib/format/money";

const COLUMN_COUNT = 9;
const PAGE_SIZE = 25;

// Filter controls share the .form-row input look (mockup), inline.
const CONTROL = "rounded-md border border-border bg-panel px-3 py-2 text-[13.5px] text-text";

// Badge per live order_status (the full enum, SPEC-BE-041): waiting -> neutral,
// being worked on -> warn, on its way / done -> success, cancelled or refunded
// -> danger. An unknown value renders as plain text, never an invented badge.
const STATUS_BADGES: Record<OrderStatus, { label: string; className: string }> = {
  pending: { label: "Pending", className: "badge badge-neutral" },
  confirmed: { label: "Confirmed", className: "badge badge-warn" },
  processing: { label: "Processing", className: "badge badge-warn" },
  shipped: { label: "Shipped", className: "badge badge-success" },
  delivered: { label: "Delivered", className: "badge badge-success" },
  cancelled: { label: "Cancelled", className: "badge badge-danger" },
  refunded: { label: "Refunded", className: "badge badge-danger" },
};

// Same money formatting as the Products table: "৳1,850", "$12.50", "¥1,500".
function formatTotal(o: OrderListItem): string {
  return formatMoney(o.total, o.currency);
}

// "Sep 30, 14:05" in the viewer's local time.
function formatPlacedAt(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
}

// "COD", or "COD · paid" when the backend has a payment status.
function formatPayment(o: OrderListItem): string {
  const method = o.payment_method ? o.payment_method.toUpperCase() : "—";
  return o.payment_status ? `${method} · ${o.payment_status}` : method;
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

// Orders tab (SPEC-FE-026): status filter + search, the orders table, and
// 25-per-page pagination driven by the backend's `total`.
export default function OrdersTable() {
  const [status, setStatus] = useState<OrderStatus | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);

  // Debounce the search box by 300 ms; a new search starts from page 1.
  useEffect(() => {
    const id = setTimeout(() => {
      setQ(searchInput.trim());
      setPage(0);
    }, 300);
    return () => clearTimeout(id);
  }, [searchInput]);

  const params = { status, q, limit: PAGE_SIZE, offset: page * PAGE_SIZE };
  const query = useQuery({
    queryKey: orderKeys.list(params),
    // The offset travels with the rows, so "Showing x–y" always describes the
    // rows on screen, including the previous page kept while the next loads.
    queryFn: async () => ({ ...(await fetchOrders(params)), offset: params.offset }),
    placeholderData: keepPreviousData,
  });

  const filtered = status !== null || q !== "";
  const total = query.data?.total ?? 0;
  const shownOffset = query.data?.offset ?? 0;
  const from = total === 0 ? 0 : shownOffset + 1;
  const to = Math.min(shownOffset + PAGE_SIZE, total);

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select
          aria-label="Filter by status"
          className={CONTROL}
          value={status ?? ""}
          onChange={(e) => {
            setStatus(e.target.value === "" ? null : (e.target.value as OrderStatus));
            setPage(0);
          }}
        >
          <option value="">All statuses</option>
          {ORDER_STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS_BADGES[s].label}
            </option>
          ))}
        </select>
        <input
          type="search"
          aria-label="Search orders"
          placeholder="Search order # or customer"
          maxLength={100}
          className={`${CONTROL} w-64`}
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
        />
      </div>

      <div className="card" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>Order</th>
              <th>Date</th>
              <th>Customer</th>
              <th>Channel</th>
              <th>Items</th>
              <th>Total</th>
              <th>Payment</th>
              <th>Status</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {query.isPending ? (
              <MessageRow className="text-muted">Loading orders…</MessageRow>
            ) : query.isError ? (
              <MessageRow className="text-danger">Failed to load orders: {query.error.message}</MessageRow>
            ) : query.data.items.length === 0 ? (
              <MessageRow className="text-muted">
                {filtered ? "No orders match these filters" : "No orders yet"}
              </MessageRow>
            ) : (
              query.data.items.map((o) => {
                const badge = STATUS_BADGES[o.status];
                return (
                  <tr key={o.id}>
                    <td className="font-semibold">{o.order_number}</td>
                    <td>{formatPlacedAt(o.placed_at)}</td>
                    <td>{o.customer_name ?? <span className="text-muted">Guest</span>}</td>
                    <td>{channelLabel(o.channel)}</td>
                    <td>{o.item_count}</td>
                    <td>{formatTotal(o)}</td>
                    <td>{formatPayment(o)}</td>
                    <td>{badge ? <span className={badge.className}>{badge.label}</span> : o.status}</td>
                    {/* No order actions are defined yet: a static glyph, as in Products. */}
                    <td className="text-muted">⋮</td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {query.data && total > 0 && (
        <div className="mt-3 flex items-center justify-between text-[13px] text-muted">
          <span>
            Showing {from}–{to} of {total.toLocaleString("en-US")}
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={page === 0 || query.isFetching}
              onClick={() => setPage((p) => p - 1)}
            >
              Prev
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={to >= total || query.isFetching}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </>
  );
}
