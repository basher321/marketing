"use client";

import { useEffect, useState } from "react";

import InventoryTable from "@/components/ecommerce/inventory-table";
import OrdersTable from "@/components/ecommerce/orders-table";
import PricingRules from "@/components/ecommerce/pricing-rules";
import ProductsTable from "@/components/ecommerce/products-table";
import ShippingZones from "@/components/ecommerce/shipping-zones";

const TABS = ["Products", "Orders", "Inventory", "Pricing Rules", "Shipping"] as const;
type Tab = (typeof TABS)[number];

// E-Commerce Automation (SPEC-FE-011). The mockup only has content for
// Products; the other tabs follow common e-commerce admin practice: Orders
// (SPEC-FE-026), Inventory (SPEC-FE-027), Pricing Rules (SPEC-FE-028) and
// Shipping (SPEC-FE-029).
export default function EcommercePage() {
  const [tab, setTab] = useState<Tab>("Products");
  // Deep links from Command Chat results (SPEC-FE-041): /ecommerce?tab=shipping.
  useEffect(() => {
    const wanted = new URLSearchParams(window.location.search).get("tab")?.toLowerCase();
    const match = TABS.find((t) => t.toLowerCase().replace(" ", "-") === wanted || t.toLowerCase() === wanted);
    if (match) setTab(match);
  }, []);
  return (
    <>
      <h1 className="m-0 mb-1 text-[22px] font-bold">{"E-Commerce Automation"}</h1>
      <p className="m-0 mb-5 text-muted">{"Catalog, orders, inventory, pricing — all in one place."}</p>
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <div
            key={t}
            role="tab"
            aria-selected={tab === t}
            tabIndex={0}
            className={tab === t ? "tab active" : "tab"}
            onClick={() => setTab(t)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") setTab(t);
            }}
          >
            {t}
          </div>
        ))}
      </div>
      {tab === "Products" && <ProductsTable />}
      {tab === "Orders" && <OrdersTable />}
      {tab === "Inventory" && <InventoryTable />}
      {tab === "Pricing Rules" && <PricingRules />}
      {tab === "Shipping" && <ShippingZones />}
    </>
  );
}
