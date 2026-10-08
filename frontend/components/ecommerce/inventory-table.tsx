"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";

import { dashboardKeys } from "@/lib/api/dashboard";
import { adjustInventory, fetchInventory, inventoryKeys } from "@/lib/api/inventory";
import { productKeys } from "@/lib/api/products";
import { ApiError } from "@/lib/types/common";
import type { InventoryItem } from "@/lib/types/inventory";

const COLUMN_COUNT = 9;

// Adjust inputs share the .form-row input look (mockup), inline.
const CONTROL = "rounded-md border border-border bg-panel px-3 py-2 text-[13.5px] text-text";

// Stock status from backend fields only (no frontend cutoff): nothing
// available -> Out of stock, the backend's low_stock flag -> Low stock.
function statusBadge(item: InventoryItem): { label: string; className: string } {
  if (item.available <= 0) return { label: "Out of stock", className: "badge badge-danger" };
  if (item.low_stock) return { label: "Low stock", className: "badge badge-warn" };
  return { label: "In stock", className: "badge badge-success" };
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

// Inline editor under a row: a new absolute on-hand quantity and an optional
// reason. The frontend has no current-user role, so any user sees it and the
// backend enforces manager+ (a 403 gets a plain-language message).
function AdjustRow({ item, onDone }: { item: InventoryItem; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [onHand, setOnHand] = useState(String(item.on_hand));
  const [reason, setReason] = useState("");

  const adjust = useMutation({
    mutationFn: () => adjustInventory(item.id, { on_hand: Number(onHand), reason: reason.trim() || null }),
    onSuccess: (updated) => {
      queryClient.setQueryData<InventoryItem[]>(inventoryKeys.list, (old) =>
        old?.map((row) => (row.id === updated.id ? updated : row)),
      );
      // Stock also shows in the Products tab and the Dashboard's low-stock card.
      void queryClient.invalidateQueries({ queryKey: productKeys.list });
      void queryClient.invalidateQueries({ queryKey: dashboardKeys.lowStock });
      onDone();
    },
    // On failure the typed values stay; the message shows below.
  });

  const errorText =
    adjust.error instanceof ApiError && adjust.error.status === 403
      ? "Only managers and above can adjust stock."
      : adjust.error?.message;

  return (
    <tr>
      <td colSpan={COLUMN_COUNT}>
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            adjust.mutate();
          }}
        >
          <label className="flex flex-col gap-1 text-[13px] font-medium">
            New on-hand quantity
            <input
              type="number"
              min={0}
              step={1}
              required
              className={`${CONTROL} w-40`}
              value={onHand}
              onChange={(e) => setOnHand(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-[13px] font-medium">
            Reason (optional)
            <input
              maxLength={500}
              placeholder="e.g. Stock count"
              className={`${CONTROL} w-64`}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <button type="submit" className="btn btn-sm" disabled={adjust.isPending}>
            {adjust.isPending ? "Saving…" : "Save"}
          </button>
          <button type="button" className="btn btn-secondary btn-sm" disabled={adjust.isPending} onClick={onDone}>
            Cancel
          </button>
        </form>
        {adjust.isError && (
          <p className="mb-0 mt-2 text-xs text-danger" role="alert">
            {errorText}
          </p>
        )}
      </td>
    </tr>
  );
}

// Inventory tab (SPEC-FE-027): stock per variant and location, a "Low stock
// only" filter (client-side, on the backend's flag) and an inline Adjust.
export default function InventoryTable() {
  const query = useQuery({ queryKey: inventoryKeys.list, queryFn: fetchInventory });
  const [lowOnly, setLowOnly] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  const items = query.data ?? [];
  const lowCount = items.filter((i) => i.low_stock).length;
  const shown = lowOnly ? items.filter((i) => i.low_stock) : items;

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-4 text-[13px]">
        <label className="flex items-center gap-1.5">
          <input type="checkbox" checked={lowOnly} onChange={(e) => setLowOnly(e.target.checked)} />
          Low stock only
        </label>
        {query.data && (
          <span className="text-muted">
            {items.length} {items.length === 1 ? "item" : "items"} · {lowCount} low stock
          </span>
        )}
      </div>

      <div className="card" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>Product</th>
              <th>SKU</th>
              <th>Location</th>
              <th>On hand</th>
              <th>Committed</th>
              <th>Available</th>
              <th>Reorder point</th>
              <th>Status</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {query.isPending ? (
              <MessageRow className="text-muted">Loading inventory…</MessageRow>
            ) : query.isError ? (
              <MessageRow className="text-danger">Failed to load inventory: {query.error.message}</MessageRow>
            ) : items.length === 0 ? (
              <MessageRow className="text-muted">No inventory records yet</MessageRow>
            ) : shown.length === 0 ? (
              <MessageRow className="text-muted">No low-stock items</MessageRow>
            ) : (
              shown.map((item) => {
                const badge = statusBadge(item);
                return [
                  <tr key={item.id}>
                    <td>
                      {item.product_title}
                      {item.variant_label && <div className="text-xs text-muted">{item.variant_label}</div>}
                    </td>
                    <td>{item.sku}</td>
                    <td>{item.location_name}</td>
                    <td>{item.on_hand}</td>
                    <td>{item.committed}</td>
                    <td>{item.available}</td>
                    <td>{item.reorder_point}</td>
                    <td>
                      <span className={badge.className}>{badge.label}</span>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        disabled={editingId === item.id}
                        onClick={() => setEditingId(item.id)}
                      >
                        Adjust
                      </button>
                    </td>
                  </tr>,
                  editingId === item.id && (
                    <AdjustRow key={`${item.id}-adjust`} item={item} onDone={() => setEditingId(null)} />
                  ),
                ];
              })
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
