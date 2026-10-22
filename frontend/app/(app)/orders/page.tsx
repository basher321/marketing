"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import OrdersTable from "@/components/ecommerce/orders-table";
import OrderForm from "@/components/orders/order-form";
import { ORDER_STATUSES, type OrderStatus } from "@/lib/types/orders";

// Orders (SPEC-FE-073): the order lifecycle list. `?status=` opens a filter
// (e.g. the dashboard's "Waiting for confirmation" card); "New order" opens the form.
function OrdersInner() {
  const params = useSearchParams();
  const wanted = params.get("status");
  const initial = (ORDER_STATUSES as readonly string[]).includes(wanted ?? "") ? (wanted as OrderStatus) : null;
  const [creating, setCreating] = useState(params.get("new") === "1");
  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="page-title">Orders</h1>
          <p className="page-subtitle">Placed → confirmation SMS → customer reply → delivery, with every change recorded.</p>
        </div>
        <button type="button" className="btn" onClick={() => setCreating(true)}>
          + New order
        </button>
      </div>
      <OrdersTable key={initial ?? "all"} initialStatus={initial} />
      {creating && <OrderForm onClose={() => setCreating(false)} />}
    </>
  );
}

export default function OrdersPage() {
  return (
    <Suspense fallback={<p className="text-muted">Loading…</p>}>
      <OrdersInner />
    </Suspense>
  );
}
