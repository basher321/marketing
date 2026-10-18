"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";

import { OrganicHeader, StatusBadge, errorText } from "@/components/organic/shared";
import { connectFromMeta, fetchSocialAccounts, oauthConnect, socialKeys } from "@/lib/api/social";
import { FLOW_LABEL, PLATFORM_FLOW, type SocialAccount, type SocialFlow, type TokenStatus } from "@/lib/types/social";

// SPEC-BE-101: pasted tokens are refused; a page connects by sign-in or, since
// SPEC-BE-104, through the company's SocialAPI account (Organic › SocialAPI).
const SOCIALAPI_HREF = "/marketing/organic/socialapi";

const TOKEN_LABEL: Record<TokenStatus, string> = {
  valid: "Valid",
  expiring_soon: "Expires soon",
  expired: "Expired",
  no_expiry: "Doesn't expire",
  unknown: "Unknown",
};
const TOKEN_CLASS: Partial<Record<TokenStatus, string>> = { expiring_soon: "text-warn", expired: "text-danger" };

const when = (v: string | null) => (v ? new Date(v).toLocaleString() : "—");

function ConnectButton({ account }: { account: SocialAccount }) {
  const flow: SocialFlow = PLATFORM_FLOW[account.platform];
  // The browser goes to the platform's sign-in; the backend made the URL (with a signed, single-use state).
  const connect = useMutation({ mutationFn: () => oauthConnect(flow), onSuccess: (r) => window.location.assign(r.login_url) });
  if (account.connected_via === "socialapi") return null;
  if (!account.oauth_available) {
    return account.status === "not_connected" ? (
      <p className="m-0 mb-1 text-xs text-muted">Connect it through SocialAPI (direct sign-in isn&apos;t set up in PilotSonic).</p>
    ) : null;
  }
  const reconnect =
    account.status === "expired" || account.status === "error" || account.token_status === "expired" || account.token_status === "expiring_soon";
  const label = account.status === "not_connected" ? `Connect with ${FLOW_LABEL[flow]}` : reconnect ? `Reconnect with ${FLOW_LABEL[flow]}` : null;
  if (!label) return null;
  return (
    <>
      <button type="button" className="btn btn-sm mr-2 mt-1" disabled={connect.isPending} onClick={() => connect.mutate()} data-testid={`connect-${account.platform}`}>
        {connect.isPending ? "Opening…" : label}
      </button>
      {connect.isError && <p className="m-0 mb-1 text-xs text-danger">{errorText(connect.error)}</p>}
    </>
  );
}

function Details({ a }: { a: SocialAccount }) {
  if (a.status === "not_connected" || !a.connected_via) return null;
  return (
    <dl className="m-0 mb-1 grid grid-cols-[auto_1fr] gap-x-3 text-xs">
      <dt className="text-muted">Connected via</dt>
      <dd className="m-0">{a.connected_via === "oauth" ? "Sign-in" : a.connected_via === "socialapi" ? "SocialAPI" : "Pasted token"}</dd>
      <dt className="text-muted">Account ID</dt>
      <dd className="m-0 break-all">{a.account_id ?? "—"}</dd>
      {a.connected_via === "socialapi" ? null : (
        <>
      <dt className="text-muted">Token</dt>
      <dd className={`m-0 ${a.token_status ? TOKEN_CLASS[a.token_status] ?? "" : ""}`}>
        {a.token_status ? TOKEN_LABEL[a.token_status] : "—"}
        {a.token_expires_at ? ` · expires ${when(a.token_expires_at)}` : ""}
        {a.reconnect_by && a.reconnect_by !== a.token_expires_at ? ` · reconnect by ${when(a.reconnect_by)}` : ""}
      </dd>
      <dt className="text-muted">Last checked</dt>
      <dd className="m-0">{when(a.last_checked_at)}</dd>
      <dt className="text-muted">Results sync</dt>
      <dd className="m-0">{when(a.last_synced_at)}</dd>
        </>
      )}
      {a.scopes.length > 0 && (
        <>
          <dt className="text-muted">Permissions</dt>
          <dd className="m-0">
            <details>
              <summary className="cursor-pointer">{a.scopes.length} granted</summary>
              {a.scopes.join(", ")}
            </details>
          </dd>
        </>
      )}
    </dl>
  );
}

// Connected Social Accounts (SPEC-FE-050 / SPEC-BE-075; sign-in and token
// status SPEC-FE-052 / SPEC-BE-080). Tokens stay on the backend; this page
// shows status, profile, capabilities, limits and connection details.
export default function AccountsPage() {
  const queryClient = useQueryClient();
  const accounts = useQuery({ queryKey: socialKeys.accounts, queryFn: fetchSocialAccounts });
  const fromMeta = useMutation({ mutationFn: connectFromMeta, onSuccess: () => void queryClient.invalidateQueries({ queryKey: socialKeys.accounts }) });
  return (
    <>
      <OrganicHeader
        title="Connected Social Accounts"
        subtitle="Where organic posts are published."
        action={
          <button type="button" className="btn btn-secondary" disabled={fromMeta.isPending} onClick={() => fromMeta.mutate()} title="Uses the Page (and Instagram account) of your Meta Ads connection">
            {fromMeta.isPending ? "Connecting…" : "Use my Meta connection"}
          </button>
        }
      />
      {fromMeta.data && <p className="text-xs text-success">{fromMeta.data.message}</p>}
      {fromMeta.isError && <p className="text-xs text-danger">{errorText(fromMeta.error)}</p>}
      {accounts.isError && <p className="text-[13px] text-danger">{errorText(accounts.error)}</p>}
      <div className="grid gap-4 md:grid-cols-2" data-testid="accounts-grid">
        {(accounts.data?.items ?? []).map((a) => (
          <div key={a.platform} className="card">
            <div className="mb-2 flex items-center gap-2">
              {a.avatar_url ? (
                <img src={a.avatar_url} alt="" className="h-9 w-9 rounded-full object-cover" />
              ) : (
                <div className="flex h-9 w-9 items-center justify-center rounded-full bg-accent-soft font-semibold">{a.label.slice(0, 1)}</div>
              )}
              <div className="min-w-0">
                <div className="font-semibold">{a.label}</div>
                <div className="truncate text-xs text-muted">
                  {a.account_name ?? "—"}
                  {a.handle ? ` · @${a.handle}` : ""}
                </div>
              </div>
              <span className="ml-auto">
                <StatusBadge status={a.status} />
              </span>
            </div>
            {a.status === "missing_permissions" && <p className="m-0 mb-1 text-xs text-warn">Missing: {a.missing_permissions.join(", ")}</p>}
            {a.last_error && a.status !== "connected" && <p className="m-0 mb-1 text-xs text-danger">{a.last_error}</p>}
            {a.status !== "not_connected" && (
              <p className="m-0 mb-1 text-xs text-muted">
                Can post:{" "}
                {Object.entries(a.capabilities)
                  .filter(([, v]) => v)
                  .map(([k]) => k.replace("_", " "))
                  .join(", ")}
                {typeof a.limits.caption_max === "number" ? ` · captions up to ${a.limits.caption_max.toLocaleString()} characters` : ""}
                {typeof a.limits.posts_used_24h === "number" ? ` · ${a.limits.posts_used_24h}/${String(a.limits.posts_per_24h)} API posts in 24 h` : ""}
              </p>
            )}
            <Details a={a} />
            {a.last_published_at && <p className="m-0 mb-1 text-xs text-muted">Last post: {new Date(a.last_published_at).toLocaleString()}</p>}
            {a.platform === "instagram" && a.status === "not_connected" && a.oauth_available && (
              <p className="m-0 mb-1 text-xs text-muted">Instagram connects through the Facebook Page it&apos;s linked to.</p>
            )}
            {a.notes.map((n) => (
              <p key={n} className="m-0 mb-1 text-xs text-muted">
                ℹ {n}
              </p>
            ))}
            <ConnectButton account={a} />
            {a.status === "not_connected" || a.connected_via === "socialapi" ? (
              <Link href={SOCIALAPI_HREF} className="btn btn-secondary btn-sm mt-1 inline-block no-underline">
                {a.connected_via === "socialapi" ? "Manage in Organic › SocialAPI" : "Connect through SocialAPI"}
              </Link>
            ) : (
              <Link href="/integrations" className="btn btn-secondary btn-sm mt-1 inline-block no-underline">
                Manage / test in Integrations
              </Link>
            )}
          </div>
        ))}
      </div>
    </>
  );
}
