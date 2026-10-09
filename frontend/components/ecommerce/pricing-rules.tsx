"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";

import { createPricingRule, fetchPricingRules, pricingKeys, setPricingRuleEnabled } from "@/lib/api/pricing";
import { fetchProducts, productKeys } from "@/lib/api/products";
import { ApiError, isRoleDenied } from "@/lib/types/common";
import type { PricingRule, PricingRuleCreate, PricingRuleState } from "@/lib/types/pricing";
import { formatMoney } from "@/lib/format/money";

const COLUMN_COUNT = 9;
const FORBIDDEN = "Only managers and above can change pricing rules.";

const TYPE_LABELS: Record<PricingRule["rule_type"], string> = {
  percent_discount: "Percent off",
  fixed_discount: "Fixed amount off",
  fixed_price: "Fixed price",
  tiered: "Tiered",
};

// Badge per backend-derived state: active -> success, scheduled -> warn,
// expired / disabled -> neutral.
const STATE_BADGES: Record<PricingRuleState, { label: string; className: string }> = {
  active: { label: "Active", className: "badge badge-success" },
  scheduled: { label: "Scheduled", className: "badge badge-warn" },
  expired: { label: "Expired", className: "badge badge-neutral" },
  disabled: { label: "Disabled", className: "badge badge-neutral" },
};

// Amounts in the tenant currency, with its own symbol (SPEC-FE-048).
function money(amount: number, currency: string): string {
  return formatMoney(amount, currency);
}

function formatValue(rule: PricingRule, currency: string): string {
  switch (rule.rule_type) {
    case "percent_discount":
      return `${rule.value}% off`;
    case "fixed_discount":
      return `${money(rule.value, currency)} off`;
    case "fixed_price":
      return money(rule.value, currency);
    default:
      return "—"; // tiered: the tiers live in the rule's conditions
  }
}

function appliesTo(rule: PricingRule): string {
  if (rule.scope === "all") return "All products";
  const noun = { sku: "product", category: "category", tag: "tag" }[rule.scope];
  const plural = rule.scope === "category" ? "categories" : `${noun}s`;
  return `${rule.scope_count} ${rule.scope_count === 1 ? noun : plural}`;
}

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function schedule(rule: PricingRule): string {
  if (rule.starts_at && rule.ends_at) return `${shortDate(rule.starts_at)} – ${shortDate(rule.ends_at)}`;
  if (rule.starts_at) return `From ${shortDate(rule.starts_at)}`;
  if (rule.ends_at) return `Until ${shortDate(rule.ends_at)}`;
  return "Always";
}

// A readable message for a failed write: 403 in plain language; FastAPI's 422
// list of field errors as their messages; otherwise the backend's own message.
function errorText(err: Error): string {
  if (err instanceof ApiError) {
    if (isRoleDenied(err)) return FORBIDDEN;
    const detail = (err.body as { detail?: unknown } | undefined)?.detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d: { msg?: string }) => (d.msg ?? "").replace(/^Value error, /, ""))
        .filter(Boolean)
        .join(" ");
    }
  }
  return err.message;
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

const EMPTY_FORM = {
  name: "",
  description: "",
  rule_type: "percent_discount" as PricingRuleCreate["rule_type"],
  value: "",
  scope: "all" as PricingRuleCreate["scope"],
  product_ids: [] as string[],
  min_quantity: "",
  starts_at: "",
  ends_at: "",
  priority: "0",
};

// "+ New rule" form with exactly the create schema's fields. The checks here
// mirror the backend's; the backend stays the authority and its errors show inline.
function NewRuleForm({ currency, onDone }: { currency: string; onDone: () => void }) {
  const queryClient = useQueryClient();
  const products = useQuery({ queryKey: productKeys.list, queryFn: fetchProducts });
  const [f, setF] = useState(EMPTY_FORM);
  const [localError, setLocalError] = useState<string | null>(null);
  const set = <K extends keyof typeof EMPTY_FORM>(key: K, value: (typeof EMPTY_FORM)[K]) =>
    setF((cur) => ({ ...cur, [key]: value }));

  const create = useMutation({
    mutationFn: (body: PricingRuleCreate) => createPricingRule(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: pricingKeys.rules });
      setF(EMPTY_FORM);
      onDone();
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const value = Number(f.value);
    // datetime-local is the viewer's local time; send it as an absolute instant.
    const startsAt = f.starts_at ? new Date(f.starts_at).toISOString() : null;
    const endsAt = f.ends_at ? new Date(f.ends_at).toISOString() : null;
    if (!(value > 0)) return setLocalError("The value must be greater than 0.");
    if (f.rule_type === "percent_discount" && value > 100) return setLocalError("A percentage discount cannot exceed 100.");
    if (f.scope === "sku" && f.product_ids.length === 0) return setLocalError("Choose at least one product.");
    if (startsAt && endsAt && endsAt <= startsAt) return setLocalError("The end must be after the start.");
    setLocalError(null);
    create.mutate({
      name: f.name.trim(),
      description: f.description.trim() || null,
      rule_type: f.rule_type,
      value,
      scope: f.scope,
      product_ids: f.scope === "sku" ? f.product_ids : [],
      min_quantity: f.min_quantity ? Number(f.min_quantity) : null,
      starts_at: startsAt,
      ends_at: endsAt,
      priority: Number(f.priority) || 0,
    });
  };

  const toggleProduct = (id: string) =>
    set("product_ids", f.product_ids.includes(id) ? f.product_ids.filter((p) => p !== id) : [...f.product_ids, id]);
  const valueUnit = f.rule_type === "percent_discount" ? "%" : currency;

  return (
    <form className="card mb-4" onSubmit={submit}>
      <h3 className="mt-0">New pricing rule</h3>
      <div className="grid gap-x-4 sm:grid-cols-2">
        <div className="form-row">
          <label htmlFor="pr_name">Name</label>
          <input id="pr_name" required maxLength={255} value={f.name} onChange={(e) => set("name", e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor="pr_desc">Description (optional)</label>
          <input id="pr_desc" maxLength={2000} value={f.description} onChange={(e) => set("description", e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor="pr_type">Type</label>
          <select
            id="pr_type"
            value={f.rule_type}
            onChange={(e) => set("rule_type", e.target.value as PricingRuleCreate["rule_type"])}
          >
            <option value="percent_discount">Percent off</option>
            <option value="fixed_discount">Fixed amount off</option>
            <option value="fixed_price">Fixed price</option>
          </select>
        </div>
        <div className="form-row">
          <label htmlFor="pr_value">Value ({valueUnit})</label>
          <input
            id="pr_value"
            type="number"
            required
            min={0.01}
            max={f.rule_type === "percent_discount" ? 100 : undefined}
            step="0.01"
            value={f.value}
            onChange={(e) => set("value", e.target.value)}
          />
        </div>
        <div className="form-row">
          <label htmlFor="pr_min">Minimum quantity (optional)</label>
          <input id="pr_min" type="number" min={1} step={1} value={f.min_quantity} onChange={(e) => set("min_quantity", e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor="pr_priority">Priority (higher applies first)</label>
          <input id="pr_priority" type="number" min={0} max={1000} step={1} value={f.priority} onChange={(e) => set("priority", e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor="pr_start">Starts (optional)</label>
          <input id="pr_start" type="datetime-local" value={f.starts_at} onChange={(e) => set("starts_at", e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor="pr_end">Ends (optional)</label>
          <input id="pr_end" type="datetime-local" value={f.ends_at} onChange={(e) => set("ends_at", e.target.value)} />
        </div>
      </div>
      <fieldset className="form-row border-none p-0">
        <legend className="mb-1.5 text-[13px] font-medium">Applies to</legend>
        <div className="flex gap-4 text-[13px]">
          <label className="flex items-center gap-1 font-normal">
            <input type="radio" name="pr_scope" checked={f.scope === "all"} onChange={() => set("scope", "all")} />
            All products
          </label>
          <label className="flex items-center gap-1 font-normal">
            <input type="radio" name="pr_scope" checked={f.scope === "sku"} onChange={() => set("scope", "sku")} />
            Specific products
          </label>
        </div>
        {f.scope === "sku" && (
          <div className="mt-2 flex flex-wrap gap-3 text-[13px]">
            {products.isPending ? (
              <span className="text-muted">Loading products…</span>
            ) : products.isError ? (
              <span className="text-danger">Failed to load products: {products.error.message}</span>
            ) : (
              products.data.map((p) => (
                <label key={p.id} className="flex items-center gap-1 font-normal">
                  <input type="checkbox" checked={f.product_ids.includes(p.id)} onChange={() => toggleProduct(p.id)} />
                  {p.title} <span className="text-muted">({p.sku})</span>
                </label>
              ))
            )}
          </div>
        )}
      </fieldset>
      <div className="flex gap-2">
        <button type="submit" className="btn btn-sm" disabled={create.isPending}>
          {create.isPending ? "Creating…" : "Create rule"}
        </button>
        <button type="button" className="btn btn-secondary btn-sm" disabled={create.isPending} onClick={onDone}>
          Cancel
        </button>
      </div>
      {(localError || create.isError) && (
        <p className="mb-0 mt-3 text-xs text-danger" role="alert">
          {localError ?? (create.error ? errorText(create.error) : "")}
        </p>
      )}
    </form>
  );
}

// Pricing Rules tab (SPEC-FE-028): automatic discount / price rules with a
// "+ New rule" form and per-rule Enable/Disable.
export default function PricingRules() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: pricingKeys.rules, queryFn: fetchPricingRules });
  const [adding, setAdding] = useState(false);

  const toggle = useMutation({
    mutationFn: (rule: PricingRule) => setPricingRuleEnabled(rule.id, !rule.enabled),
    onSuccess: () => {
      // Refetch: toggling can move the rule in the backend's enabled-first order.
      void queryClient.invalidateQueries({ queryKey: pricingKeys.rules });
    },
  });

  const currency = query.data?.currency ?? "BDT";

  return (
    <>
      <div className="mb-4 flex items-center justify-between">
        <span className="text-[13px] text-muted">
          {query.data ? `${query.data.count} ${query.data.count === 1 ? "rule" : "rules"}` : ""}
        </span>
        {!adding && (
          <button type="button" className="btn btn-sm" onClick={() => setAdding(true)}>
            + New rule
          </button>
        )}
      </div>

      {adding && query.data && <NewRuleForm currency={currency} onDone={() => setAdding(false)} />}

      <div className="card" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>Rule</th>
              <th>Type</th>
              <th>Value</th>
              <th>Applies to</th>
              <th>Min qty</th>
              <th>Schedule</th>
              <th>Priority</th>
              <th>Status</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {query.isPending ? (
              <MessageRow className="text-muted">Loading pricing rules…</MessageRow>
            ) : query.isError ? (
              <MessageRow className="text-danger">Failed to load pricing rules: {query.error.message}</MessageRow>
            ) : query.data.items.length === 0 ? (
              <MessageRow className="text-muted">
                No pricing rules yet — create one to discount products automatically.
              </MessageRow>
            ) : (
              query.data.items.map((rule) => {
                const badge = STATE_BADGES[rule.state];
                const busy = toggle.isPending && toggle.variables?.id === rule.id;
                return (
                  <tr key={rule.id}>
                    <td>
                      {rule.name}
                      {rule.description && <div className="text-xs text-muted">{rule.description}</div>}
                    </td>
                    <td>{TYPE_LABELS[rule.rule_type] ?? rule.rule_type}</td>
                    <td>{formatValue(rule, currency)}</td>
                    <td>{appliesTo(rule)}</td>
                    <td>{rule.min_quantity ?? "—"}</td>
                    <td>{schedule(rule)}</td>
                    <td>{rule.priority}</td>
                    <td>{badge ? <span className={badge.className}>{badge.label}</span> : rule.state}</td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        disabled={busy}
                        onClick={() => toggle.mutate(rule)}
                      >
                        {rule.enabled ? "Disable" : "Enable"}
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
      {toggle.isError && (
        <p className="mb-0 mt-3 text-xs text-danger" role="alert">
          {errorText(toggle.error)}
        </p>
      )}
    </>
  );
}
