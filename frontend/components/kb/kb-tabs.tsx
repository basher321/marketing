"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import Policies from "@/components/kb/policies";
import { fetchPricingRules, pricingKeys } from "@/lib/api/pricing";
import { fetchProducts, productKeys } from "@/lib/api/products";
import { fetchShippingZones, shippingKeys } from "@/lib/api/shipping";
import type { PricingRule } from "@/lib/types/pricing";
import { formatMoney } from "@/lib/format/money";

function money(amount: number, currency: string): string {
  return formatMoney(amount, currency);
}

function ruleText(rule: PricingRule, currency: string): string {
  const value =
    rule.rule_type === "percent_discount"
      ? `${rule.value}% off`
      : rule.rule_type === "fixed_discount"
        ? `${money(rule.value, currency)} off`
        : rule.rule_type === "fixed_price"
          ? `fixed price ${money(rule.value, currency)}`
          : "tiered pricing";
  const scope = rule.scope === "all" ? "all products" : `${rule.scope_count} ${rule.scope === "sku" ? "product(s)" : rule.scope}`;
  return `${value} on ${scope}${rule.min_quantity ? ` (min ${rule.min_quantity})` : ""}`;
}

const STOCK_TEXT: Record<string, string> = { active: "Available", out_of_stock: "Out of stock", draft: "Draft (hidden)", archived: "Archived (hidden)" };

// KB › Products & Pricing (SPEC-FE-033): a read view of what the AI can quote,
// from the existing product and pricing-rule endpoints. Editing stays in
// E-Commerce, so nothing is duplicated here.
export function ProductsPricingTab() {
  const products = useQuery({ queryKey: productKeys.list, queryFn: fetchProducts });
  const rules = useQuery({ queryKey: pricingKeys.rules, queryFn: fetchPricingRules });
  const activeRules = (rules.data?.items ?? []).filter((r) => r.state === "active");
  return (
    <div className="grid-2">
      <div className="card" style={{ padding: 0 }}>
        <div className="flex items-center justify-between px-5 pt-4">
          <h3 className="m-0">Products the AI can quote</h3>
          <Link href="/ecommerce" className="text-[13px] text-accent">
            Manage in E-Commerce →
          </Link>
        </div>
        <table className="mt-3">
          <thead>
            <tr>
              <th>Product</th>
              <th>SKU</th>
              <th>Price</th>
              <th>Availability</th>
            </tr>
          </thead>
          <tbody>
            {products.isPending ? (
              <tr>
                <td colSpan={4} className="text-muted">
                  Loading products…
                </td>
              </tr>
            ) : products.isError ? (
              <tr>
                <td colSpan={4} className="text-danger">
                  Failed to load products: {products.error.message}
                </td>
              </tr>
            ) : products.data.length === 0 ? (
              <tr>
                <td colSpan={4} className="text-muted">
                  No products yet — add them in E-Commerce.
                </td>
              </tr>
            ) : (
              products.data.map((p) => (
                <tr key={p.id}>
                  <td>{p.title}</td>
                  <td>{p.sku}</td>
                  <td>{money(p.price, p.currency)}</td>
                  <td>
                    {STOCK_TEXT[p.status] ?? p.status}
                    {p.status === "active" && p.stock !== null && <span className={`ml-1 text-xs ${p.low_stock ? "text-warn" : "text-muted"}`}>({p.stock} in stock)</span>}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <div className="card">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="m-0">Active price rules</h3>
          <Link href="/ecommerce" className="text-[13px] text-accent">
            Manage →
          </Link>
        </div>
        {rules.isPending ? (
          <p className="text-[13px] text-muted">Loading rules…</p>
        ) : rules.isError ? (
          <p className="text-[13px] text-danger">Failed to load pricing rules: {rules.error.message}</p>
        ) : activeRules.length === 0 ? (
          <p className="text-[13px] text-muted">No discounts are active right now.</p>
        ) : (
          <div className="kb-list">
            {activeRules.map((r) => (
              <div key={r.id} className="kb-item">
                <div className="kb-item-icon">%</div>
                <div>
                  <b>{r.name}</b>
                  <br />
                  <span className="text-xs text-muted">{ruleText(r, rules.data.currency)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function delivery(min: number | null, max: number | null): string {
  if (min !== null && max !== null) return min === max ? `${min} day${min === 1 ? "" : "s"}` : `${min}–${max} days`;
  if (max !== null) return `up to ${max} days`;
  if (min !== null) return `${min}+ days`;
  return "—";
}

// KB › Shipping (SPEC-FE-033): the zones and rates the AI can quote (read view
// of E-Commerce › Shipping) plus the editable delivery policy text.
export function ShippingTab() {
  const zones = useQuery({ queryKey: shippingKeys.zones, queryFn: fetchShippingZones });
  return (
    <>
      <div className="card mb-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="m-0">Delivery zones & rates</h3>
          <Link href="/ecommerce" className="text-[13px] text-accent">
            Manage in E-Commerce → Shipping
          </Link>
        </div>
        {zones.isPending ? (
          <p className="text-[13px] text-muted">Loading shipping zones…</p>
        ) : zones.isError ? (
          <p className="text-[13px] text-danger">Failed to load shipping zones: {zones.error.message}</p>
        ) : zones.data.zones.length === 0 ? (
          <p className="text-[13px] text-muted">No delivery zones yet — add them in E-Commerce › Shipping.</p>
        ) : (
          <div className="kb-list">
            {zones.data.zones.map((z) => (
              <div key={z.id} className="kb-item block">
                <b>{z.name}</b> <span className="text-xs text-muted">({z.regions.length ? z.regions.join(", ") : z.country_codes.join(", ")})</span>
                <ul className="m-0 mt-1 pl-5 text-[13px]">
                  {z.rates.filter((r) => r.active).map((r) => (
                    <li key={r.id}>
                      {r.name} via {r.carrier}: {r.rate === 0 ? "Free" : money(r.rate, zones.data.currency)}
                      {r.free_over !== null && `, free over ${money(r.free_over, zones.data.currency)}`} · {delivery(r.sla_days_min, r.sla_days_max)}
                    </li>
                  ))}
                  {z.rates.filter((r) => r.active).length === 0 && <li className="text-muted">No active rates</li>}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>
      <Policies only="shipping" />
    </>
  );
}
