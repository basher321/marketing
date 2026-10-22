"use client";

import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { fetchProducts, productKeys } from "@/lib/api/products";
import type { ProductListItem, ProductStatus } from "@/lib/types/products";
import { formatMoney } from "@/lib/format/money";

const COLUMN_COUNT = 8;

// The backend's complete channel_type set (CLAUDE.md "Enum values"). Only a
// product listing exactly these reads "All channels" (mockup wording).
const ALL_CHANNELS = ["facebook", "instagram", "tiktok", "whatsapp", "messenger", "email", "sms", "web"];

// Mockup channel abbreviations ("FB, IG") for the live values; the rest use plain
// names. The mockup's "Shopify" has no channel_type (the storefront is "web").
const CHANNEL_SHORT: Record<string, string> = {
  facebook: "FB",
  instagram: "IG",
  tiktok: "TikTok",
  whatsapp: "WhatsApp",
  messenger: "Messenger",
  email: "Email",
  sms: "SMS",
  web: "Web",
};

// Badge per real product_status: active -> success, out_of_stock -> warn,
// draft -> neutral (the mockup's three). archived is the fourth live value the
// mockup doesn't show; it gets the neutral badge rather than an invented color.
const STATUS_BADGES: Record<ProductStatus, { label: string; className: string }> = {
  active: { label: "Active", className: "badge badge-success" },
  out_of_stock: { label: "Out of Stock", className: "badge badge-warn" },
  draft: { label: "Draft", className: "badge badge-neutral" },
  archived: { label: "Archived", className: "badge badge-neutral" },
};

// "৳790", "৳1,850" (mockup): the product currency's symbol, comma-grouped (SPEC-FE-048).
function formatPrice(p: ProductListItem): string {
  return formatMoney(p.price, p.currency);
}

function formatChannels(channels: string[]): string {
  if (channels.length === ALL_CHANNELS.length && ALL_CHANNELS.every((c) => channels.includes(c))) {
    return "All channels";
  }
  return channels.map((c) => CHANNEL_SHORT[c] ?? c).join(", ");
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

// Products table (SPEC-FE-011), markup from the reference mockup. SPEC-FE-075:
// a Category column, Stock only when the business type tracks stock, and Edit.
export default function ProductsTable({
  showStock = true,
  onEdit,
}: { showStock?: boolean; onEdit?: (id: string) => void } = {}) {
  const query = useQuery({ queryKey: productKeys.list, queryFn: fetchProducts });

  return (
    <div className="card" style={{ padding: 0 }}>
      <table>
        <thead>
          <tr>
            <th>SKU</th>
            <th>Product</th>
            <th>Category</th>
            <th>Price</th>
            {showStock && <th>Stock</th>}
            <th>Channel</th>
            <th>Status</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {query.isPending ? (
            <MessageRow className="text-muted">Loading products…</MessageRow>
          ) : query.isError ? (
            <MessageRow className="text-danger">Failed to load products: {query.error.message}</MessageRow>
          ) : query.data.length === 0 ? (
            <MessageRow className="text-muted">No products yet</MessageRow>
          ) : (
            query.data.map((p) => {
              const badge = STATUS_BADGES[p.status];
              return (
                <tr key={p.id}>
                  <td>{p.sku}</td>
                  <td>{p.title}</td>
                  <td>{p.category ?? <span className="text-muted">—</span>}</td>
                  <td>{formatPrice(p)}</td>
                  {showStock && <td>
                    {p.stock === null ? (
                      "—"
                    ) : p.low_stock ? (
                      // Badged only when the backend flags it (available <= reorder point).
                      <span className="badge badge-danger">{p.stock}</span>
                    ) : (
                      p.stock
                    )}
                  </td>}
                  <td>{formatChannels(p.channels)}</td>
                  <td>{badge ? <span className={badge.className}>{badge.label}</span> : p.status}</td>
                  <td>
                    {onEdit ? (
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => onEdit(p.id)}>
                        Edit
                      </button>
                    ) : (
                      <span className="text-muted">⋮</span>
                    )}
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
