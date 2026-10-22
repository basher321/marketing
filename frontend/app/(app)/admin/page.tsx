"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";

import PasswordInput from "@/components/auth/password-input";
import AIModels from "@/components/integrations/ai-models";
import ConnectPanel, { type PanelOps } from "@/components/integrations/connect-panel";
import SideSheet from "@/components/ui/side-sheet";
import { fetchCatalog, integrationKeys } from "@/lib/api/integrations";
import {
  fetchCompanies,
  fetchCompanyIntegrations,
  fetchPlatformMe,
  fetchPlatformSettings,
  platformKeys,
  removeCompanyIntegration,
  saveCompanyAccess,
  saveCompanyIntegration,
  savePlatformSettings,
  testCompanyIntegration,
  testPlatformSettings,
} from "@/lib/api/platform";
import AdminIntegrations from "@/components/integrations/admin-health";
import type { AccessGroup, CompanyList, CompanyRow, SettingGroupRead } from "@/lib/types/platform";

// Super admin (SPEC-FE-068 / SPEC-BE-101): PilotSonic's own API keys, used by
// every company. Companies never enter keys; they only connect their pages.
// Only the Super admin gets data from /platform (anyone else: 404), so a
// company user who opens /admin just sees "Not found".

const HELP: Record<string, string> = {
  socialapi: "The master key from your SocialAPI.ai dashboard. Each company gets its own brand and a brand-restricted key made from it, so companies never see each other's pages.",
  zernio: "One Zernio key serves every company; each company works in its own Zernio profile.",
  meta_app: "The Meta app behind \"Connect with Facebook\" (ads and pages). Leave empty to keep using the server settings.",
  tiktok_app: "The TikTok developer app behind \"Connect with TikTok\".",
  linkedin_app: "The LinkedIn app behind \"Connect with LinkedIn\".",
};
const TESTABLE = new Set(["socialapi", "zernio"]);

function SettingCard({ data }: { data: SettingGroupRead }) {
  const qc = useQueryClient();
  const [values, setValues] = useState<Record<string, string>>({});
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const refresh = (d: SettingGroupRead) =>
    qc.setQueryData<SettingGroupRead[]>(platformKeys.settings, (cur) => (cur ?? []).map((g) => (g.group === d.group ? d : g)));
  const fail = (e: unknown) => setNote({ ok: false, text: e instanceof Error ? e.message : String(e) });
  const save = useMutation({
    mutationFn: (clear: string[]) => savePlatformSettings(data.group, Object.fromEntries(Object.entries(values).filter(([, v]) => v.trim())), clear),
    onSuccess: (d) => {
      refresh(d);
      setValues({});
      setNote({ ok: true, text: "Saved." });
    },
    onError: fail,
  });
  const test = useMutation({
    mutationFn: () => testPlatformSettings(data.group),
    onSuccess: (r) => {
      setNote({ ok: r.ok, text: r.message });
      void qc.invalidateQueries({ queryKey: platformKeys.settings });
    },
    onError: fail,
  });
  const busy = save.isPending || test.isPending;
  const anySet = data.fields.some((f) => f.set);
  const fromAdmin = data.fields.filter((f) => f.source === "admin").map((f) => f.field);
  return (
    <form
      className="integration-card"
      data-group={data.group}
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        setNote(null);
        save.mutate([]);
      }}
    >
      <div className="integration-header">
        <div className="integration-name">{data.label}</div>
        <span className={`badge ${data.last_error ? "badge-danger" : anySet ? "badge-success" : "badge-neutral"}`}>
          {data.last_error ? "Error" : anySet ? "Set" : "Not set"}
        </span>
      </div>
      <p className="m-0 mb-2 text-xs text-muted">{HELP[data.group]}</p>
      {data.fields.map((f) => (
        <div className="form-row mb-2" key={f.field}>
          <label htmlFor={`ps_${data.group}_${f.field}`} className="text-xs">
            {f.label}{" "}
            {f.set && (
              <span className="font-normal text-muted">
                ({f.value}
                {f.source === "server" ? ", from server settings" : ""})
              </span>
            )}
          </label>
          {f.secret ? (
            <PasswordInput
              id={`ps_${data.group}_${f.field}`}
              autoComplete="off"
              placeholder={f.set ? "Leave empty to keep it" : "Paste the value"}
              value={values[f.field] ?? ""}
              onChange={(e) => setValues((cur) => ({ ...cur, [f.field]: e.target.value }))}
            />
          ) : (
            <input
              id={`ps_${data.group}_${f.field}`}
              placeholder={f.set ? `Leave empty to keep ${f.value ?? "it"}` : ""}
              value={values[f.field] ?? ""}
              onChange={(e) => setValues((cur) => ({ ...cur, [f.field]: e.target.value }))}
            />
          )}
        </div>
      ))}
      {data.last_error && <p className="m-0 mb-2 text-xs text-danger">Last error: {data.last_error}</p>}
      <div className="flex flex-wrap gap-1.5">
        <button type="submit" className="btn btn-sm" disabled={busy || !Object.values(values).some((v) => v.trim())}>
          {save.isPending ? "Saving…" : "Save"}
        </button>
        {TESTABLE.has(data.group) && anySet && (
          <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => { setNote(null); test.mutate(); }}>
            {test.isPending ? "Testing…" : "Test"}
          </button>
        )}
        {fromAdmin.length > 0 && (
          <button
            type="button"
            className="btn btn-ghost btn-sm text-danger"
            disabled={busy}
            onClick={() => {
              if (window.confirm(`Remove the ${data.label} values saved here? The server settings (if any) apply again.`)) save.mutate(fromAdmin);
            }}
          >
            Remove
          </button>
        )}
      </div>
      {note && !busy && (
        <p className={`mb-0 mt-2 text-xs ${note.ok ? "text-success" : "text-danger"}`} role="status">
          {note.text}
        </p>
      )}
    </form>
  );
}

// SPEC-FE-080 / SPEC-BE-115: a company's API keys (store, email, CRM, WhatsApp
// token), which only the Super admin enters. The list is a side sheet; choosing
// a provider swaps it for the usual connect form, aimed at /platform/companies.
const KEY_BADGE: Record<string, string> = { connected: "badge-success", needs_reconnect: "badge-warn", not_connected: "badge-neutral" };
const KEY_LABEL: Record<string, string> = { connected: "Connected", needs_reconnect: "Reconnect", not_connected: "Not connected" };

function CompanyKeys({ row, onClose }: { row: CompanyRow; onClose: () => void }) {
  const [provider, setProvider] = useState<string | null>(null);
  const listKey = platformKeys.companyIntegrations(row.tenant_id);
  const list = useQuery({ queryKey: listKey, queryFn: () => fetchCompanyIntegrations(row.tenant_id) });
  const catalog = useQuery({ queryKey: integrationKeys.catalog, queryFn: fetchCatalog, staleTime: Infinity });
  const ops: PanelOps = {
    save: (p, body) => saveCompanyIntegration(row.tenant_id, p, body),
    test: (p) => testCompanyIntegration(row.tenant_id, p),
    disconnect: (p) => removeCompanyIntegration(row.tenant_id, p),
    listKey,
  };
  const spec = provider ? catalog.data?.find((p) => p.provider === provider) : undefined;
  const status = provider ? list.data?.find((i) => i.provider === provider) : undefined;
  if (spec && status) {
    return <ConnectPanel key={provider} spec={spec} status={status} ops={ops} onClose={() => setProvider(null)} />;
  }
  return (
    <SideSheet title={`API keys · ${row.name}`} onClose={onClose}>
      <p className="m-0 mb-3 text-xs text-muted">
        Only you enter these for {row.name}: they see the status (keys masked) and can test, but can&apos;t change them.
      </p>
      {list.isPending ? (
        <p className="text-[13px] text-muted">Loading…</p>
      ) : list.isError ? (
        <p className="text-[13px] text-danger" role="alert">
          Failed to load: {list.error.message}
        </p>
      ) : (
        <ul className="m-0 list-none p-0" data-testid="company-keys">
          {list.data.map((i) => (
            <li key={i.provider} className="flex items-center justify-between gap-2 border-b border-border py-2 last:border-0">
              <div>
                <div className="text-[13px] font-semibold">{i.name}</div>
                <div className="text-xs text-muted">
                  {i.category}
                  {i.account_name ? ` · ${i.account_name}` : ""}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className={`badge ${KEY_BADGE[i.status]}`}>{KEY_LABEL[i.status]}</span>
                <button type="button" className="btn btn-secondary btn-sm" disabled={!catalog.data} onClick={() => setProvider(i.provider)}>
                  {i.status === "not_connected" ? "Add keys" : "Manage"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </SideSheet>
  );
}

// SPEC-FE-069 / SPEC-BE-103: which companies may use each of PilotSonic's keys.
// Everything is on by default; a switched-off company gets a clear "PilotSonic
// hasn't enabled …" message instead of the service.
const PAGE_SIZE = 25;

function AccessSwitch({ row, group, label, page, q }: { row: CompanyRow; group: AccessGroup; label: string; page: number; q: string }) {
  const qc = useQueryClient();
  const key = platformKeys.companies(q, page);
  const on = row.access[group];
  const save = useMutation({
    mutationFn: (next: boolean) => saveCompanyAccess(row.tenant_id, { [group]: next }),
    onSuccess: (access) =>
      qc.setQueryData<CompanyList>(key, (cur) =>
        cur ? { ...cur, items: cur.items.map((r) => (r.tenant_id === row.tenant_id ? { ...r, access } : r)) } : cur,
      ),
    onError: (e) => window.alert(`Couldn't save: ${e instanceof Error ? e.message : String(e)}`),
  });
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={`${label} for ${row.name}`}
      title={on ? `${label}: allowed` : `${label}: switched off`}
      className="cc-switch"
      disabled={save.isPending}
      onClick={() => {
        if (on && !window.confirm(`Switch ${label} off for ${row.name}? They lose it right away.`)) return;
        save.mutate(!on);
      }}
    />
  );
}

function CompanyAccessSection() {
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [keysFor, setKeysFor] = useState<CompanyRow | null>(null);
  const list = useQuery({
    queryKey: platformKeys.companies(q, page),
    queryFn: () => fetchCompanies(q, page, PAGE_SIZE),
    placeholderData: keepPreviousData,
  });
  const pages = list.data ? Math.max(1, Math.ceil(list.data.total / list.data.page_size)) : 1;
  return (
    <section className="mb-8" data-testid="company-access">
      <h2 className="section-title">Companies</h2>
      <p className="m-0 mb-3 text-xs text-muted">
        Which companies may use PilotSonic&apos;s keys. Everything is on for a new company. Switching a key off stops it for
        that company at once; for the sign-in apps, accounts already connected keep working until their token runs out.
      </p>
      <form
        className="mb-3 flex flex-wrap gap-1.5"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          setPage(1);
          setQ(search);
        }}
      >
        <input
          aria-label="Search companies"
          placeholder="Search by name or slug"
          className="max-w-xs"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <button type="submit" className="btn btn-secondary btn-sm">
          Search
        </button>
      </form>
      {list.isPending ? (
        <p className="text-[13px] text-muted">Loading…</p>
      ) : list.isError ? (
        <p className="text-[13px] text-danger" role="alert">
          Failed to load: {list.error.message}
        </p>
      ) : list.data.items.length === 0 ? (
        <p className="text-[13px] text-muted">No companies match.</p>
      ) : (
        <>
          <div className="card overflow-x-auto">
            <table>
              <thead>
                <tr>
                  <th>Company</th>
                  {list.data.groups.map((g) => (
                    <th key={g.group} className="whitespace-nowrap">
                      {g.label.replace(/ \(.*\)$/, "")}
                    </th>
                  ))}
                  <th>Shared services</th>
                  <th>API keys</th>
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((row) => (
                  <tr key={row.tenant_id} data-slug={row.slug}>
                    <td>
                      <div className="font-semibold">{row.name}</div>
                      <div className="text-xs text-muted">
                        {row.slug}
                        {row.status !== "active" ? ` · ${row.status}` : ""}
                      </div>
                    </td>
                    {list.data.groups.map((g) => (
                      <td key={g.group}>
                        <AccessSwitch row={row} group={g.group} label={g.label} page={page} q={q} />
                      </td>
                    ))}
                    <td className="text-xs">
                      <div>SocialAPI brand: {row.socialapi_brand ? "yes" : "not yet"}</div>
                      <div>Zernio profile: {row.zernio_profile ? "yes" : "not yet"}</div>
                      {row.socialapi_error && <div className="text-danger">SocialAPI: {row.socialapi_error}</div>}
                    </td>
                    <td>
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => setKeysFor(row)}>
                        Keys
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {pages > 1 && (
            <div className="mt-2 flex items-center gap-2 text-xs text-muted">
              <button type="button" className="btn btn-secondary btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                Previous
              </button>
              Page {page} of {pages} · {list.data.total} companies
              <button type="button" className="btn btn-secondary btn-sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>
                Next
              </button>
            </div>
          )}
        </>
      )}
      {keysFor && <CompanyKeys key={keysFor.tenant_id} row={keysFor} onClose={() => setKeysFor(null)} />}
    </section>
  );
}

export default function SuperAdminPage() {
  const me = useQuery({ queryKey: platformKeys.me, queryFn: fetchPlatformMe });
  const settings = useQuery({ queryKey: platformKeys.settings, queryFn: fetchPlatformSettings, enabled: me.data?.super_admin === true });
  // /admin#platforms (Marketing › Social API Configuration): the section only exists once the page has
  // loaded, after the browser's own jump to the anchor, so scroll to it then.
  const ready = settings.isSuccess;
  useEffect(() => {
    if (ready && window.location.hash === "#platforms") document.getElementById("platforms")?.scrollIntoView({ block: "start" });
  }, [ready]);

  if (me.isPending) return <p className="text-[13px] text-muted">Loading…</p>;
  if (!me.data?.super_admin) {
    return (
      <div data-testid="admin-not-found">
        <h1 className="page-title">Not found</h1>
        <p className="page-subtitle mb-0">This page doesn&apos;t exist.</p>
      </div>
    );
  }
  return (
    <div data-testid="super-admin">
      <h1 className="page-title">Super admin</h1>
      <p className="page-subtitle">
        PilotSonic&apos;s own API keys, used by every company. Companies never enter keys: they only connect their own pages
        and accounts. Keys are stored encrypted and never shown again.
      </p>
      <AIModels admin />
      <CompanyAccessSection />
      <AdminIntegrations />
      {/* Marketing › Social API Configuration links here (SPEC-FE-080). */}
      <section className="mb-8 scroll-mt-24" id="platforms">
        <h2 className="section-title">Platforms and sign-in apps</h2>
        {settings.isPending ? (
          <p className="text-[13px] text-muted">Loading…</p>
        ) : settings.isError ? (
          <p className="text-[13px] text-danger" role="alert">
            Failed to load: {settings.error.message}
          </p>
        ) : (
          <div className="integrations-grid">
            {settings.data.map((g) => (
              <SettingCard key={g.group} data={g} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
