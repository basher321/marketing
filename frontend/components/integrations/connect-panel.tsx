"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import PasswordInput from "@/components/auth/password-input";
import { disconnectIntegration, integrationKeys, saveIntegration, testIntegration } from "@/lib/api/integrations";
import { metaConnectUrl } from "@/lib/api/meta";
import { ApiError } from "@/lib/types/common";
import type { CatalogProvider, IntegrationStatus, IntegrationTestResult } from "@/lib/types/integrations";

const FORBIDDEN = "Only managers and above can change integrations.";

/** A readable message: 403 in plain words; FastAPI 422 field errors joined; else the backend's text. */
export function apiErrorText(err: Error, forbidden: string): string {
  if (err instanceof ApiError) {
    if (err.status === 403) return forbidden;
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

// Connect / Manage side panel (SPEC-FE-037): the catalog's fields for one
// provider. Secrets are password fields showing only the masked saved value;
// leaving one empty keeps it. "Save & test" stores the credentials encrypted
// and runs the provider's real verification call (SPEC-BE-052).
export default function ConnectPanel({
  spec,
  status,
  onClose,
}: {
  spec: CatalogProvider;
  status: IntegrationStatus;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(spec.fields.map((f) => [f.key, f.secret ? "" : (status.masked[f.key] ?? "")])),
  );
  const [accountName, setAccountName] = useState(status.account_name ?? "");
  const [result, setResult] = useState<IntegrationTestResult | null>(null);
  const refresh = () => void queryClient.invalidateQueries({ queryKey: integrationKeys.list });
  const save = useMutation({
    mutationFn: () => saveIntegration(spec.provider, { account_name: accountName.trim() || null, fields: values }),
    onSuccess: (r) => {
      setResult(r);
      setValues((cur) => Object.fromEntries(Object.entries(cur).map(([k, v]) => [k, spec.fields.find((f) => f.key === k)?.secret ? "" : v])));
      refresh();
    },
  });
  const test = useMutation({
    mutationFn: () => testIntegration(spec.provider),
    onSuccess: (r) => {
      setResult(r);
      refresh();
    },
  });
  const disconnect = useMutation({
    mutationFn: () => disconnectIntegration(spec.provider),
    onSuccess: () => {
      refresh();
      onClose();
    },
  });
  // "Connect with Facebook" (SPEC-BE-054 / SPEC-FE-039): Facebook Login for
  // Business; Meta returns to /integrations/meta/callback.
  const connectMeta = useMutation({
    mutationFn: metaConnectUrl,
    onSuccess: (r) => {
      window.location.href = r.login_url;
    },
  });
  const [advanced, setAdvanced] = useState(false);
  const isMeta = spec.provider === "meta_ads";
  const err = save.error ?? test.error ?? disconnect.error ?? connectMeta.error;
  const hasSaved = status.configured_fields.length > 0;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" role="dialog" aria-modal="true" aria-label={`${spec.label} connection`} onClick={onClose}>
      <form
        className="h-full w-full max-w-[460px] overflow-y-auto bg-panel p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div className="mb-1 flex items-center justify-between">
          <h3 className="m-0">{spec.label}</h3>
          <button type="button" className="btn btn-ghost btn-sm" aria-label="Close" onClick={onClose}>
            ✕
          </button>
        </div>
        <p className="m-0 mb-4 text-xs text-muted">
          {spec.category} ·{" "}
          <a href={spec.docs_url} target="_blank" rel="noreferrer" className="text-accent">
            Where do I find these? ↗
          </a>
        </p>
        {isMeta && (
          <div className="mb-4">
            <button type="button" className="btn w-full" disabled={connectMeta.isPending} onClick={() => connectMeta.mutate()}>
              {connectMeta.isPending ? "Opening Facebook…" : status.status === "not_connected" ? "Connect with Facebook" : "Reconnect with Facebook"}
            </button>
            <button type="button" className="mt-2 text-xs text-muted underline" onClick={() => setAdvanced((v) => !v)}>
              {advanced ? "Hide" : "Advanced: paste a system user token instead"}
            </button>
          </div>
        )}
        {(!isMeta || advanced) && (
        <>
        <div className="form-row">
          <label htmlFor="ic_account">Account name (optional)</label>
          <input id="ic_account" maxLength={255} placeholder="e.g. Main ad account" value={accountName} onChange={(e) => setAccountName(e.target.value)} />
        </div>
        {spec.fields.map((f) => (
          <div className="form-row" key={f.key}>
            <label htmlFor={`ic_${f.key}`}>
              {f.label}
              {!f.required && <span className="font-normal text-muted"> (optional)</span>}
            </label>
            {f.secret ? (
              <PasswordInput
                id={`ic_${f.key}`}
                autoComplete="off"
                placeholder={status.masked[f.key] ? `Saved ${status.masked[f.key]} — leave empty to keep` : ""}
                value={values[f.key] ?? ""}
                onChange={(e) => setValues((cur) => ({ ...cur, [f.key]: e.target.value }))}
              />
            ) : (
              <input id={`ic_${f.key}`} value={values[f.key] ?? ""} onChange={(e) => setValues((cur) => ({ ...cur, [f.key]: e.target.value }))} />
            )}
            {f.help && <span className="text-xs text-muted">{f.help}</span>}
          </div>
        ))}
        </>
        )}
        {result && (
          <p className={`text-[13px] ${result.ok ? "text-success" : "text-danger"}`} role="status">
            {result.ok ? `✓ ${result.message}${result.account_name ? ` (${result.account_name})` : ""}` : `✗ ${result.message}`}
          </p>
        )}
        {err && (
          <p className="text-xs text-danger" role="alert">
            {apiErrorText(err, FORBIDDEN)}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          {(!isMeta || advanced) && (
            <button type="submit" className="btn btn-sm" disabled={save.isPending}>
              {save.isPending ? "Saving & testing…" : "Save & test"}
            </button>
          )}
          {hasSaved && (
            <button type="button" className="btn btn-secondary btn-sm" disabled={test.isPending} onClick={() => test.mutate()}>
              {test.isPending ? "Testing…" : "Test again"}
            </button>
          )}
          {status.status !== "not_connected" && (
            <button
              type="button"
              className="btn btn-ghost btn-sm text-danger"
              disabled={disconnect.isPending}
              onClick={() => {
                if (window.confirm(`Disconnect ${spec.label}? Saved credentials will be deleted.`)) disconnect.mutate();
              }}
            >
              Disconnect
            </button>
          )}
        </div>
        <p className="mb-0 mt-4 text-xs text-muted">
          Credentials are encrypted and never shown again. Connecting verifies them.
          {isMeta ? " Campaigns built in Campaigns are published to this Meta ad account." : " Publishing posts to this platform isn't active yet."}
        </p>
      </form>
    </div>
  );
}
