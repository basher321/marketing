"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";

import { formatWhen } from "@/components/orders/status";
import { customerKeys, fetchCustomers } from "@/lib/api/customers";
import { formatMoney } from "@/lib/format/money";

const PAGE = 25;
const CONTROL = "rounded-md border border-border bg-panel px-3 py-2 text-[13.5px] text-text";

// Customers (SPEC-FE-073 / SPEC-BE-109): search and page through the company's
// customers; each row opens the customer record.
export default function CustomersPage() {
  const [input, setInput] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => {
      setQ(input.trim());
      setPage(0);
    }, 300);
    return () => clearTimeout(t);
  }, [input]);
  // One extra row tells whether there is a next page.
  const query = useQuery({
    queryKey: customerKeys.list(q, page),
    queryFn: () => fetchCustomers(q, PAGE + 1, page * PAGE),
    placeholderData: keepPreviousData,
  });
  const rows = (query.data ?? []).slice(0, PAGE);
  const more = (query.data?.length ?? 0) > PAGE;
  return (
    <>
      <h1 className="page-title">Customers</h1>
      <p className="page-subtitle">Everyone who ordered or wrote to you, with their orders, messages and SMS.</p>
      <input
        type="search"
        aria-label="Search customers"
        placeholder="Search name, phone or email"
        maxLength={100}
        className={`${CONTROL} mb-4 w-72`}
        value={input}
        onChange={(e) => setInput(e.target.value)}
      />
      <div className="card" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Phone</th>
              <th>Email</th>
              <th>Orders</th>
              <th>Lifetime value</th>
              <th>Last order</th>
            </tr>
          </thead>
          <tbody>
            {query.isPending ? (
              <tr><td colSpan={6} className="text-muted">Loading customers…</td></tr>
            ) : query.isError ? (
              <tr><td colSpan={6} className="text-danger">Failed to load customers: {query.error.message}</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={6} className="text-muted">{q ? "No customers match this search" : "No customers yet"}</td></tr>
            ) : (
              rows.map((c) => (
                <tr key={c.id}>
                  <td className="font-semibold">
                    <Link href={`/customers/${c.id}`} className="text-accent">
                      {[c.first_name, c.last_name].filter(Boolean).join(" ") || c.phone || c.email}
                    </Link>
                  </td>
                  <td>{c.phone ?? "—"}</td>
                  <td>{c.email ?? "—"}</td>
                  <td>{c.order_count}</td>
                  <td>{c.currency ? formatMoney(c.lifetime_value, c.currency) : c.lifetime_value}</td>
                  <td>{formatWhen(c.last_order_at)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex justify-end gap-2">
        <button type="button" className="btn btn-secondary btn-sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
          Prev
        </button>
        <button type="button" className="btn btn-secondary btn-sm" disabled={!more} onClick={() => setPage((p) => p + 1)}>
          Next
        </button>
      </div>
    </>
  );
}
