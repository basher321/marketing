"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import MediaPicker from "@/components/organic/media-picker";
import { errorText, useCompanyTimezone } from "@/components/organic/shared";
import {
  ZERNIO_CHANNEL,
  boostPost,
  connectPlatform,
  createCampaign,
  disconnectAccount,
  fetchAdAccounts,
  fetchIdentities,
  fetchPlatforms,
  fetchPosts,
  fetchReach,
  previewCampaign,
  searchTargeting,
  validateCampaign,
  zernioKeys,
} from "@/lib/api/zernio";
import { formatMoney } from "@/lib/format/money";
import {
  emptyTargeting,
  type CityRef,
  type Entity,
  type GeoRef,
  type ZBoostCreate,
  type ZCampaignCreate,
  type ZPlatform,
  type ZPlatformInfo,
  type ZSearchHit,
  type ZTargeting,
} from "@/lib/types/zernio";
import { formatNumber } from "@/lib/format/number";

// Zernio "New campaign" wizard (SPEC-FE-055). Every option (goals, buttons,
// targeting fields, text limits, media kinds) comes from GET /zernio/platforms,
// so a platform only shows what Zernio accepts for it. The backend checks the
// same rules and its message is shown on the step it belongs to.

const STEPS = ["Platform", "Account", "Goal", "Budget & schedule", "Audience", "Ad", "Review"] as const;
const BOOST_GOALS = ["engagement", "traffic", "awareness", "video_views"];
const pretty = (s: string) => s.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase());

/** "YYYY-MM-DDTHH:mm" read as wall-clock time in `tz` -> UTC ISO. */
function zonedToUtcIso(local: string, tz: string): string | null {
  if (!local) return null;
  const [d, t] = local.split("T");
  const [y, mo, da] = d.split("-").map(Number);
  const [h, mi] = (t ?? "00:00").split(":").map(Number);
  const guess = Date.UTC(y, mo - 1, da, h, mi);
  try {
    const parts = Object.fromEntries(
      new Intl.DateTimeFormat("en-US", { timeZone: tz, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })
        .formatToParts(new Date(guess))
        .map((p) => [p.type, p.value]),
    );
    const asTz = Date.UTC(+parts.year, +parts.month - 1, +parts.day, +parts.hour, +parts.minute);
    return new Date(guess - (asTz - guess)).toISOString();
  } catch {
    return new Date(guess).toISOString();
  }
}

type Draft = {
  mode: "new" | "boost";
  platform: ZPlatform | null;
  account_id: string; // the ads account (or the posting account for a boost)
  ads_account_id: string; // boost: the ads connection whose ad accounts are listed
  ad_account_id: string;
  post_id: string;
  page_id: string;
  instagram_account_id: string;
  identity_id: string;
  organization_id: string;
  board_id: string;
  goal: string;
  campaign_type: "display" | "search";
  pixel_id: string;
  custom_event_type: string;
  application_id: string;
  object_store_url: string;
  lead_gen_form_id: string;
  budget_type: "daily" | "lifetime";
  amount: string;
  start: string;
  end: string;
  bid_strategy: string;
  bid_amount: string;
  roas_floor: string;
  targeting: ZTargeting;
  manual_placements: boolean;
  placements: Record<string, string[]>;
  special_ad_categories: string[];
  keywords: string;
  keyword_match: "exact" | "phrase" | "broad";
  headline: string;
  long_headline: string;
  body: string;
  description: string;
  call_to_action: string;
  link_url: string;
  media_id: string;
  square_media_id: string;
  name: string;
  status: "ACTIVE" | "PAUSED";
};

const START: Draft = {
  mode: "new", platform: null, account_id: "", ads_account_id: "", ad_account_id: "", post_id: "", page_id: "",
  instagram_account_id: "", identity_id: "", organization_id: "", board_id: "", goal: "", campaign_type: "display",
  pixel_id: "", custom_event_type: "", application_id: "", object_store_url: "", lead_gen_form_id: "",
  budget_type: "daily", amount: "", start: "", end: "", bid_strategy: "", bid_amount: "", roas_floor: "",
  targeting: emptyTargeting(), manual_placements: false, placements: {}, special_ad_categories: [], keywords: "",
  keyword_match: "broad", headline: "", long_headline: "", body: "", description: "", call_to_action: "", link_url: "",
  media_id: "", square_media_id: "", name: "", status: "PAUSED",
};

function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="mb-3 block text-[13px]">
      <span className="mb-1 block font-medium">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

function Counter({ value, limit }: { value: string; limit?: number }) {
  if (!limit) return null;
  return <span className={value.length > limit ? "text-danger" : ""}>{value.length}/{limit}</span>;
}

function Chips<T>({ items, label, onRemove }: { items: T[]; label: (t: T) => string; onRemove: (i: number) => void }) {
  if (!items.length) return null;
  return (
    <div className="mb-2 flex flex-wrap gap-1.5">
      {items.map((t, i) => (
        <span key={`${label(t)}-${i}`} className="badge badge-neutral flex items-center gap-1">
          {label(t)}
          <button type="button" aria-label={`Remove ${label(t)}`} className="text-muted" onClick={() => onRemove(i)}>
            ×
          </button>
        </span>
      ))}
    </div>
  );
}

/** Search Zernio's targeting catalog for this account and pick results. */
function SearchPicker({
  accountId,
  adAccountId,
  dimension,
  geoTypes,
  placeholder,
  onPick,
}: {
  accountId: string;
  adAccountId: string;
  dimension: "geo" | "interest" | "behavior";
  geoTypes?: string[];
  placeholder: string;
  onPick: (hit: ZSearchHit) => void;
}) {
  const [q, setQ] = useState("");
  const [geoType, setGeoType] = useState(geoTypes?.[0] ?? "");
  const [submitted, setSubmitted] = useState("");
  const results = useQuery({
    queryKey: zernioKeys.search(accountId, `${dimension}:${geoType}`, submitted),
    queryFn: () => searchTargeting({ account_id: accountId, q: submitted, dimension, geo_type: dimension === "geo" ? geoType : null, ad_account_id: adAccountId }),
    enabled: !!submitted && !!accountId,
  });
  return (
    <div className="mb-2">
      <div className="flex flex-wrap gap-2">
        {geoTypes && (
          <select value={geoType} onChange={(e) => setGeoType(e.target.value)} aria-label="Location type">
            {geoTypes.map((g) => (
              <option key={g} value={g}>
                {pretty(g)}
              </option>
            ))}
          </select>
        )}
        <input
          className="min-w-[200px] flex-1"
          value={q}
          placeholder={placeholder}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              setSubmitted(q.trim());
            }
          }}
        />
        <button type="button" className="btn btn-secondary btn-sm" disabled={!q.trim()} onClick={() => setSubmitted(q.trim())}>
          Search
        </button>
      </div>
      {results.isFetching && <p className="m-0 mt-1 text-xs text-muted">Searching…</p>}
      {results.isError && <p className="m-0 mt-1 text-xs text-danger">{errorText(results.error)}</p>}
      {results.data && (
        <ul className="m-0 mt-1 max-h-48 list-none overflow-auto rounded-md border border-border p-0">
          {results.data.items.length === 0 && <li className="p-2 text-xs text-muted">No matches.</li>}
          {results.data.items.map((h) => (
            <li key={`${h.type}-${h.id}`}>
              <button type="button" className="w-full p-2 text-left text-[13px] hover:bg-bg" onClick={() => onPick(h)}>
                {h.name}
                <span className="text-xs text-muted">
                  {h.type ? ` · ${h.type}` : ""}
                  {h.path ? ` · ${h.path}` : ""}
                  {h.audience_size ? ` · ~${h.audience_size.toLocaleString()} people` : ""}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const GEO_BUCKET: Record<string, "countries" | "regions" | "cities" | "zips" | "metros"> = {
  country: "countries", region: "regions", city: "cities", subcity: "cities", zip: "zips", metro_area: "metros", geo_market: "metros", metro: "metros",
};

export default function ZernioWizard() {
  const router = useRouter();
  const qc = useQueryClient();
  const tz = useCompanyTimezone();
  const [step, setStep] = useState(1);
  const [d, setD] = useState<Draft>(START);
  const [requestId] = useState(() => (globalThis.crypto?.randomUUID?.() ?? `${Date.now()}${Math.random()}`).replace(/[^A-Za-z0-9]/g, ""));
  const set = (patch: Partial<Draft>) => setD((prev) => ({ ...prev, ...patch }));
  const setT = (patch: Partial<ZTargeting>) => setD((prev) => ({ ...prev, targeting: { ...prev.targeting, ...patch } }));

  const platforms = useQuery({ queryKey: zernioKeys.platforms, queryFn: fetchPlatforms });
  const info: ZPlatformInfo | undefined = platforms.data?.platforms.find((p) => p.key === d.platform);
  const has = (cap: string) => !!info?.targeting.includes(cap);
  const family = d.platform === "facebook" || d.platform === "instagram" ? "meta" : d.platform;
  const listAccount = d.mode === "boost" ? d.ads_account_id : d.account_id;

  // The sign-in tab says when it finished, so the cards refresh without a reload.
  useEffect(() => {
    if (typeof BroadcastChannel === "undefined") return;
    const ch = new BroadcastChannel(ZERNIO_CHANNEL);
    ch.onmessage = () => void qc.invalidateQueries({ queryKey: zernioKeys.platforms });
    return () => ch.close();
  }, [qc]);

  const adAccounts = useQuery({ queryKey: zernioKeys.adAccounts(listAccount), queryFn: () => fetchAdAccounts(listAccount), enabled: !!listAccount });
  const adAccount = adAccounts.data?.items.find((a) => a.id === d.ad_account_id);
  const currency = adAccount?.currency ?? null;
  const identities = useQuery({
    queryKey: zernioKeys.identities(listAccount, d.ad_account_id),
    queryFn: () => fetchIdentities(listAccount, d.ad_account_id),
    enabled: !!listAccount && !!d.ad_account_id && (family === "meta" || family === "tiktok"),
  });
  const posts = useQuery({ queryKey: zernioKeys.posts(d.account_id), queryFn: () => fetchPosts(d.account_id), enabled: d.mode === "boost" && !!d.account_id });

  const connect = useMutation({
    mutationFn: ({ platform }: { platform: ZPlatform; tab: Window | null }) => connectPlatform(platform),
    onSuccess: (r, { tab }) => {
      if (!r.auth_url) {
        tab?.close();
        return void qc.invalidateQueries({ queryKey: zernioKeys.platforms });
      }
      if (tab && !tab.closed) tab.location.href = r.auth_url;
      else window.open(r.auth_url, "_blank", "noopener");
    },
    onError: (_e, { tab }) => tab?.close(),
  });
  const disconnect = useMutation({
    mutationFn: disconnectAccount,
    onSuccess: () => {
      set({ ...START, mode: d.mode });
      void qc.invalidateQueries({ queryKey: zernioKeys.all });
    },
  });

  const payload = useMemo((): ZCampaignCreate | null => {
    if (!d.platform) return null;
    const t = d.targeting;
    const bid = d.bid_strategy ? { strategy: d.bid_strategy, amount: d.bid_amount || null, roas_floor: d.roas_floor || null } : null;
    const po = { pixel_id: d.pixel_id || null, custom_event_type: d.custom_event_type || null, application_id: d.application_id || null, object_store_url: d.object_store_url || null };
    const keywords = d.keywords
      .split("\n")
      .map((k) => k.trim())
      .filter(Boolean)
      .map((text) => ({ text, match: d.keyword_match }));
    return {
      platform: d.platform,
      account_id: d.account_id,
      ad_account_id: d.ad_account_id,
      name: d.name.trim() || `${info?.label ?? d.platform} ${d.goal}`.trim(),
      goal: d.goal,
      campaign_type: d.platform === "googleads" ? d.campaign_type : null,
      budget: { amount: d.amount, type: d.budget_type },
      start_at: zonedToUtcIso(d.start, tz),
      end_at: zonedToUtcIso(d.end, tz),
      bid,
      targeting: t,
      placements: family === "meta" && d.manual_placements ? d.placements : null,
      special_ad_categories: family === "meta" ? d.special_ad_categories : [],
      creative: {
        headline: d.headline || null,
        long_headline: d.platform === "googleads" ? d.long_headline || null : null,
        body: d.body || null,
        description: family === "meta" ? d.description || null : null,
        call_to_action: d.call_to_action || null,
        link_url: d.link_url || null,
        media_id: d.media_id || null,
        square_media_id: d.platform === "googleads" && d.campaign_type === "display" ? d.square_media_id || null : null,
      },
      page_id: family === "meta" ? d.page_id || null : null,
      instagram_account_id: family === "meta" ? d.instagram_account_id || null : null,
      identity_id: family === "tiktok" ? d.identity_id || null : null,
      organization_id: family === "linkedin" ? d.organization_id || null : null,
      board_id: family === "pinterest" ? d.board_id || null : null,
      promoted_object: Object.values(po).some(Boolean) ? po : null,
      lead_gen_form_id: d.goal === "lead_generation" ? d.lead_gen_form_id || null : null,
      keywords: d.platform === "googleads" && d.campaign_type === "search" ? keywords : [],
      status: d.status,
      request_id: requestId,
    };
  }, [d, info, family, tz, requestId]);

  const boostPayload = (): ZBoostCreate => ({
    platform: d.platform as ZBoostCreate["platform"],
    account_id: d.account_id,
    ad_account_id: d.ad_account_id,
    post_id: d.post_id,
    name: d.name.trim() || `Boost ${d.post_id}`,
    goal: d.goal,
    budget: { amount: d.amount, type: d.budget_type },
    start_at: zonedToUtcIso(d.start, tz),
    end_at: zonedToUtcIso(d.end, tz),
    targeting: {
      countries: d.targeting.countries,
      regions: d.targeting.regions,
      cities: d.targeting.cities,
      age_min: d.targeting.age_min,
      age_max: d.targeting.age_max === null ? null : Math.min(d.targeting.age_max, 65),
      gender: d.targeting.gender,
      languages: d.targeting.languages,
      interests: d.targeting.interests,
    },
    status: d.status,
    request_id: requestId,
  });

  const publish = useMutation({
    mutationFn: () => (d.mode === "boost" ? boostPost(boostPayload()) : createCampaign(payload!)),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: zernioKeys.all });
      router.push("/marketing/paid?tab=zernio");
    },
  });
  const check = useMutation({ mutationFn: () => validateCampaign(payload!) });
  const preview = useMutation({ mutationFn: () => previewCampaign(payload!) });
  const reach = useMutation({ mutationFn: () => fetchReach({ platform: d.platform!, account_id: d.account_id, ad_account_id: d.ad_account_id, targeting: d.targeting }) });

  // What each step needs before Next (the backend checks everything again).
  const ready: Record<number, boolean> = {
    1: !!info && (d.mode === "boost" ? info.posting_accounts.length > 0 && info.connected : info.connected),
    2: !!d.account_id && !!d.ad_account_id && !!adAccount?.selectable && (d.mode === "new" || !!d.post_id),
    3: !!d.goal,
    4: Number(d.amount) > 0 && (d.budget_type === "daily" || !!d.end),
    5: true,
    6: true,
    7: true,
  };
  const go = (n: number) => setStep(d.mode === "boost" && n === 6 ? (step < 6 ? 7 : 5) : n);

  if (platforms.isPending) return <p className="text-[13px] text-muted">Loading platforms…</p>;
  if (platforms.isError) return <p className="text-[13px] text-danger">{errorText(platforms.error)}</p>;
  if (!platforms.data.configured)
    return (
      <div className="card">
        <p className="m-0 text-[13px]">Zernio isn&apos;t set up on this server yet. The administrator adds the server&apos;s Zernio key (ZERNIO_API_KEY), then every company can create campaigns here.</p>
      </div>
    );

  let body: ReactNode = null;
  if (step === 1) {
    body = (
      <>
        <div className="tabs mb-3" role="tablist" aria-label="What to create">
          {(["new", "boost"] as const).map((m) => (
            <button key={m} type="button" role="tab" aria-selected={d.mode === m} className={d.mode === m ? "tab active" : "tab"} onClick={() => set({ ...START, mode: m })}>
              {m === "new" ? "New ad" : "Boost an existing post"}
            </button>
          ))}
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {platforms.data.platforms
            .filter((p) => d.mode === "new" || p.key !== "googleads")
            .map((p) => (
              <div key={p.key} className={`card flex flex-col gap-2 ${d.platform === p.key ? "ring-2 ring-accent" : ""}`} data-testid={`zp-${p.key}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[15px] font-semibold">{p.label}</span>
                  <span className={`badge ${p.connected ? "badge-success" : "badge-neutral"}`}>{p.connected ? "Connected" : "Not connected"}</span>
                </div>
                {/* Every connected account uses one of the Zernio plan's slots (free plan: 2). */}
                {[...p.ads_accounts, ...p.posting_accounts].length === 0 ? (
                  <div className="text-xs text-muted">No accounts connected</div>
                ) : (
                  <ul className="m-0 grid list-none gap-1 p-0">
                    {[...p.ads_accounts.map((a) => ({ a, role: "ads" })), ...p.posting_accounts.map((a) => ({ a, role: "account" }))].map(({ a, role }) => (
                      <li key={a.id} className="flex items-center gap-1.5 text-xs">
                        <span className="min-w-0 flex-1 truncate text-muted">
                          {a.display_name ?? a.username ?? a.id} <span className="opacity-70">({role})</span>
                          {a.needs_reconnection && <span className="text-warn"> · needs reconnecting</span>}
                        </span>
                        <button
                          type="button"
                          className="text-danger underline"
                          disabled={disconnect.isPending}
                          onClick={() =>
                            window.confirm(`Disconnect ${a.display_name ?? a.username ?? a.id} from Zernio? Campaigns already on ${p.label} keep running there.`) &&
                            disconnect.mutate(a.id)
                          }
                        >
                          Disconnect
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                {d.mode === "boost" && p.posting_accounts.length === 0 && <div className="text-xs text-warn">Boosting needs the {p.label} account itself connected.</div>}
                <div className="mt-auto flex gap-2 pt-1">
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={connect.isPending}
                    onClick={() => connect.mutate({ platform: p.key, tab: window.open("about:blank", "_blank") })}
                  >
                    {p.connected ? "Reconnect ↗" : "Connect ↗"}
                  </button>
                  <button type="button" className="btn btn-sm" disabled={!p.connected} onClick={() => set({ ...START, mode: d.mode, platform: p.key })}>
                    {d.platform === p.key ? "Selected" : "Use"}
                  </button>
                </div>
              </div>
            ))}
        </div>
        {connect.isError && <p className="mt-2 text-xs text-danger">{errorText(connect.error)}</p>}
        {disconnect.isError && <p className="mt-2 text-xs text-danger">{errorText(disconnect.error)}</p>}
        {disconnect.isSuccess && <p className="mt-2 text-xs text-success">Disconnected. That Zernio slot is free again.</p>}
        <p className="mt-3 text-xs text-muted">Connect opens the platform&apos;s sign-in in a new tab. X asks twice: first the X account, then its ads account.</p>
      </>
    );
  } else if (step === 2 && info) {
    const accounts = d.mode === "boost" ? info.posting_accounts : info.ads_accounts;
    body = (
      <>
        <Field label={d.mode === "boost" ? `${info.label} account (the post's owner)` : `${info.label} ads connection`}>
          <select
            value={d.account_id}
            onChange={(e) => set({ account_id: e.target.value, ad_account_id: "", post_id: "", ads_account_id: d.mode === "boost" ? info.ads_accounts[0]?.id ?? "" : "" })}
          >
            <option value="">Choose…</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id} disabled={a.needs_reconnection}>
                {a.display_name ?? a.username ?? a.id}
                {a.needs_reconnection ? " (reconnect needed)" : ""}
              </option>
            ))}
          </select>
        </Field>
        {listAccount && (
          <Field label="Ad account" hint={adAccounts.isError ? <span className="text-danger">{errorText(adAccounts.error)}</span> : adAccount?.min_daily_budget ? `Minimum daily budget: ${formatMoney(adAccount.min_daily_budget, currency)}` : undefined}>
            <select value={d.ad_account_id} onChange={(e) => set({ ad_account_id: e.target.value })}>
              <option value="">{adAccounts.isPending ? "Loading…" : "Choose…"}</option>
              {(adAccounts.data?.items ?? []).map((a) => (
                <option key={a.id} value={a.id} disabled={!a.selectable}>
                  {a.name ?? a.id} · {a.currency ?? "?"} · {a.timezone ?? "?"}
                  {!a.selectable ? ` (can't be used: ${a.unusable_reason ?? "unavailable"})` : ""}
                </option>
              ))}
            </select>
          </Field>
        )}
        {d.mode === "boost" && d.account_id && (
          <Field label="Post to boost" hint={posts.isError ? <span className="text-danger">{errorText(posts.error)}</span> : undefined}>
            <select value={d.post_id} onChange={(e) => set({ post_id: e.target.value })}>
              <option value="">{posts.isPending ? "Loading posts…" : "Choose a post…"}</option>
              {(posts.data?.items ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {(p.message ?? "(no text)").slice(0, 80)} {p.created_at ? `· ${new Date(p.created_at).toLocaleDateString()}` : ""}
                </option>
              ))}
            </select>
          </Field>
        )}
        {d.mode === "new" && family === "meta" && d.ad_account_id && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Facebook Page the ad runs as" hint={`Default: ${identities.data?.pages.find((p) => p.id === identities.data?.default_page_id)?.name ?? "the connected Page"}`}>
              <select value={d.page_id} onChange={(e) => set({ page_id: e.target.value })}>
                <option value="">Default</option>
                {(identities.data?.pages ?? []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name ?? p.id}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Instagram account">
              <select value={d.instagram_account_id} onChange={(e) => set({ instagram_account_id: e.target.value })}>
                <option value="">Default</option>
                {(identities.data?.instagram_accounts ?? []).map((p) => (
                  <option key={p.id} value={p.id}>
                    @{p.name ?? p.id} {p.detail ? `(${p.detail})` : ""}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        )}
        {d.mode === "new" && family === "tiktok" && d.ad_account_id && (
          <Field label="TikTok identity (the profile shown on the ad)">
            <select value={d.identity_id} onChange={(e) => set({ identity_id: e.target.value })}>
              <option value="">Default</option>
              {(identities.data?.tiktok_identities ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name ?? p.id} ({pretty(p.kind)})
                </option>
              ))}
            </select>
          </Field>
        )}
        {d.mode === "new" && family === "linkedin" && (
          <Field label="LinkedIn Company Page id (optional)" hint="Leave empty to use the connected Company Page.">
            <input value={d.organization_id} onChange={(e) => set({ organization_id: e.target.value.trim() })} placeholder="e.g. 12345678" />
          </Field>
        )}
        {d.mode === "new" && family === "pinterest" && (
          <Field label="Pinterest board id (optional)" hint="Leave empty and Zernio creates a board for the ad.">
            <input value={d.board_id} onChange={(e) => set({ board_id: e.target.value.trim() })} />
          </Field>
        )}
      </>
    );
  } else if (step === 3 && info) {
    const goals = d.mode === "boost" ? info.goals.filter((g) => BOOST_GOALS.includes(g.key)) : info.goals;
    body = (
      <>
        {d.platform === "googleads" && d.mode === "new" && (
          <Field label="Google campaign type">
            <select value={d.campaign_type} onChange={(e) => set({ campaign_type: e.target.value as Draft["campaign_type"], media_id: "", square_media_id: "" })}>
              <option value="display">Display: image ads across Google&apos;s sites and apps</option>
              <option value="search">Search: text ads on Google search results (needs keywords)</option>
            </select>
          </Field>
        )}
        <div className="grid gap-2">
          {goals.map((g) => (
            <label key={g.key} className={`flex cursor-pointer items-center gap-2 rounded-md border p-2 text-[13px] ${d.goal === g.key ? "border-accent" : "border-border"}`}>
              <input type="radio" name="goal" checked={d.goal === g.key} onChange={() => set({ goal: g.key })} />
              {g.label}
            </label>
          ))}
        </div>
        {(d.goal === "conversions" || d.goal === "lead_conversion") && d.mode === "new" && (family === "meta" || family === "tiktok") && (
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <Field label="Pixel id">
              <input value={d.pixel_id} onChange={(e) => set({ pixel_id: e.target.value.trim() })} />
            </Field>
            <Field label="Event to optimise for" hint={family === "meta" ? "e.g. PURCHASE (sales) or LEAD (leads)" : "Optional, e.g. SHOPPING"}>
              <input value={d.custom_event_type} onChange={(e) => set({ custom_event_type: e.target.value.trim().toUpperCase() })} />
            </Field>
          </div>
        )}
        {d.goal === "app_promotion" && family === "meta" && d.mode === "new" && (
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <Field label="App id">
              <input value={d.application_id} onChange={(e) => set({ application_id: e.target.value.trim() })} />
            </Field>
            <Field label="App store URL">
              <input value={d.object_store_url} onChange={(e) => set({ object_store_url: e.target.value.trim() })} placeholder="https://play.google.com/store/apps/details?id=…" />
            </Field>
          </div>
        )}
        {d.goal === "lead_generation" && (family === "meta" || family === "linkedin") && d.mode === "new" && (
          <Field label="Lead form id" hint="The instant form (Meta) or Lead Gen form (LinkedIn) people fill in.">
            <input value={d.lead_gen_form_id} onChange={(e) => set({ lead_gen_form_id: e.target.value.trim() })} />
          </Field>
        )}
      </>
    );
  } else if (step === 4 && info) {
    body = (
      <>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Budget type">
            <select value={d.budget_type} onChange={(e) => set({ budget_type: e.target.value as Draft["budget_type"] })}>
              <option value="daily">Daily: spend up to this each day</option>
              <option value="lifetime">Lifetime: spend up to this in total</option>
            </select>
          </Field>
          <Field
            label={`Amount (${currency ?? "ad account currency"})`}
            hint={`${Number(d.amount) > 0 ? formatMoney(Number(d.amount), currency) : ""}${adAccount?.min_daily_budget ? ` · minimum daily ${formatMoney(adAccount.min_daily_budget, currency)}` : ""}`}
          >
            <input type="number" min="0" step="0.01" inputMode="decimal" value={d.amount} onChange={(e) => set({ amount: e.target.value })} />
          </Field>
          <Field label={`Start (${tz})`} hint="Empty = start as soon as it's approved.">
            <input type="datetime-local" value={d.start} onChange={(e) => set({ start: e.target.value })} />
          </Field>
          <Field label={`End (${tz})`} hint={d.budget_type === "lifetime" ? "Required for a lifetime budget." : "Optional."}>
            <input type="datetime-local" value={d.end} onChange={(e) => set({ end: e.target.value })} />
          </Field>
        </div>
        {info.bid && d.mode === "new" && (
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Bid strategy">
              <select value={d.bid_strategy} onChange={(e) => set({ bid_strategy: e.target.value, bid_amount: "", roas_floor: "" })}>
                <option value="">Platform default</option>
                {info.bid_strategies.map((b) => (
                  <option key={b} value={b}>
                    {pretty(b)}
                  </option>
                ))}
              </select>
            </Field>
            {(d.bid_strategy === "LOWEST_COST_WITH_BID_CAP" || d.bid_strategy === "COST_CAP") && (
              <Field label={`Bid amount (${currency ?? ""})`}>
                <input type="number" min="0" step="0.01" value={d.bid_amount} onChange={(e) => set({ bid_amount: e.target.value })} />
              </Field>
            )}
            {d.bid_strategy === "LOWEST_COST_WITH_MIN_ROAS" && (
              <Field label="Minimum ROAS (e.g. 2.0)">
                <input type="number" min="0" step="0.1" value={d.roas_floor} onChange={(e) => set({ roas_floor: e.target.value })} />
              </Field>
            )}
          </div>
        )}
      </>
    );
  } else if (step === 5 && info) {
    const t = d.targeting;
    const boost = d.mode === "boost";
    const geoTypes = ["country", "region", "city", ...(has("zips") && !boost ? ["zip"] : []), ...(has("metros") && !boost ? ["metro_area"] : [])];
    const addGeo = (h: ZSearchHit, exclude = false) => {
      const bucket = GEO_BUCKET[h.type ?? ""] ?? "cities";
      if (exclude) {
        const ex = t.excluded ?? { countries: [], regions: [], cities: [], zips: [] };
        if (bucket === "countries") setT({ excluded: { ...ex, countries: [...ex.countries, h.country_code ?? h.id] } });
        else if (bucket === "regions" || bucket === "cities" || bucket === "zips") setT({ excluded: { ...ex, [bucket]: [...ex[bucket], { key: h.id, name: h.name }] } });
        return;
      }
      if (bucket === "countries") setT({ countries: Array.from(new Set([...t.countries, (h.country_code ?? h.id).toUpperCase()])) });
      else setT({ [bucket]: [...(t[bucket] as GeoRef[]), { key: h.id, name: h.name }] } as Partial<ZTargeting>);
    };
    const geoName = (g: GeoRef) => g.name ?? g.key;
    body = (
      <>
        <h3 className="m-0 mb-2 text-[14px] font-semibold">Places</h3>
        <SearchPicker accountId={d.mode === "boost" ? d.account_id : d.account_id} adAccountId={d.ad_account_id} dimension="geo" geoTypes={geoTypes} placeholder="Search a country, region or city" onPick={(h) => addGeo(h)} />
        <Chips items={t.countries} label={(c) => c} onRemove={(i) => setT({ countries: t.countries.filter((_, j) => j !== i) })} />
        <Chips items={t.regions} label={geoName} onRemove={(i) => setT({ regions: t.regions.filter((_, j) => j !== i) })} />
        {t.cities.map((c, i) => (
          <div key={`${c.key}-${i}`} className="mb-1.5 flex flex-wrap items-center gap-2 text-[13px]">
            <span className="badge badge-neutral">{geoName(c)}</span>
            {has("city_radius") && (
              <>
                <input
                  type="number"
                  min="0"
                  max="500"
                  className="w-20"
                  placeholder="radius"
                  value={c.radius ?? ""}
                  onChange={(e) => {
                    const v = e.target.value ? Number(e.target.value) : null;
                    setT({ cities: t.cities.map((x, j): CityRef => (j === i ? { ...x, radius: v, distance_unit: v ? x.distance_unit ?? "kilometer" : null } : x)) });
                  }}
                />
                <select
                  value={c.distance_unit ?? "kilometer"}
                  onChange={(e) => setT({ cities: t.cities.map((x, j): CityRef => (j === i ? { ...x, distance_unit: e.target.value as CityRef["distance_unit"] } : x)) })}
                >
                  <option value="kilometer">km</option>
                  <option value="mile">miles</option>
                </select>
              </>
            )}
            <button type="button" className="text-muted" onClick={() => setT({ cities: t.cities.filter((_, j) => j !== i) })}>
              Remove
            </button>
          </div>
        ))}
        <Chips items={t.zips} label={geoName} onRemove={(i) => setT({ zips: t.zips.filter((_, j) => j !== i) })} />
        <Chips items={t.metros} label={geoName} onRemove={(i) => setT({ metros: t.metros.filter((_, j) => j !== i) })} />
        {has("custom_locations") && !boost && <PinEditor value={t.custom_locations} onChange={(v) => setT({ custom_locations: v })} />}
        {has("excluded_locations") && !boost && (
          <details className="mb-3">
            <summary className="cursor-pointer text-[13px]">Exclude places</summary>
            <SearchPicker accountId={d.account_id} adAccountId={d.ad_account_id} dimension="geo" geoTypes={["country", "region", "city", "zip"]} placeholder="Search a place to leave out" onPick={(h) => addGeo(h, true)} />
            {t.excluded && (
              <Chips
                items={[...t.excluded.countries.map((c) => ({ k: "countries" as const, key: c, name: c })), ...(["regions", "cities", "zips"] as const).flatMap((k) => t.excluded![k].map((g) => ({ k, key: g.key, name: g.name ?? g.key })))]}
                label={(x) => `not ${x.name}`}
                onRemove={(i) => {
                  const all = [...t.excluded!.countries.map((c) => ({ k: "countries" as const, key: c })), ...(["regions", "cities", "zips"] as const).flatMap((k) => t.excluded![k].map((g) => ({ k, key: g.key })))];
                  const gone = all[i];
                  const ex = { ...t.excluded! };
                  if (gone.k === "countries") ex.countries = ex.countries.filter((c) => c !== gone.key);
                  else ex[gone.k] = ex[gone.k].filter((g) => g.key !== gone.key);
                  setT({ excluded: ex });
                }}
              />
            )}
          </details>
        )}
        <h3 className="m-0 mb-2 mt-4 text-[14px] font-semibold">People</h3>
        <div className="grid gap-3 sm:grid-cols-4">
          {(has("age") || boost) && (
            <>
              <Field label="Age from">
                <input type="number" min="13" max={boost ? 65 : 100} value={t.age_min ?? ""} onChange={(e) => setT({ age_min: e.target.value ? Number(e.target.value) : null })} />
              </Field>
              <Field label="Age to">
                <input type="number" min="13" max={boost ? 65 : 100} value={t.age_max ?? ""} onChange={(e) => setT({ age_max: e.target.value ? Number(e.target.value) : null })} />
              </Field>
            </>
          )}
          {(has("gender") || boost) && (
            <Field label="Gender">
              <select value={t.gender} onChange={(e) => setT({ gender: e.target.value as ZTargeting["gender"] })}>
                <option value="all">Everyone</option>
                <option value="female">Women</option>
                <option value="male">Men</option>
              </select>
            </Field>
          )}
          {(has("languages") || boost) && (
            <Field label="Languages" hint="Codes, comma-separated (e.g. en, bn)">
              <input
                value={t.languages.join(", ")}
                onChange={(e) => setT({ languages: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })}
              />
            </Field>
          )}
        </div>
        {(has("interests") || boost) && (
          <>
            <span className="mb-1 block text-[13px] font-medium">Interests</span>
            <SearchPicker accountId={d.account_id} adAccountId={d.ad_account_id} dimension="interest" placeholder="Search interests (e.g. fashion)" onPick={(h) => setT({ interests: [...t.interests, { id: h.id, name: h.name }] })} />
            <Chips items={t.interests} label={(x: Entity) => x.name} onRemove={(i) => setT({ interests: t.interests.filter((_, j) => j !== i) })} />
          </>
        )}
        {has("behaviors") && !boost && (
          <>
            <span className="mb-1 block text-[13px] font-medium">Behaviours</span>
            <SearchPicker accountId={d.account_id} adAccountId={d.ad_account_id} dimension="behavior" placeholder="Search behaviours (e.g. travelers)" onPick={(h) => setT({ behaviors: [...t.behaviors, { id: h.id, name: h.name }] })} />
            <Chips items={t.behaviors} label={(x: Entity) => x.name} onRemove={(i) => setT({ behaviors: t.behaviors.filter((_, j) => j !== i) })} />
          </>
        )}
        {info.income_tiers.length > 0 && !boost && (
          <Field label="Household income">
            <select value={t.income_tier ?? ""} onChange={(e) => setT({ income_tier: e.target.value || null })}>
              <option value="">Any</option>
              {info.income_tiers.map((x) => (
                <option key={x} value={x}>
                  {pretty(x).replace("Top ", "Top ").replace(/_/g, "–")}%
                </option>
              ))}
            </select>
          </Field>
        )}
        {d.platform === "googleads" && d.campaign_type === "search" && !boost && (
          <>
            <h3 className="m-0 mb-2 mt-4 text-[14px] font-semibold">Keywords</h3>
            <div className="grid gap-3 sm:grid-cols-[1fr_180px]">
              <Field label="One keyword per line">
                <textarea rows={4} value={d.keywords} onChange={(e) => set({ keywords: e.target.value })} />
              </Field>
              <Field label="Match type">
                <select value={d.keyword_match} onChange={(e) => set({ keyword_match: e.target.value as Draft["keyword_match"] })}>
                  <option value="broad">Broad</option>
                  <option value="phrase">Phrase</option>
                  <option value="exact">Exact</option>
                </select>
              </Field>
            </div>
          </>
        )}
        {family === "meta" && !boost && (
          <>
            <h3 className="m-0 mb-2 mt-4 text-[14px] font-semibold">Placements</h3>
            <label className="mr-4 text-[13px]">
              <input type="radio" checked={!d.manual_placements} onChange={() => set({ manual_placements: false })} /> Automatic (recommended)
            </label>
            <label className="text-[13px]">
              <input type="radio" checked={d.manual_placements} onChange={() => set({ manual_placements: true, placements: { publisher_platforms: ["facebook", "instagram"] } })} /> Manual
            </label>
            {d.manual_placements && (
              <div className="mt-2 grid gap-2">
                {Object.entries(info.placements).map(([group, options]) => (
                  <div key={group} className="text-[13px]">
                    <span className="mb-1 block font-medium">{pretty(group)}</span>
                    <div className="flex flex-wrap gap-3">
                      {options.map((o) => (
                        <label key={o} className="flex items-center gap-1">
                          <input
                            type="checkbox"
                            checked={(d.placements[group] ?? []).includes(o)}
                            onChange={(e) => {
                              const cur = d.placements[group] ?? [];
                              set({ placements: { ...d.placements, [group]: e.target.checked ? [...cur, o] : cur.filter((x) => x !== o) } });
                            }}
                          />
                          {pretty(o)}
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
            <h3 className="m-0 mb-2 mt-4 text-[14px] font-semibold">Special ad categories</h3>
            <p className="m-0 mb-1 text-xs text-muted">Tick one if the ad is about housing, jobs, credit, finance, politics or gambling (Meta limits targeting for these).</p>
            <div className="flex flex-wrap gap-3 text-[13px]">
              {info.special_ad_categories.map((c) => (
                <label key={c} className="flex items-center gap-1">
                  <input
                    type="checkbox"
                    checked={d.special_ad_categories.includes(c)}
                    onChange={(e) => set({ special_ad_categories: e.target.checked ? [...d.special_ad_categories, c] : d.special_ad_categories.filter((x) => x !== c) })}
                  />
                  {pretty(c)}
                </label>
              ))}
            </div>
          </>
        )}
        {!boost && (
          <div className="mt-4 flex items-center gap-3">
            <button type="button" className="btn btn-secondary btn-sm" disabled={reach.isPending} onClick={() => reach.mutate()}>
              {reach.isPending ? "Estimating…" : "Estimate reach"}
            </button>
            {reach.data &&
              (reach.data.available ? (
                <span className="text-[13px]">
                  About {reach.data.lower?.toLocaleString()}–{reach.data.upper?.toLocaleString()} people
                  {reach.data.daily ? ` · ~${reach.data.daily.toLocaleString()} a day` : ""}
                </span>
              ) : (
                <span className="text-[13px] text-muted">{info.label} gives no reach estimate before the campaign runs.</span>
              ))}
            {reach.isError && <span className="text-xs text-danger">{errorText(reach.error)}</span>}
          </div>
        )}
      </>
    );
  } else if (step === 6 && info) {
    const search = d.platform === "googleads" && d.campaign_type === "search";
    const display = d.platform === "googleads" && d.campaign_type === "display";
    const lim = info.limits;
    const mediaKind = info.media.length === 1 ? (info.media[0] as "image" | "video") : undefined;
    body = (
      <>
        {d.platform !== "tiktok" && (
          <Field label="Headline" hint={<Counter value={d.headline} limit={lim.headline} />}>
            <input value={d.headline} onChange={(e) => set({ headline: e.target.value })} />
          </Field>
        )}
        {d.platform === "googleads" && (
          <Field label="Long headline (optional)" hint={<Counter value={d.long_headline} limit={lim.long_headline} />}>
            <input value={d.long_headline} onChange={(e) => set({ long_headline: e.target.value })} />
          </Field>
        )}
        <Field label={d.platform === "twitter" ? "Post text" : "Main text"} hint={<Counter value={d.body} limit={lim.body} />}>
          <textarea rows={4} value={d.body} onChange={(e) => set({ body: e.target.value })} />
        </Field>
        {family === "meta" && (
          <Field label="Link description (optional)" hint={<Counter value={d.description} limit={lim.description} />}>
            <input value={d.description} onChange={(e) => set({ description: e.target.value })} />
          </Field>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          {info.ctas.length > 0 && (
            <Field label="Button">
              <select value={d.call_to_action} onChange={(e) => set({ call_to_action: e.target.value })}>
                <option value="">{family === "meta" ? "Choose…" : "None"}</option>
                {info.ctas.map((c) => (
                  <option key={c} value={c}>
                    {pretty(c)}
                  </option>
                ))}
              </select>
            </Field>
          )}
          <Field label="Link (where people go)">
            <input type="url" value={d.link_url} onChange={(e) => set({ link_url: e.target.value.trim() })} placeholder="https://" />
          </Field>
        </div>
        {!search && (
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <span className="mb-1 block text-[13px] font-medium">
                {display ? "Landscape image (1.91:1)" : mediaKind === "video" ? "Video" : info.media.length > 1 ? "Image or video" : "Image"}
              </span>
              <MediaPicker value={d.media_id ? [d.media_id] : []} onChange={(ids) => set({ media_id: ids[0] ?? "" })} kind={display ? "image" : mediaKind} max={1} />
            </div>
            {display && (
              <div>
                <span className="mb-1 block text-[13px] font-medium">Square image (1:1)</span>
                <MediaPicker value={d.square_media_id ? [d.square_media_id] : []} onChange={(ids) => set({ square_media_id: ids[0] ?? "" })} kind="image" max={1} />
              </div>
            )}
          </div>
        )}
        {search && <p className="text-xs text-muted">Google Search ads are text only.</p>}
        {info.preview_supported && (
          <div className="mt-3">
            <button type="button" className="btn btn-secondary btn-sm" disabled={preview.isPending || !d.media_id} onClick={() => preview.mutate()}>
              {preview.isPending ? "Rendering…" : "Preview on Facebook & Instagram"}
            </button>
            {preview.isError && <p className="text-xs text-danger">{errorText(preview.error)}</p>}
            {preview.data && !preview.data.supported && <p className="text-xs text-muted">Previews are shown for image ads.</p>}
            {preview.data?.supported && (
              <div className="mt-2 grid gap-3 sm:grid-cols-2">
                {preview.data.items.map((p) => {
                  const src = previewSrc(p.html);
                  return (
                    <div key={p.format}>
                      <span className="text-xs text-muted">{pretty(p.format)}</span>
                      {src ? (
                        <iframe title={p.format} className="h-[420px] w-full rounded-md border border-border" src={src} />
                      ) : (
                        <p className="m-0 text-xs text-muted">No preview for this placement.</p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </>
    );
  } else if (step === 7 && info) {
    const t = d.targeting;
    const places = [...t.countries, ...t.regions.map((r) => r.name ?? r.key), ...t.cities.map((c) => `${c.name ?? c.key}${c.radius ? ` +${c.radius} ${c.distance_unit === "mile" ? "mi" : "km"}` : ""}`)];
    const rows: [string, string][] = [
      ["Platform", `${info.label}${d.mode === "boost" ? " · boost a post" : ""}`],
      ["Ad account", `${adAccount?.name ?? d.ad_account_id} (${currency ?? "?"})`],
      ["Goal", info.goals.find((g) => g.key === d.goal)?.label ?? d.goal],
      ["Budget", `${formatMoney(Number(d.amount || 0), currency)} ${d.budget_type}`],
      ["Schedule", `${d.start ? d.start.replace("T", " ") : "As soon as approved"} → ${d.end ? d.end.replace("T", " ") : "no end"} (${tz})`],
      ["Places", places.join(", ") || "Everywhere the platform allows"],
      ["People", `${t.age_min ?? "any"}–${t.age_max ?? "any"} · ${t.gender === "all" ? "everyone" : t.gender}${t.interests.length ? ` · ${t.interests.map((i) => i.name).join(", ")}` : ""}`],
    ];
    if (d.mode === "new") rows.push(["Ad", `${d.headline || "(no headline)"} · ${d.call_to_action ? pretty(d.call_to_action) : "no button"} · ${d.link_url || "no link"}`]);
    body = (
      <>
        <Field label="Campaign name">
          <input value={d.name} onChange={(e) => set({ name: e.target.value })} placeholder={`${info.label} ${d.goal}`} />
        </Field>
        <table className="mb-3">
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k}>
                <th className="w-40">{k}</th>
                <td>{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {d.mode === "new" && (
          <div className="mb-3">
            <button type="button" className="btn btn-secondary btn-sm" disabled={check.isPending} onClick={() => check.mutate()}>
              {check.isPending ? "Checking…" : "Check with platform"}
            </button>
            {check.data && <p className={`m-0 mt-1 text-xs ${check.data.ok ? (check.data.supported ? "text-success" : "text-muted") : "text-danger"}`}>{check.data.message}</p>}
            {check.isError && <p className="m-0 mt-1 text-xs text-danger">{errorText(check.error)}</p>}
          </div>
        )}
        <div className="mb-3 flex flex-wrap gap-4 text-[13px]">
          <label className="flex items-center gap-1.5">
            <input type="radio" checked={d.status === "PAUSED"} onChange={() => set({ status: "PAUSED" })} /> Create paused (resume it later from the Zernio tab)
          </label>
          <label className="flex items-center gap-1.5">
            <input type="radio" checked={d.status === "ACTIVE"} onChange={() => set({ status: "ACTIVE" })} /> Publish live (spends money once approved)
          </label>
        </div>
        {publish.isError && <p className="text-[13px] text-danger">{errorText(publish.error)}</p>}
        <button type="button" className="btn" disabled={publish.isPending} onClick={() => publish.mutate()}>
          {publish.isPending ? "Sending to the platform…" : d.status === "ACTIVE" ? "Publish live" : "Create paused"}
        </button>
      </>
    );
  }

  const shownSteps = STEPS.map((label, i) => ({ label, n: i + 1 })).filter((s) => !(d.mode === "boost" && s.n === 6));
  return (
    <div>
      <ol className="m-0 mb-4 flex list-none flex-wrap gap-1.5 p-0" aria-label="Steps">
        {shownSteps.map((s, i) => (
          <li key={s.label}>
            <button
              type="button"
              aria-current={step === s.n ? "step" : undefined}
              disabled={s.n > step && !shownSteps.slice(0, i).every((p) => ready[p.n])}
              className={step === s.n ? "btn btn-sm" : "btn btn-secondary btn-sm"}
              onClick={() => setStep(s.n)}
            >
              {i + 1}. {s.label}
            </button>
          </li>
        ))}
      </ol>
      <section className="card mb-4">{body}</section>
      <div className="flex justify-between">
        {step > 1 ? (
          <button type="button" className="btn btn-secondary" onClick={() => go(step - 1)}>
            Back
          </button>
        ) : (
          <Link href="/marketing/paid/ad-manager" className="btn btn-secondary">
            Cancel
          </Link>
        )}
        {step < 7 && (
          <button type="button" className="btn" disabled={!ready[step]} onClick={() => go(step + 1)}>
            Next
          </button>
        )}
      </div>
    </div>
  );
}

/** Meta's preview is an <iframe src="https://www.facebook.com/ads/api/preview_iframe.php?..."> snippet.
 * Only that facebook.com address is used (never the raw HTML), so nothing in the
 * answer can run on this page. */
function previewSrc(html: string | null): string | null {
  const m = html?.match(/src="([^"]+)"/i);
  if (!m) return null;
  try {
    const url = new URL(m[1].replace(/&amp;/g, "&"));
    return url.protocol === "https:" && (url.hostname === "facebook.com" || url.hostname.endsWith(".facebook.com")) ? url.toString() : null;
  } catch {
    return null;
  }
}

/** Point + radius pins (Meta / Google). */
function PinEditor({ value, onChange }: { value: ZTargeting["custom_locations"]; onChange: (v: ZTargeting["custom_locations"]) => void }) {
  const [lat, setLat] = useState("");
  const [lng, setLng] = useState("");
  const [radius, setRadius] = useState("5");
  const ok = lat !== "" && lng !== "" && Math.abs(Number(lat)) <= 90 && Math.abs(Number(lng)) <= 180 && Number(radius) > 0;
  return (
    <details className="mb-3">
      <summary className="cursor-pointer text-[13px]">Pin + radius (e.g. around your shop)</summary>
      <div className="mt-2 flex flex-wrap items-end gap-2 text-[13px]">
        <input className="w-28" placeholder="Latitude" value={lat} onChange={(e) => setLat(e.target.value)} />
        <input className="w-28" placeholder="Longitude" value={lng} onChange={(e) => setLng(e.target.value)} />
        <input className="w-20" placeholder="km" value={radius} onChange={(e) => setRadius(e.target.value)} />
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={!ok}
          onClick={() => {
            onChange([...value, { latitude: Number(lat), longitude: Number(lng), radius: Number(radius), distance_unit: "kilometer" }]);
            setLat("");
            setLng("");
          }}
        >
          Add pin
        </button>
      </div>
      <Chips items={value} label={(p) => `${formatNumber(p.latitude)}, ${formatNumber(p.longitude)} +${formatNumber(p.radius)} km`} onRemove={(i) => onChange(value.filter((_, j) => j !== i))} />
    </details>
  );
}
