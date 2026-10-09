"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import {
  createShippingRate,
  createShippingZone,
  fetchShippingStatus,
  fetchShippingZones,
  setShippingRateActive,
  shippingKeys,
  updateShippingRate,
} from "@/lib/api/shipping";
import { ApiError, isRoleDenied } from "@/lib/types/common";
import type { ShippingRate, ShippingZone, ValidationResult } from "@/lib/types/shipping";
import { formatMoney } from "@/lib/format/money";

import ShippingSetupWizard from "./shipping-setup-wizard";
import ShippingStatusBar from "./shipping-status-bar";

const SOURCE_LABEL: Record<string, string> = { local: "Local", shopify: "Shopify", woocommerce: "WooCommerce" };
const METHOD_LABEL: Record<string, string> = {
  flat_rate: "Flat rate",
  free_shipping: "Free shipping",
  carrier_calculated: "Carrier-calculated",
  local_pickup: "Local pickup",
  local_delivery: "Local delivery",
};

function conditionsText(rate: ShippingRate): string {
  const c = rate.conditions ?? {};
  const parts: string[] = [];
  if (c.min_subtotal != null) parts.push(`order ≥ ${c.min_subtotal}`);
  if (c.max_subtotal != null) parts.push(`order ≤ ${c.max_subtotal}`);
  if (c.min_weight_g != null) parts.push(`≥ ${c.min_weight_g} g`);
  if (c.max_weight_g != null) parts.push(`≤ ${c.max_weight_g} g`);
  return parts.join(", ") || "—";
}

// Validation icon with the issues as its tooltip (SPEC-FE-040).
function ValidationIcon({ v }: { v: ValidationResult | null }) {
  if (!v || v.issues.length === 0) return null;
  const error = v.issues.some((i) => i.severity === "error");
  return (
    <span className={error ? "ml-1 text-danger" : "ml-1 text-warn"} title={v.issues.map((i) => i.message).join("\n")} aria-label={error ? "Validation errors" : "Validation warnings"}>
      {error ? "⛔" : "⚠"}
    </span>
  );
}

// Inline rate editor; a store-sourced rate is changed in the store first (backend).
function EditRateForm({ rate, currency, onDone }: { rate: ShippingRate; currency: string; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [f, setF] = useState({
    name: rate.name,
    rate: String(rate.rate),
    free_over: rate.free_over === null ? "" : String(rate.free_over),
    min_subtotal: rate.conditions?.min_subtotal == null ? "" : String(rate.conditions.min_subtotal),
    min: rate.sla_days_min === null ? "" : String(rate.sla_days_min),
    max: rate.sla_days_max === null ? "" : String(rate.sla_days_max),
  });
  const set = (k: keyof typeof f, v: string) => setF((cur) => ({ ...cur, [k]: v }));
  const save = useMutation({
    mutationFn: () =>
      updateShippingRate(rate.id, {
        name: f.name.trim(),
        rate: Number(f.rate || 0),
        free_over: f.free_over === "" ? null : Number(f.free_over),
        conditions: { min_subtotal: f.min_subtotal === "" ? null : Number(f.min_subtotal) },
        sla_days_min: f.min === "" ? null : Number(f.min),
        sla_days_max: f.max === "" ? null : Number(f.max),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: shippingKeys.zones });
      onDone();
    },
  });
  return (
    <tr>
      <td colSpan={10}>
        <div className="grid gap-x-3 sm:grid-cols-6">
          <div className="form-row">
            <label htmlFor={`er_n_${rate.id}`}>Name</label>
            <input id={`er_n_${rate.id}`} value={f.name} onChange={(e) => set("name", e.target.value)} />
          </div>
          <div className="form-row">
            <label htmlFor={`er_p_${rate.id}`}>Price ({currency})</label>
            <input id={`er_p_${rate.id}`} type="number" min={0} step="0.01" value={f.rate} onChange={(e) => set("rate", e.target.value)} />
          </div>
          <div className="form-row">
            <label htmlFor={`er_f_${rate.id}`}>Free over</label>
            <input id={`er_f_${rate.id}`} type="number" min={0} step="0.01" value={f.free_over} onChange={(e) => set("free_over", e.target.value)} />
          </div>
          <div className="form-row">
            <label htmlFor={`er_m_${rate.id}`}>Min order</label>
            <input id={`er_m_${rate.id}`} type="number" min={0} step="0.01" value={f.min_subtotal} onChange={(e) => set("min_subtotal", e.target.value)} />
          </div>
          <div className="form-row">
            <label htmlFor={`er_s_${rate.id}`}>Days min</label>
            <input id={`er_s_${rate.id}`} type="number" min={0} value={f.min} onChange={(e) => set("min", e.target.value)} />
          </div>
          <div className="form-row">
            <label htmlFor={`er_x_${rate.id}`}>Days max</label>
            <input id={`er_x_${rate.id}`} type="number" min={0} value={f.max} onChange={(e) => set("max", e.target.value)} />
          </div>
        </div>
        <div className="flex gap-2">
          <button type="button" className="btn btn-sm" disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? "Saving…" : rate.source === "local" ? "Save" : `Save to ${SOURCE_LABEL[rate.source]}`}
          </button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onDone}>
            Cancel
          </button>
        </div>
        {save.isError && <ErrorLine text={errorText(save.error)} />}
      </td>
    </tr>
  );
}

const FORBIDDEN = "Only managers and above can change shipping settings.";

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

// Amounts in the tenant currency, with its own symbol (SPEC-FE-048).
function money(amount: number, currency: string): string {
  return formatMoney(amount, currency);
}

// "BD" -> "Bangladesh" (built-in Intl names; the raw code if unknown).
const regionNames = new Intl.DisplayNames(["en"], { type: "region" });
function countryName(code: string): string {
  try {
    return regionNames.of(code) ?? code;
  } catch {
    return code;
  }
}

function delivery(rate: ShippingRate): string {
  const { sla_days_min: min, sla_days_max: max } = rate;
  if (min !== null && max !== null) return min === max ? `${min} ${min === 1 ? "day" : "days"}` : `${min}–${max} days`;
  if (min !== null) return `${min}+ days`;
  if (max !== null) return `Up to ${max} days`;
  return "—";
}

// Split "Dhaka, Chattogram" into clean, non-empty parts.
function splitList(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function ErrorLine({ text }: { text: string }) {
  return (
    <p className="mb-0 mt-3 text-xs text-danger" role="alert">
      {text}
    </p>
  );
}

function NewZoneForm({ onDone }: { onDone: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [countries, setCountries] = useState("BD");
  const [regions, setRegions] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: createShippingZone,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: shippingKeys.zones });
      onDone();
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const codes = splitList(countries).map((c) => c.toUpperCase());
    if (codes.length === 0 || codes.some((c) => !/^[A-Z]{2}$/.test(c))) {
      return setLocalError("Country codes must be two letters, comma-separated (e.g. BD).");
    }
    setLocalError(null);
    create.mutate({ name: name.trim(), country_codes: codes, regions: splitList(regions) });
  };

  return (
    <form className="card mb-4" onSubmit={submit}>
      <h3 className="mt-0">New shipping zone</h3>
      <div className="grid gap-x-4 sm:grid-cols-3">
        <div className="form-row">
          <label htmlFor="sz_name">Zone name</label>
          <input id="sz_name" required maxLength={255} placeholder="e.g. Dhaka City" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor="sz_countries">Country codes</label>
          <input id="sz_countries" required placeholder="BD" value={countries} onChange={(e) => setCountries(e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor="sz_regions">Regions (optional, comma-separated)</label>
          <input id="sz_regions" placeholder="Dhaka, Gazipur" value={regions} onChange={(e) => setRegions(e.target.value)} />
        </div>
      </div>
      <div className="flex gap-2">
        <button type="submit" className="btn btn-sm" disabled={create.isPending}>
          {create.isPending ? "Adding…" : "Add zone"}
        </button>
        <button type="button" className="btn btn-secondary btn-sm" disabled={create.isPending} onClick={onDone}>
          Cancel
        </button>
      </div>
      {localError && <ErrorLine text={localError} />}
      {!localError && create.isError && <ErrorLine text={errorText(create.error)} />}
    </form>
  );
}

function NewRateForm({ zoneId, currency, onDone }: { zoneId: string; currency: string; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [f, setF] = useState({ name: "", carrier: "", rate: "", free_over: "", min: "", max: "", cutoff: "" });
  const [localError, setLocalError] = useState<string | null>(null);
  const set = (key: keyof typeof f, value: string) => setF((cur) => ({ ...cur, [key]: value }));

  const create = useMutation({
    mutationFn: (body: Parameters<typeof createShippingRate>[1]) => createShippingRate(zoneId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: shippingKeys.zones });
      onDone();
    },
  });

  const num = (v: string) => (v === "" ? null : Number(v));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const min = num(f.min);
    const max = num(f.max);
    if (min !== null && max !== null && max < min) {
      return setLocalError("Maximum delivery days cannot be less than the minimum.");
    }
    setLocalError(null);
    create.mutate({
      name: f.name.trim(),
      carrier: f.carrier.trim(),
      rate: Number(f.rate),
      free_over: num(f.free_over),
      sla_days_min: min,
      sla_days_max: max,
      cutoff_time: f.cutoff || null,
    });
  };

  return (
    <form className="border-t border-border p-4" onSubmit={submit}>
      <div className="grid gap-x-4 sm:grid-cols-4">
        <div className="form-row">
          <label htmlFor={`sr_name_${zoneId}`}>Rate name</label>
          <input id={`sr_name_${zoneId}`} required maxLength={255} placeholder="e.g. Standard" value={f.name} onChange={(e) => set("name", e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor={`sr_carrier_${zoneId}`}>Carrier</label>
          <input id={`sr_carrier_${zoneId}`} required maxLength={255} placeholder="e.g. Pathao" value={f.carrier} onChange={(e) => set("carrier", e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor={`sr_rate_${zoneId}`}>Price ({currency}, 0 = free)</label>
          <input id={`sr_rate_${zoneId}`} type="number" required min={0} step="0.01" value={f.rate} onChange={(e) => set("rate", e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor={`sr_free_${zoneId}`}>Free over (optional)</label>
          <input id={`sr_free_${zoneId}`} type="number" min={0.01} step="0.01" value={f.free_over} onChange={(e) => set("free_over", e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor={`sr_min_${zoneId}`}>Min days (optional)</label>
          <input id={`sr_min_${zoneId}`} type="number" min={0} max={365} step={1} value={f.min} onChange={(e) => set("min", e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor={`sr_max_${zoneId}`}>Max days (optional)</label>
          <input id={`sr_max_${zoneId}`} type="number" min={0} max={365} step={1} value={f.max} onChange={(e) => set("max", e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor={`sr_cutoff_${zoneId}`}>Order cutoff (optional)</label>
          <input id={`sr_cutoff_${zoneId}`} type="time" value={f.cutoff} onChange={(e) => set("cutoff", e.target.value)} />
        </div>
      </div>
      <div className="flex gap-2">
        <button type="submit" className="btn btn-sm" disabled={create.isPending}>
          {create.isPending ? "Adding…" : "Add rate"}
        </button>
        <button type="button" className="btn btn-secondary btn-sm" disabled={create.isPending} onClick={onDone}>
          Cancel
        </button>
      </div>
      {localError && <ErrorLine text={localError} />}
      {!localError && create.isError && <ErrorLine text={errorText(create.error)} />}
    </form>
  );
}

function ZoneCard({ zone, currency }: { zone: ShippingZone; currency: string }) {
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const storeZone = zone.source !== "local";

  const toggle = useMutation({
    mutationFn: (rate: ShippingRate) => setShippingRateActive(rate.id, !rate.active),
    onSuccess: (updated) => {
      queryClient.setQueryData(shippingKeys.zones, (old: { currency: string; zones: ShippingZone[] } | undefined) =>
        old && {
          ...old,
          zones: old.zones.map((z) => ({ ...z, rates: z.rates.map((r) => (r.id === updated.id ? updated : r)) })),
        },
      );
    },
  });

  const where = zone.rest_of_world
    ? "Rest of world"
    : `${zone.country_codes.map(countryName).join(", ")} · ${zone.regions.length ? zone.regions.join(", ") : "All regions"}`;

  return (
    <div className="card mb-4" style={{ padding: 0 }}>
      <div className="flex items-center justify-between p-4">
        <div>
          <b>{zone.name}</b> <span className="badge badge-neutral">{SOURCE_LABEL[zone.source] ?? zone.source}</span>
          {!zone.active && <span className="badge badge-neutral ml-1">Inactive</span>}
          <ValidationIcon v={zone.validation} />
          <div className="text-xs text-muted">{where}</div>
        </div>
        {!adding && !storeZone && (
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setAdding(true)}>
            + Add rate
          </button>
        )}
      </div>
      {zone.rates.length === 0 ? (
        <p className="m-0 border-t border-border p-4 text-[13px] text-muted">No rates yet</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Rate</th>
              <th>Method</th>
              <th>Carrier</th>
              <th>Price</th>
              <th>Free over</th>
              <th>Conditions</th>
              <th>Delivery</th>
              <th>Order cutoff</th>
              <th>Status</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {zone.rates.map((rate) =>
              editing === rate.id ? (
                <EditRateForm key={rate.id} rate={rate} currency={currency} onDone={() => setEditing(null)} />
              ) : (
              <tr key={rate.id}>
                <td>
                  {rate.name}
                  <ValidationIcon v={rate.validation} />
                </td>
                <td>{METHOD_LABEL[rate.method_type] ?? rate.method_type}</td>
                <td>{rate.carrier}</td>
                <td>{rate.method_type === "carrier_calculated" ? "At checkout" : rate.rate === 0 ? "Free" : money(rate.rate, currency)}</td>
                <td>{rate.free_over === null ? "—" : money(rate.free_over, currency)}</td>
                <td>{conditionsText(rate)}</td>
                <td>{delivery(rate)}</td>
                <td>{rate.cutoff_time ?? "—"}</td>
                <td>
                  <span className={rate.active ? "badge badge-success" : "badge badge-neutral"}>
                    {rate.active ? "Active" : "Inactive"}
                  </span>
                </td>
                <td className="whitespace-nowrap">
                  {rate.read_only ? (
                    <span className="text-xs text-muted" title={`Edit this method in ${SOURCE_LABEL[rate.source]}`}>
                      🔒 Managed by {SOURCE_LABEL[rate.source]}
                    </span>
                  ) : (
                    <>
                      <button type="button" className="btn btn-secondary btn-sm mr-1" onClick={() => setEditing(rate.id)}>
                        Edit
                      </button>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        disabled={toggle.isPending && toggle.variables?.id === rate.id}
                        onClick={() => toggle.mutate(rate)}
                      >
                        {rate.active ? "Disable" : "Enable"}
                      </button>
                    </>
                  )}
                </td>
              </tr>
              ),
            )}
          </tbody>
        </table>
      )}
      {adding && <NewRateForm zoneId={zone.id} currency={currency} onDone={() => setAdding(false)} />}
      {toggle.isError && (
        <p className="m-0 px-4 pb-3 text-xs text-danger" role="alert">
          {errorText(toggle.error)}
        </p>
      )}
    </div>
  );
}

// Shipping tab (SPEC-FE-029): one card per zone (where you ship) with its
// rates, plus "+ New zone", "+ Add rate" and per-rate Enable/Disable.
export default function ShippingZones() {
  const query = useQuery({ queryKey: shippingKeys.zones, queryFn: fetchShippingZones });
  const status = useQuery({ queryKey: shippingKeys.status, queryFn: fetchShippingStatus });
  const [adding, setAdding] = useState(false);
  const [wizard, setWizard] = useState<boolean | null>(null);
  const zones = query.data?.zones ?? [];
  const store = status.data?.store ? (SOURCE_LABEL[status.data.store.provider] ?? status.data.store.provider) : null;
  // Guided setup opens by itself when there is no usable setup (3B).
  const showWizard = wizard ?? status.data?.mode === "setup_required";

  return (
    <>
      <ShippingStatusBar />
      {showWizard && <ShippingSetupWizard storeName={store} onDone={() => setWizard(false)} />}
      <div className="mb-4 flex items-center justify-between">
        <span className="text-[13px] text-muted">
          {query.data ? `${zones.length} ${zones.length === 1 ? "zone" : "zones"}` : ""}
        </span>
        <span className="flex gap-2">
          {!showWizard && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setWizard(true)}>
              Guided setup
            </button>
          )}
          {!adding && (
            <button type="button" className="btn btn-sm" onClick={() => setAdding(true)}>
              + New zone
            </button>
          )}
        </span>
      </div>

      {adding && <NewZoneForm onDone={() => setAdding(false)} />}

      {query.isPending ? (
        <p className="text-[13px] text-muted">Loading shipping zones…</p>
      ) : query.isError ? (
        <p className="text-[13px] text-danger" role="alert">
          Failed to load shipping zones: {query.error.message}
        </p>
      ) : zones.length === 0 ? (
        <div className="card text-[13px] text-muted">
          No shipping zones yet — add a zone to start offering delivery.
        </div>
      ) : (
        zones.map((zone) => <ZoneCard key={zone.id} zone={zone} currency={query.data.currency} />)
      )}
    </>
  );
}
