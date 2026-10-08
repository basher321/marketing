"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { setupShipping, shippingKeys, validateShippingSetup } from "@/lib/api/shipping";
import { ApiError } from "@/lib/types/common";
import type { MethodType, ShippingSetup, ValidationResult } from "@/lib/types/shipping";

type MethodDraft = {
  name: string;
  method_type: MethodType;
  carrier: string;
  rate: string;
  min_subtotal: string;
  max_subtotal: string;
  sla_min: string;
  sla_max: string;
  cutoff: string;
  pickup_location: string;
  pickup_instructions: string;
};
type ZoneDraft = { name: string; countries: string; regions: string; methods: MethodDraft[] };

const METHOD_TYPES: { value: MethodType; label: string }[] = [
  { value: "flat_rate", label: "Flat rate" },
  { value: "free_shipping", label: "Free shipping (with minimum order)" },
  { value: "carrier_calculated", label: "Carrier-calculated" },
  { value: "local_pickup", label: "Local pickup" },
  { value: "local_delivery", label: "Local delivery" },
];

const STEPS = ["Where you ship", "Methods", "Review", "Activate"] as const;

const newMethod = (): MethodDraft => ({
  name: "Standard delivery",
  method_type: "flat_rate",
  carrier: "Own delivery",
  rate: "",
  min_subtotal: "",
  max_subtotal: "",
  sla_min: "",
  sla_max: "",
  cutoff: "",
  pickup_location: "",
  pickup_instructions: "",
});
const newZone = (): ZoneDraft => ({ name: "", countries: "BD", regions: "", methods: [newMethod()] });

const list = (v: string) => v.split(",").map((s) => s.trim()).filter(Boolean);
const num = (v: string) => (v === "" ? null : Number(v));

function toPayload(zones: ZoneDraft[], push: boolean): ShippingSetup {
  return {
    push_to_store: push,
    zones: zones.map((z) => ({
      name: z.name.trim(),
      country_codes: list(z.countries).map((c) => c.toUpperCase()),
      regions: list(z.regions),
      methods: z.methods.map((m) => ({
        name: m.name.trim(),
        method_type: m.method_type,
        carrier: m.carrier.trim() || "Own delivery",
        rate: m.method_type === "free_shipping" || m.method_type === "carrier_calculated" ? 0 : Number(m.rate || 0),
        free_over: null,
        sla_days_min: num(m.sla_min),
        sla_days_max: num(m.sla_max),
        cutoff_time: m.cutoff || null,
        conditions: { min_subtotal: num(m.min_subtotal), max_subtotal: num(m.max_subtotal) },
        pickup_location: m.pickup_location || null,
        pickup_instructions: m.pickup_instructions || null,
      })),
    })),
  };
}

function errText(err: Error): string {
  if (err instanceof ApiError) {
    if (err.status === 403) return "Only managers and above can set up shipping.";
    const detail = (err.body as { detail?: unknown } | undefined)?.detail;
    if (Array.isArray(detail)) return detail.map((d: { msg?: string }) => (d.msg ?? "").replace(/^Value error, /, "")).join(" ");
  }
  return err.message;
}

// Guided shipping setup (SPEC-FE-040, step 3B): zones -> methods -> review
// (the backend validates the draft, nothing written) -> activate (creates it,
// and in the store too when asked).
export default function ShippingSetupWizard({ storeName, onDone }: { storeName: string | null; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [step, setStep] = useState(0);
  const [zones, setZones] = useState<ZoneDraft[]>([newZone()]);
  const [push, setPush] = useState(Boolean(storeName));
  const [review, setReview] = useState<ValidationResult | null>(null);

  const setZone = (i: number, patch: Partial<ZoneDraft>) => setZones((zs) => zs.map((z, j) => (j === i ? { ...z, ...patch } : z)));
  const setMethod = (zi: number, mi: number, patch: Partial<MethodDraft>) =>
    setZones((zs) => zs.map((z, j) => (j === zi ? { ...z, methods: z.methods.map((m, k) => (k === mi ? { ...m, ...patch } : m)) } : z)));

  const validate = useMutation({
    mutationFn: () => validateShippingSetup(toPayload(zones, false)),
    onSuccess: (r) => setReview(r),
  });
  const activate = useMutation({
    mutationFn: () => setupShipping(toPayload(zones, push)),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: shippingKeys.zones });
      void queryClient.invalidateQueries({ queryKey: shippingKeys.status });
      onDone();
    },
  });

  const zonesOk = zones.every((z) => z.name.trim() && list(z.countries).every((c) => /^[A-Za-z]{2}$/.test(c)) && list(z.countries).length);
  const go = (n: number) => {
    setStep(n);
    if (n === 2) validate.mutate();
  };

  return (
    <div className="card mb-4">
      <h3 className="mt-0">Set up shipping</h3>
      <div className="tabs mb-4" role="tablist">
        {STEPS.map((s, i) => (
          <div key={s} role="tab" aria-selected={step === i} className={step === i ? "tab active" : "tab"}>
            {i + 1}. {s}
          </div>
        ))}
      </div>

      {step === 0 && (
        <>
          {zones.map((z, i) => (
            <div key={i} className="grid gap-x-4 sm:grid-cols-3">
              <div className="form-row">
                <label htmlFor={`wz_name_${i}`}>Zone name</label>
                <input id={`wz_name_${i}`} placeholder="e.g. Inside Dhaka" value={z.name} onChange={(e) => setZone(i, { name: e.target.value })} />
              </div>
              <div className="form-row">
                <label htmlFor={`wz_c_${i}`}>Countries (two-letter codes)</label>
                <input id={`wz_c_${i}`} value={z.countries} onChange={(e) => setZone(i, { countries: e.target.value })} />
              </div>
              <div className="form-row">
                <label htmlFor={`wz_r_${i}`}>Regions (optional)</label>
                <input id={`wz_r_${i}`} placeholder="Dhaka, Gazipur" value={z.regions} onChange={(e) => setZone(i, { regions: e.target.value })} />
              </div>
            </div>
          ))}
          <div className="flex gap-2">
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setZones((zs) => [...zs, newZone()])}>
              + Another zone
            </button>
            <button type="button" className="btn btn-sm" disabled={!zonesOk} onClick={() => go(1)}>
              Continue
            </button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={onDone}>
              Cancel
            </button>
          </div>
        </>
      )}

      {step === 1 && (
        <>
          {zones.map((z, zi) => (
            <div key={zi} className="mb-4">
              <b>{z.name}</b>
              {z.methods.map((m, mi) => (
                <div key={mi} className="mt-2 grid gap-x-4 border-t border-border pt-2 sm:grid-cols-4">
                  <div className="form-row">
                    <label htmlFor={`wm_t_${zi}_${mi}`}>Method</label>
                    <select id={`wm_t_${zi}_${mi}`} value={m.method_type} onChange={(e) => setMethod(zi, mi, { method_type: e.target.value as MethodType })}>
                      {METHOD_TYPES.map((t) => (
                        <option key={t.value} value={t.value}>
                          {t.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="form-row">
                    <label htmlFor={`wm_n_${zi}_${mi}`}>Name shown at checkout</label>
                    <input id={`wm_n_${zi}_${mi}`} value={m.name} onChange={(e) => setMethod(zi, mi, { name: e.target.value })} />
                  </div>
                  {(m.method_type === "flat_rate" || m.method_type === "local_delivery" || m.method_type === "local_pickup") && (
                    <div className="form-row">
                      <label htmlFor={`wm_p_${zi}_${mi}`}>Price</label>
                      <input id={`wm_p_${zi}_${mi}`} type="number" min={0} step="0.01" value={m.rate} onChange={(e) => setMethod(zi, mi, { rate: e.target.value })} />
                    </div>
                  )}
                  <div className="form-row">
                    <label htmlFor={`wm_min_${zi}_${mi}`}>{m.method_type === "free_shipping" ? "Free for orders from" : "Min order (optional)"}</label>
                    <input id={`wm_min_${zi}_${mi}`} type="number" min={0} step="0.01" value={m.min_subtotal} onChange={(e) => setMethod(zi, mi, { min_subtotal: e.target.value })} />
                  </div>
                  <div className="form-row">
                    <label htmlFor={`wm_max_${zi}_${mi}`}>Max order (optional)</label>
                    <input id={`wm_max_${zi}_${mi}`} type="number" min={0} step="0.01" value={m.max_subtotal} onChange={(e) => setMethod(zi, mi, { max_subtotal: e.target.value })} />
                  </div>
                  <div className="form-row">
                    <label htmlFor={`wm_c_${zi}_${mi}`}>Carrier</label>
                    <input id={`wm_c_${zi}_${mi}`} value={m.carrier} onChange={(e) => setMethod(zi, mi, { carrier: e.target.value })} />
                  </div>
                  <div className="form-row">
                    <label htmlFor={`wm_s1_${zi}_${mi}`}>Delivery days (min–max)</label>
                    <div className="flex gap-1">
                      <input id={`wm_s1_${zi}_${mi}`} type="number" min={0} max={365} value={m.sla_min} onChange={(e) => setMethod(zi, mi, { sla_min: e.target.value })} />
                      <input aria-label="Max delivery days" type="number" min={0} max={365} value={m.sla_max} onChange={(e) => setMethod(zi, mi, { sla_max: e.target.value })} />
                    </div>
                  </div>
                  <div className="form-row">
                    <label htmlFor={`wm_cut_${zi}_${mi}`}>Order cutoff</label>
                    <input id={`wm_cut_${zi}_${mi}`} type="time" value={m.cutoff} onChange={(e) => setMethod(zi, mi, { cutoff: e.target.value })} />
                  </div>
                  {m.method_type === "local_pickup" && (
                    <>
                      <div className="form-row">
                        <label htmlFor={`wm_pl_${zi}_${mi}`}>Pickup location</label>
                        <input id={`wm_pl_${zi}_${mi}`} value={m.pickup_location} onChange={(e) => setMethod(zi, mi, { pickup_location: e.target.value })} />
                      </div>
                      <div className="form-row sm:col-span-2">
                        <label htmlFor={`wm_pi_${zi}_${mi}`}>Pickup instructions</label>
                        <input id={`wm_pi_${zi}_${mi}`} value={m.pickup_instructions} onChange={(e) => setMethod(zi, mi, { pickup_instructions: e.target.value })} />
                      </div>
                    </>
                  )}
                  {z.methods.length > 1 && (
                    <div className="form-row self-end">
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => setZone(zi, { methods: z.methods.filter((_, k) => k !== mi) })}>
                        Remove
                      </button>
                    </div>
                  )}
                </div>
              ))}
              <button type="button" className="btn btn-secondary btn-sm mt-2" onClick={() => setZone(zi, { methods: [...z.methods, newMethod()] })}>
                + Add method
              </button>
            </div>
          ))}
          <div className="flex gap-2">
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setStep(0)}>
              Back
            </button>
            <button type="button" className="btn btn-sm" onClick={() => go(2)}>
              Review
            </button>
          </div>
        </>
      )}

      {step === 2 && (
        <>
          {validate.isPending && <p className="text-[13px] text-muted">Checking…</p>}
          {validate.isError && <p className="text-xs text-danger">{errText(validate.error)}</p>}
          {review && (
            <>
              <p className={review.ok ? "text-[13px] text-success" : "text-[13px] text-danger"}>
                {review.ok ? "Everything checks out." : "Fix the errors below before activating."}
              </p>
              <ul className="m-0 pl-4 text-xs">
                {review.issues.map((i, k) => (
                  <li key={k} className={i.severity === "error" ? "text-danger" : "text-warn"}>
                    {i.zone ?? ""}
                    {i.rate ? ` / ${i.rate}` : ""}: {i.message}
                  </li>
                ))}
              </ul>
            </>
          )}
          <div className="mt-3 flex gap-2">
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setStep(1)}>
              Back
            </button>
            <button type="button" className="btn btn-sm" disabled={!review?.ok} onClick={() => setStep(3)}>
              Continue
            </button>
          </div>
        </>
      )}

      {step === 3 && (
        <>
          <p className="text-[13px]">
            {zones.length} zone{zones.length === 1 ? "" : "s"} with {zones.reduce((n, z) => n + z.methods.length, 0)} method(s) will be activated.
          </p>
          {storeName && (
            <label className="mb-3 flex items-center gap-2 text-[13px]">
              <input type="checkbox" checked={push} onChange={(e) => setPush(e.target.checked)} />
              Also create this in my {storeName} store
            </label>
          )}
          {activate.isError && <p className="text-xs text-danger">{errText(activate.error)}</p>}
          <div className="flex gap-2">
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setStep(2)}>
              Back
            </button>
            <button type="button" className="btn btn-sm" disabled={activate.isPending} onClick={() => activate.mutate()}>
              {activate.isPending ? "Activating…" : "Activate"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
