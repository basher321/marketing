"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { errorText } from "@/components/organic/shared";
import { formatWhen } from "@/components/orders/status";
import { fetchCompanies, fetchIntegrationErrors, fetchIntegrationHealth, platformKeys } from "@/lib/api/platform";
import { assignSmsNumber, fetchSmsNumbers, smsKeys } from "@/lib/api/sms";

const INPUT = "rounded-md border border-border bg-panel px-3 py-2 text-[13.5px] text-text";
const KIND: Record<string, string> = {
  connection: "Connection",
  webhook: "Webhook",
  invalid_signature: "Invalid signature",
  sms_failed: "SMS failed",
};

function SmsNumbers() {
  const qc = useQueryClient();
  const numbers = useQuery({ queryKey: smsKeys.numbers, queryFn: fetchSmsNumbers, retry: false });
  const companies = useQuery({ queryKey: platformKeys.companies("", 1), queryFn: () => fetchCompanies("", 1, 100) });
  const [pick, setPick] = useState<Record<string, string>>({});
  const assign = useMutation({
    mutationFn: (x: { company: string; number: string }) => assignSmsNumber(x.company, x.number),
    onSuccess: () => void qc.invalidateQueries({ queryKey: smsKeys.numbers }),
  });
  return (
    <div className="card">
      <p className="card-title">Twilio SMS numbers</p>
      <p className="mb-2 text-[12.5px] text-muted">
        One number per company: a customer&apos;s reply is matched to the company by the number it was sent to. Twilio must send
        replies and delivery updates to <code>/api/v1/webhooks/twilio/inbound</code> and <code>/status</code>.
      </p>
      {numbers.isPending ? (
        <p className="text-muted">Loading…</p>
      ) : numbers.isError ? (
        <p className="text-[13px] text-muted">{numbers.error.message}</p>
      ) : numbers.data.items.length === 0 ? (
        <p className="text-muted">The Twilio account has no numbers.</p>
      ) : (
        <table>
          <thead><tr><th>Number</th><th>SMS</th><th>Company</th><th aria-label="Actions" /></tr></thead>
          <tbody>
            {numbers.data.items.map((n) => (
              <tr key={n.number}>
                <td>{n.number}</td>
                <td>{n.sms ? "Yes" : "No"}</td>
                <td>
                  {n.company_name ?? (
                    <select aria-label={`Company for ${n.number}`} className={INPUT} value={pick[n.number ?? ""] ?? ""}
                      disabled={!n.sms} onChange={(e) => setPick({ ...pick, [n.number ?? ""]: e.target.value })}>
                      <option value="">Choose a company…</option>
                      {(companies.data?.items ?? []).map((c) => <option key={c.tenant_id} value={c.tenant_id}>{c.name}</option>)}
                    </select>
                  )}
                </td>
                <td>
                  {n.company_id ? (
                    <button type="button" className="btn btn-secondary btn-sm" disabled={assign.isPending}
                      onClick={() => { if (window.confirm(`Take ${n.number} away from ${n.company_name}?`)) assign.mutate({ company: n.company_id!, number: "" }); }}>
                      Remove
                    </button>
                  ) : (
                    <button type="button" className="btn btn-sm" disabled={assign.isPending || !pick[n.number ?? ""]}
                      onClick={() => assign.mutate({ company: pick[n.number ?? ""], number: n.number ?? "" })}>
                      Assign
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {assign.isError && <p className="mt-2 text-danger">{errorText(assign.error)}</p>}
    </div>
  );
}

// Super admin → Integrations (SPEC-FE-077 / SPEC-BE-113 FR3): health per provider,
// the recent errors log, and SMS number assignment. Never shows a secret.
export default function AdminIntegrations() {
  const health = useQuery({ queryKey: platformKeys.health, queryFn: fetchIntegrationHealth });
  const [provider, setProvider] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const errors = useQuery({ queryKey: platformKeys.errors(provider, cursor), queryFn: () => fetchIntegrationErrors(provider, cursor) });
  return (
    <section className="mb-8">
      <h2 className="section-title">Integrations health</h2>
      {health.isError && <p className="text-danger">{health.error.message}</p>}
      <div className="integrations-grid mb-4">
        {(health.data?.items ?? []).map((h) => (
          <div key={h.provider} className="integration-card">
            <div className="integration-header">
              <span className="integration-name">{h.label}</span>
              <span className={h.configured ? "badge badge-success" : "badge badge-neutral"}>{h.configured ? "Configured" : "Not set up"}</span>
            </div>
            <p className="text-[13px]">
              {h.companies_connected} compan{h.companies_connected === 1 ? "y" : "ies"} connected
              {h.companies_with_errors > 0 && <span className="text-danger"> · {h.companies_with_errors} with errors</span>}
            </p>
            {h.last_error && <p className="text-[12.5px] text-danger">Last test: {h.last_error}</p>}
            {h.last_ok_at && !h.last_error && <p className="text-[12.5px] text-muted">Last test OK {formatWhen(h.last_ok_at)}</p>}
          </div>
        ))}
      </div>
      <div className="mb-4"><SmsNumbers /></div>
      <div className="card" style={{ padding: 0 }}>
        <div className="flex items-center gap-2 px-4 pt-4">
          <p className="card-title m-0">Recent errors</p>
          <select aria-label="Provider" className={`${INPUT} ml-auto`} value={provider} onChange={(e) => { setProvider(e.target.value); setCursor(null); }}>
            <option value="">All providers</option>
            {(health.data?.items ?? []).map((h) => <option key={h.provider} value={h.provider}>{h.label}</option>)}
          </select>
        </div>
        <table>
          <thead><tr><th>When</th><th>Provider</th><th>Kind</th><th>Company</th><th>Message</th></tr></thead>
          <tbody>
            {errors.isPending ? (
              <tr><td colSpan={5} className="text-muted">Loading…</td></tr>
            ) : errors.isError ? (
              <tr><td colSpan={5} className="text-danger">{errors.error.message}</td></tr>
            ) : errors.data.items.length === 0 ? (
              <tr><td colSpan={5} className="text-muted">No errors recorded</td></tr>
            ) : (
              errors.data.items.map((e, i) => (
                <tr key={`${e.at}-${i}`}>
                  <td>{formatWhen(e.at)}</td>
                  <td>{e.provider}</td>
                  <td>{KIND[e.kind] ?? e.kind}</td>
                  <td>{e.company_name ?? "—"}</td>
                  <td className="text-[13px]">{e.message}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        {(cursor || errors.data?.next_cursor) && (
          <div className="flex justify-end gap-2 p-3">
            <button type="button" className="btn btn-secondary btn-sm" disabled={!cursor} onClick={() => setCursor(null)}>First page</button>
            <button type="button" className="btn btn-secondary btn-sm" disabled={!errors.data?.next_cursor} onClick={() => setCursor(errors.data?.next_cursor ?? null)}>Older</button>
          </div>
        )}
      </div>
    </section>
  );
}
