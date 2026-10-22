"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";

import { BusinessTypePicker, Categories, Payments } from "@/components/ecommerce/catalog-extras";
import InventoryTable from "@/components/ecommerce/inventory-table";
import OrdersTable from "@/components/ecommerce/orders-table";
import PricingRules from "@/components/ecommerce/pricing-rules";
import ProductForm from "@/components/ecommerce/product-form";
import ProductsTable from "@/components/ecommerce/products-table";
import ShippingZones from "@/components/ecommerce/shipping-zones";
import { ecommerceKeys, fetchEcommerceConfig } from "@/lib/api/ecommerce";

// E-Commerce Automation (SPEC-FE-011). The tabs follow the company's business type
// (SPEC-FE-075 / GET /ecommerce/config): Products, Categories, Inventory, Orders,
// Customers, Shipping, Payments, Pricing Rules — each only when the type has it.
// ?tab= deep links keep working; a hidden or unknown tab falls back to the first.
export default function EcommercePage() {
  const config = useQuery({ queryKey: ecommerceKeys.config, queryFn: fetchEcommerceConfig });
  const [tab, setTab] = useState<string>("products");
  const [editing, setEditing] = useState<string | null | undefined>(undefined);
  const tabs = config.data?.tabs ?? [];
  const [deepLinked, setDeepLinked] = useState(false);
  useEffect(() => {
    if (!config.data) return;
    const keys = config.data.tabs.map((t) => t.key);
    // The ?tab= deep link once; later config changes (e.g. a new business type)
    // keep the open tab unless the new type hides it.
    if (!deepLinked) {
      const wanted = new URLSearchParams(window.location.search).get("tab")?.toLowerCase().replace(" ", "-");
      setTab(wanted && keys.includes(wanted) ? wanted : keys[0] ?? "products");
      setDeepLinked(true);
    } else {
      setTab((cur) => (keys.includes(cur) ? cur : keys[0] ?? "products"));
    }
  }, [config.data, deepLinked]);
  const fields = config.data?.product_fields ?? [];
  const showStock = fields.some((f) => f.key === "stock");

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="page-title">{"E-Commerce Automation"}</h1>
          <p className="page-subtitle">{"Catalog, orders, inventory, pricing — all in one place."}</p>
        </div>
        {tab === "products" && config.data && (
          <button type="button" className="btn" onClick={() => setEditing(null)}>
            + Add product
          </button>
        )}
      </div>
      {config.isError && <p className="text-danger">Couldn&apos;t load the store settings: {config.error.message}</p>}
      {config.data && !config.data.confirmed && <BusinessTypePicker config={config.data} />}
      <div className="tabs" role="tablist">
        {tabs.map((t) => (
          <div
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            tabIndex={0}
            className={tab === t.key ? "tab active" : "tab"}
            onClick={() => setTab(t.key)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") setTab(t.key);
            }}
          >
            {t.label}
          </div>
        ))}
      </div>
      {config.isPending ? (
        <p className="text-muted">Loading…</p>
      ) : tab === "products" ? (
        <ProductsTable showStock={showStock} onEdit={(id) => setEditing(id)} />
      ) : tab === "categories" ? (
        <Categories />
      ) : tab === "orders" ? (
        <>
          <p className="mb-3 text-[13px]">
            <Link href="/orders?new=1" className="text-accent">+ New order</Link> · the full lifecycle is on the{" "}
            <Link href="/orders" className="text-accent">Orders</Link> page.
          </p>
          <OrdersTable />
        </>
      ) : tab === "customers" ? (
        <p className="card">
          Customers have their own page with each customer&apos;s orders, messages and SMS:{" "}
          <Link href="/customers" className="text-accent">Open Customers →</Link>
        </p>
      ) : tab === "inventory" ? (
        <InventoryTable />
      ) : tab === "pricing-rules" ? (
        <PricingRules />
      ) : tab === "shipping" ? (
        <ShippingZones />
      ) : tab === "payments" ? (
        <Payments />
      ) : null}
      {editing !== undefined && (
        <ProductForm fields={fields} productId={editing} onClose={() => setEditing(undefined)} />
      )}
    </>
  );
}
