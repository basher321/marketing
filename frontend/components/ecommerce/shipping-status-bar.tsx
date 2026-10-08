"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { detectShipping, fetchShippingStatus, shippingKeys, syncShipping } from "@/lib/api/shipping";
import { ApiError } from "@/lib/types/common";
import type { DetectResult, PreviewMethod } from "@/lib/types/shipping";

const STORE = { shopify: "Shopify", woocommerce: "WooCommerce" } as Record<string, string>;
const METHOD = {
  flat_rate: "Flat rate",
  free_shipping: "Free shipping",
  carrier_calculated: "Carrier-calculated",
  local_pickup: "Local pickup",
  local_delivery: "Local delivery",
} as Record<string, string>;

function when(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : "never";
}

function errText(err: Error): string {
  if (err instanceof ApiError && err.status === 403) return "Only managers and above can sync shipping.";
  return err.message;
}

function methodLine(m: PreviewMethod): string {
  const parts = [METHOD[m.method_type] ?? m.method_type];
  if (m.method_type !== "carrier_calculated" && m.rate !== null) parts.push(m.rate === 0 ? "free" : String(m.rate));
  if (m.conditions.min_subtotal) parts.push(`orders ≥ ${m.conditions.min_subtotal}`);
  if (m.conditions.max_subtotal) parts.push(`orders ≤ ${m.conditions.max_subtotal}`);
  if (!m.active) parts.push("inactive");
  return parts.join(" · ");
}

// Detected-config preview (3A): what Import will create, before anything is written.
function DetectPreview({ result, onImport, onClose, importing }: { result: DetectResult; onImport: () => void; onClose: () => void; importing: boolean }) {
  return (
    <div className="card mb-4">
      <h3 className="mt-0">
        {result.detected ? `Found shipping in ${STORE[result.provider] ?? result.provider}` : `No usable shipping in ${STORE[result.provider] ?? result.provider}`}
      </h3>
      {result.preview.zones.length === 0 ? (
        <p className="text-[13px] text-muted">The store has no shipping zones. Use the guided setup below.</p>
      ) : (
        <ul className="m-0 grid gap-2 pl-4 text-[13px]">
          {result.preview.zones.map((z, i) => (
            <li key={i}>
              <b>{z.name}</b> <span className="text-muted">({z.rest_of_world ? "Rest of world" : z.country_codes.join(", ") || "no countries"})</span>
              <ul className="pl-4 text-xs text-muted">
                {z.methods.map((m, j) => (
                  <li key={j}>
                    {m.name}: {methodLine(m)}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
      {result.warnings.length > 0 && <p className="text-xs text-warn">{result.warnings.join(" ")}</p>}
      {result.unsupported.length > 0 && (
        <p className="text-xs text-muted">Not available through the API: {result.unsupported.join("; ")}.</p>
      )}
      <div className="flex gap-2">
        {result.detected && (
          <button type="button" className="btn btn-sm" disabled={importing} onClick={onImport}>
            {importing ? "Importing…" : "Import"}
          </button>
        )}
        <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  );
}

// Shipping status bar (SPEC-FE-040): the connected store, mode, last sync,
// counts and errors, plus Sync now / Re-detect.
export default function ShippingStatusBar() {
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: shippingKeys.status, queryFn: fetchShippingStatus });
  const [preview, setPreview] = useState<DetectResult | null>(null);
  const [showErrors, setShowErrors] = useState(false);
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: shippingKeys.status });
    void queryClient.invalidateQueries({ queryKey: shippingKeys.zones });
  };
  const detect = useMutation({ mutationFn: detectShipping, onSuccess: (r) => setPreview(r), onSettled: refresh });
  const sync = useMutation({ mutationFn: syncShipping, onSuccess: () => setPreview(null), onSettled: refresh });

  if (status.isPending) return <p className="text-[13px] text-muted">Loading shipping status…</p>;
  if (status.isError) {
    return (
      <p className="text-[13px] text-danger" role="alert">
        Failed to load shipping status: {status.error.message}
      </p>
    );
  }
  const s = status.data;
  const store = s.store ? STORE[s.store.provider] ?? s.store.provider : null;
  const mode =
    s.mode === "synced"
      ? { label: `Synced from ${store ?? "store"}`, cls: "badge badge-success" }
      : s.mode === "local"
        ? { label: "Local setup", cls: "badge badge-neutral" }
        : { label: "Setup required", cls: "badge badge-warn" };

  return (
    <>
      <div className="card mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="text-[13px]">
          <span className={mode.cls}>{mode.label}</span>{" "}
          {store ? (
            <span className="text-muted">
              Store: <b className="text-text">{s.store?.account_name || store}</b> · last sync {when(s.last_sync_at)}
              {s.last_sync_status && ` (${s.last_sync_status})`} · {s.counts.zones ?? 0} zones, {s.counts.methods ?? 0} methods
            </span>
          ) : (
            <span className="text-muted">No store connected — connect Shopify or WooCommerce in Integrations to import shipping.</span>
          )}
          {s.errors.length > 0 && (
            <button type="button" className="ml-2 text-xs text-danger underline" onClick={() => setShowErrors((v) => !v)}>
              {s.errors.length} error{s.errors.length === 1 ? "" : "s"}
            </button>
          )}
        </div>
        {store && (
          <div className="flex gap-2">
            <button type="button" className="btn btn-secondary btn-sm" disabled={detect.isPending} onClick={() => detect.mutate()}>
              {detect.isPending ? "Reading store…" : "Re-detect"}
            </button>
            <button type="button" className="btn btn-sm" disabled={sync.isPending} onClick={() => sync.mutate()}>
              {sync.isPending ? "Syncing…" : "Sync now"}
            </button>
          </div>
        )}
        {showErrors && (
          <ul className="m-0 w-full pl-4 text-xs text-danger">
            {s.errors.map((e, i) => (
              <li key={i}>
                {e.message} {e.at && <span className="text-muted">({when(e.at)})</span>}
              </li>
            ))}
          </ul>
        )}
        {(detect.isError || sync.isError) && (
          <p className="m-0 w-full text-xs text-danger" role="alert">
            {errText((detect.error ?? sync.error) as Error)}
          </p>
        )}
        {sync.isSuccess && (
          <p className="m-0 w-full text-xs text-success">
            Synced: {sync.data.created} created, {sync.data.updated} updated, {sync.data.deactivated} deactivated.
            {sync.data.errors.length > 0 && ` Issues: ${sync.data.errors.join(" ")}`}
          </p>
        )}
      </div>
      {preview && <DetectPreview result={preview} importing={sync.isPending} onImport={() => sync.mutate()} onClose={() => setPreview(null)} />}
    </>
  );
}
