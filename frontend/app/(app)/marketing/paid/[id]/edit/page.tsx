"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import AdForm from "@/components/campaigns/builder/ad-form";
import AdSetForm from "@/components/campaigns/builder/adset-form";
import CampaignForm from "@/components/campaigns/builder/campaign-form";
import PreviewPanel from "@/components/campaigns/builder/preview-panel";
import BuilderTreeView, { BuilderProvider, errorText, useBuilder } from "@/components/campaigns/builder/tree";
import PlatformAdForm from "@/components/campaigns/platform-builder/ad-form";
import PlatformCampaignForm from "@/components/campaigns/platform-builder/campaign-form";
import PlatformGroupForm from "@/components/campaigns/platform-builder/group-form";
import { MetaReview, PlatformReview, Stepper, type Step } from "@/components/campaigns/review-step";
import PlatformTreeView, { FORMAT_LABEL, PlatformBuilderProvider, useBuilder as usePlatformBuilder } from "@/components/campaigns/platform-builder/tree";
import { adsKeys, fetchPlatforms, fetchPlatformTree, publishPlatformCampaign, setPlatformStatus, validatePlatformCampaign } from "@/lib/api/ads";
import { ApiError } from "@/lib/types/common";
import type { Issue as PlatformIssue } from "@/lib/types/ads";
import { BarChart, Tile, money } from "@/components/analytics/ads-report";
import {
  fetchCampaignResults,
  fetchObjectives,
  fetchTree,
  metaKeys,
  publishCampaign,
  setStatus,
  syncCampaignResults,
  validateCampaign,
} from "@/lib/api/meta";
import type { Issue } from "@/lib/types/meta";

const STATUS_CLASS: Record<string, string> = {
  running: "badge badge-success",
  scheduled: "badge badge-neutral",
  paused: "badge badge-warn",
  draft: "badge badge-neutral",
  completed: "badge badge-neutral",
  failed: "badge badge-danger",
};

function effectiveLabel(status: string, effective: string | null): string {
  if (!effective) return status;
  const map: Record<string, string> = {
    ACTIVE: "Active",
    PAUSED: "Paused",
    PENDING_REVIEW: "In review",
    IN_PROCESS: "In review",
    DISAPPROVED: "Disapproved",
    WITH_ISSUES: "With issues",
    CAMPAIGN_PAUSED: "Campaign paused",
    ADSET_PAUSED: "Ad set paused",
  };
  return map[effective] ?? effective.replace(/_/g, " ").toLowerCase();
}

// Pause / resume for the selected node (Meta first, then ours).
function NodeStatus() {
  const { tree, selected } = useBuilder();
  const queryClient = useQueryClient();
  const node =
    selected.level === "campaign"
      ? { status: tree.campaign.status, effective: tree.meta?.effective_status ?? null, published: Boolean(tree.meta?.published) }
      : selected.level === "ad_set"
        ? (() => {
            const s = tree.ad_sets.find((x) => x.id === selected.id);
            return { status: s?.status ?? "", effective: s?.effective_status ?? null, published: Boolean(s?.external_id) };
          })()
        : (() => {
            const a = tree.ad_sets.flatMap((s) => s.ads).find((x) => x.id === selected.id);
            return { status: a?.status ?? "", effective: a?.effective_status ?? null, published: Boolean(a?.external_ad_id) };
          })();
  const toggle = useMutation({
    mutationFn: (resume: boolean) => setStatus(selected.level, selected.id, resume),
    onSettled: () => void queryClient.invalidateQueries({ queryKey: metaKeys.tree(tree.campaign.id) }),
  });
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 text-[13px]">
      <span className={STATUS_CLASS[node.status] ?? "badge badge-neutral"}>{effectiveLabel(node.status, node.effective)}</span>
      {node.published && ["running", "scheduled"].includes(node.status) && (
        <button type="button" className="btn btn-secondary btn-sm" disabled={toggle.isPending} onClick={() => toggle.mutate(false)}>
          Pause
        </button>
      )}
      {node.published && node.status === "paused" && (
        <button type="button" className="btn btn-secondary btn-sm" disabled={toggle.isPending} onClick={() => toggle.mutate(true)}>
          Resume
        </button>
      )}
      {tree.meta?.ads_manager_url && (
        <a className="text-accent underline" href={tree.meta.ads_manager_url} target="_blank" rel="noreferrer">
          Open in Ads Manager ↗
        </a>
      )}
      {toggle.isError && <span className="text-xs text-danger">{errorText(toggle.error)}</span>}
    </div>
  );
}

function Editor() {
  const { tree, selected } = useBuilder();
  if (selected.level === "campaign") return <CampaignForm />;
  const adSet = selected.level === "ad_set" ? tree.ad_sets.find((s) => s.id === selected.id) : tree.ad_sets.find((s) => s.ads.some((a) => a.id === selected.id));
  if (!adSet) return null;
  if (selected.level === "ad_set") return <AdSetForm key={adSet.id} adSet={adSet} />;
  const ad = adSet.ads.find((a) => a.id === selected.id);
  return ad ? <AdForm key={ad.id} ad={ad} adSet={adSet} /> : null;
}

const STEP_LABELS = { campaign: "Campaign", group: "Ad set", ad: "Ad", review: "Review" } as const;

// Campaign → Ad set → Ad → Review (SPEC-FE-049). The first three steps select
// that level in the tree (the first ad set / ad); Review swaps the editor for
// the read-only summary. Picking a tree node leaves Review.
// Both builders: reopen where the user left off (selected node and the Review
// step), per campaign, in this browser. A saved node is used only while it
// still exists; a deleted one falls back to the campaign. Also returns the ref
// for the middle column, which scrolls on its own and starts at the top
// whenever another node is picked.
function useBuilderPlace<S extends { level: string; id: string }>(
  storageKey: string,
  selected: S,
  select: (s: S) => void,
  exists: (s: S) => boolean,
) {
  const [reviewing, setReviewing] = useState(false);
  const [restored, setRestored] = useState(false);
  const middle = useRef<HTMLDivElement>(null);
  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) ?? "null") as (S & { reviewing?: boolean }) | null;
      const node = saved?.level && saved.id ? ({ level: saved.level, id: saved.id } as S) : null;
      if (node && exists(node)) select(node);
      if (saved?.reviewing) setReviewing(true);
    } catch {
      // storage unavailable: start on the campaign
    }
    setRestored(true);
  }, [storageKey]); // restore once per campaign
  useEffect(() => {
    if (!restored) return;
    try {
      localStorage.setItem(storageKey, JSON.stringify({ level: selected.level, id: selected.id, reviewing }));
    } catch {
      // storage unavailable: nothing to remember
    }
  }, [restored, storageKey, selected.level, selected.id, reviewing]);
  useEffect(() => {
    middle.current?.scrollTo({ top: 0 });
  }, [selected.id, reviewing]);
  return { reviewing, setReviewing, middle };
}

// On wide screens the three columns get a fixed height and scroll on their
// own: the tree and the right panel stay put while only the middle moves.
const GRID_FIXED = "lg:h-[calc(100vh-320px)] lg:min-h-[420px]";
const COLUMN = "lg:min-h-0 lg:overflow-y-auto";

function MetaSteps() {
  const { tree, selected, select } = useBuilder();
  const { reviewing, setReviewing, middle } = useBuilderPlace(`meta-builder:${tree.campaign.id}`, selected, select, (s) =>
    s.level === "campaign" ? s.id === tree.campaign.id : s.level === "ad_set" ? tree.ad_sets.some((x) => x.id === s.id) : tree.ad_sets.some((x) => x.ads.some((a) => a.id === s.id)),
  );
  const firstSet = tree.ad_sets[0];
  const firstAd = tree.ad_sets.flatMap((s) => s.ads)[0];
  const current: Step = reviewing ? "review" : selected.level === "ad_set" ? "group" : selected.level;
  const onStep = (s: Step) => {
    if (s === "review") {
      if (firstAd && selected.level !== "ad") select({ level: "ad", id: firstAd.id });
      setReviewing(true);
      return;
    }
    setReviewing(false);
    if (s === "campaign") select({ level: "campaign", id: tree.campaign.id });
    else if (s === "group" && firstSet) select({ level: "ad_set", id: firstSet.id });
    else if (s === "ad" && firstAd) select({ level: "ad", id: firstAd.id });
  };
  const objective = tree.campaign.objective.replace(/_/g, " ");
  return (
    <>
      <Stepper labels={STEP_LABELS} current={current} onStep={onStep} disabled={{ group: !firstSet, ad: !firstAd }} />
      <div className={`grid gap-4 ${GRID_FIXED} lg:grid-cols-[260px_1fr_320px]`}>
        <div className={COLUMN} onClickCapture={() => setReviewing(false)}>
          <BuilderTreeView />
        </div>
        <div ref={middle} className={`${COLUMN} lg:pr-1`}>
          {reviewing ? (
            <MetaReview tree={tree} objectiveLabel={objective.charAt(0).toUpperCase() + objective.slice(1)} />
          ) : (
            <>
              <NodeStatus />
              <Editor />
            </>
          )}
        </div>
        <div className={COLUMN}>
          <PreviewPanel />
        </div>
      </div>
    </>
  );
}

// Sticky footer: Save draft (autosaved) · Validate · Preview · Publish ▾.
function Footer() {
  const { tree, run, busy, error, select } = useBuilder();
  const [menu, setMenu] = useState(false);
  const [issues, setIssues] = useState<Issue[] | null>(null);
  const validate = useMutation({ mutationFn: () => validateCampaign(tree.campaign.id), onSuccess: (r) => setIssues(r.errors) });
  const draft = tree.campaign.status === "draft";
  const future = tree.ad_sets.some((s) => s.starts_at && new Date(s.starts_at) > new Date());
  const publish = (mode: "active" | "paused") => {
    setMenu(false);
    void run(() => publishCampaign(tree.campaign.id, mode));
  };
  const shown = issues ?? (tree.missing.length ? tree.missing : null);
  return (
    <div className="card sticky bottom-0 z-10 mt-4" style={{ padding: 12 }}>
      {shown && shown.length > 0 && (
        <ul className="m-0 mb-2 max-h-32 overflow-y-auto pl-4 text-xs text-danger">
          {shown.map((i, k) => (
            <li key={k}>
              <button type="button" className="text-left underline" onClick={() => i.id && select({ level: i.level, id: i.id })}>
                {i.level.replace("_", " ")}
                {i.source === "meta" ? " (Meta)" : ""}: {i.message}
              </button>
            </li>
          ))}
        </ul>
      )}
      {issues && issues.length === 0 && <p className="m-0 mb-2 text-xs text-success">Validation passed (local checks and Meta).</p>}
      {tree.meta?.last_error && <p className="m-0 mb-2 text-xs text-danger">Last publish error: {tree.meta.last_error}</p>}
      {tree.campaign.pending_approval_id && <p className="m-0 mb-2 text-xs text-warn">Waiting for owner approval — see Command Chat › Pending Approvals.</p>}
      {error && (
        <p className="m-0 mb-2 text-xs text-danger" role="alert">
          {error}
        </p>
      )}
      <div className="flex flex-wrap items-center justify-end gap-2">
        <span className="mr-auto text-xs text-muted">{busy ? "Saving…" : "All changes saved to the draft"}</span>
        <button type="button" className="btn btn-secondary btn-sm" disabled={validate.isPending || !draft} onClick={() => validate.mutate()}>
          {validate.isPending ? "Validating…" : "Validate"}
        </button>
        {draft && !tree.campaign.pending_approval_id && (
          <div className="relative">
            <button type="button" className="btn btn-sm" disabled={busy} aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu((m) => !m)}>
              Publish ▾
            </button>
            {menu && (
              <div role="menu" className="absolute bottom-full right-0 mb-1 w-64 rounded-md border border-border bg-panel p-1 shadow">
                <button role="menuitem" type="button" className="block w-full rounded px-2 py-1.5 text-left text-[13px] hover:bg-bg" onClick={() => publish("active")}>
                  {future ? "Schedule (starts at the ad set start)" : "Publish now"}
                </button>
                <button role="menuitem" type="button" className="block w-full rounded px-2 py-1.5 text-left text-[13px] hover:bg-bg" onClick={() => publish("paused")}>
                  Publish paused (created on Meta, not spending)
                </button>
              </div>
            )}
          </div>
        )}
      </div>
      {validate.isError && <p className="m-0 mt-1 text-xs text-danger">{errorText(validate.error)}</p>}
    </div>
  );
}

// Results (SPEC-FE-042): imported Meta results only; "—" when Meta reported none.
function Results({ campaignId, currency }: { campaignId: string; currency: string }) {
  const queryClient = useQueryClient();
  const [range, setRange] = useState("7d");
  const results = useQuery({ queryKey: metaKeys.results(campaignId, range), queryFn: () => fetchCampaignResults(campaignId, range) });
  const sync = useMutation({
    mutationFn: () => syncCampaignResults(campaignId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["meta", "results", campaignId] });
      void queryClient.invalidateQueries({ queryKey: metaKeys.tree(campaignId) });
    },
  });
  const r = results.data;
  const fmt = (v: number | null, f: (n: number) => string = String) => (v === null ? "—" : f(v));
  return (
    <div className="card mt-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="m-0">Results</h3>
        <div className="flex items-center gap-2">
          <select aria-label="Range" value={range} onChange={(e) => setRange(e.target.value)}>
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
            <option value="90d">Last 90 days</option>
            <option value="lifetime">Lifetime</option>
          </select>
          <button type="button" className="btn btn-secondary btn-sm" disabled={sync.isPending} onClick={() => sync.mutate()}>
            {sync.isPending ? "Syncing…" : "Sync now"}
          </button>
        </div>
      </div>
      {sync.isError && <p className="text-xs text-danger">{errorText(sync.error)}</p>}
      {results.isError && <p className="text-xs text-danger">{results.error.message}</p>}
      {r && (
        <>
          <p className="m-0 mb-3 text-xs text-muted">
            Source: Meta · last synced {r.last_sync_at ? new Date(r.last_sync_at).toLocaleString() : "never"} · {r.summary}
          </p>
          <div className="mb-4 grid gap-3 sm:grid-cols-4 lg:grid-cols-7">
            <Tile title="Spend" value={fmt(r.totals.spend, (n) => money(n, currency))} />
            <Tile title="Impressions" value={fmt(r.totals.impressions, (n) => n.toLocaleString())} />
            <Tile title="Reach" value={fmt(r.totals.reach, (n) => n.toLocaleString())} />
            <Tile title="Link clicks" value={fmt(r.totals.clicks, (n) => n.toLocaleString())} />
            <Tile title="CTR" value={fmt(r.totals.ctr, (n) => `${n}%`)} />
            <Tile title={`Results (${r.result_metric.replace(/_/g, " ")})`} value={fmt(r.totals.results, (n) => n.toLocaleString())} />
            <Tile title="ROAS" value={fmt(r.totals.roas, (n) => n.toFixed(2))} />
          </div>
          {r.daily.length > 0 && (
            <BarChart
              days={r.daily.map((d) => ({ ...d, spend: d.spend ?? 0, results: d.results ?? 0 }))}
              series={[
                { key: "spend", label: "Spend", barClass: "bar", dotClass: "" },
                { key: "results", label: "Results", barClass: "bar bg-chart-2", dotClass: "" },
              ]}
            />
          )}
          {r.ads.length > 0 && (
            <table className="mt-3">
              <thead>
                <tr>
                  <th>Ad</th>
                  <th>Status</th>
                  <th>Spend</th>
                  <th>Impr.</th>
                  <th>CTR</th>
                  <th>Results</th>
                </tr>
              </thead>
              <tbody>
                {r.ads.map((a) => (
                  <tr key={a.id}>
                    <td>{a.name}</td>
                    <td>{effectiveLabel(a.status, a.effective_status)}</td>
                    <td>{fmt(a.spend, (n) => money(n, currency))}</td>
                    <td>{fmt(a.impressions, (n) => n.toLocaleString())}</td>
                    <td>{fmt(a.ctr, (n) => `${n}%`)}</td>
                    <td>{fmt(a.results)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}

// Ads Manager-style builder (SPEC-FE-039): tree | editor | preview, with a
// sticky publish footer, and results once published (SPEC-FE-042).
function MetaCampaignBuilder() {
  const { id } = useParams<{ id: string }>();
  const tree = useQuery({ queryKey: metaKeys.tree(id), queryFn: () => fetchTree(id) });
  const objectives = useQuery({ queryKey: metaKeys.objectives, queryFn: fetchObjectives, staleTime: 5 * 60_000 });
  if (tree.isPending) return <p className="text-[13px] text-muted">Loading campaign…</p>;
  if (tree.isError) {
    return (
      <p className="text-[13px] text-danger" role="alert">
        Couldn&apos;t load this campaign: {tree.error.message}{" "}
        <Link href="/marketing/paid" className="underline">
          Back to campaigns
        </Link>
      </p>
    );
  }
  const t = tree.data;
  return (
    <BuilderProvider tree={t} objectives={objectives.data}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <Link href="/marketing/paid" className="text-xs text-muted underline">
            ← Campaigns
          </Link>
          <h1 className="m-0 text-[22px] font-bold">{t.campaign.name}</h1>
          <p className="m-0 text-xs text-muted">
            {t.campaign.status === "draft" ? "Draft (saved here; Meta has no drafts)" : `On Meta · ${t.campaign.status}`}
            {t.approval?.required && t.campaign.status === "draft" && ` · Publishing needs owner approval: ${t.approval.reason}`}
          </p>
        </div>
        {!objectives.data?.connection.connected && (
          <Link href="/integrations" className="badge badge-warn">
            Connect Meta to publish
          </Link>
        )}
      </div>
      <MetaSteps />
      <Footer />
      {t.meta?.published && <Results campaignId={t.campaign.id} currency={t.campaign.currency} />}
    </BuilderProvider>
  );
}

// ---------------------------------------------------------------------------
// Multi-platform builder (SPEC-FE-045): TikTok, Google Ads, YouTube, LinkedIn,
// X, Snapchat, Pinterest. Same layout as the Meta builder above.
// ---------------------------------------------------------------------------
function PlatformNodeStatus() {
  const { tree, selected, platform } = usePlatformBuilder();
  const queryClient = useQueryClient();
  const node =
    selected.level === "campaign"
      ? { status: tree.campaign.status, published: Boolean(tree.campaign.external_id) }
      : selected.level === "group"
        ? (() => {
            const g = tree.groups.find((x) => x.id === selected.id);
            return { status: g?.status ?? "", published: Boolean(g?.external_id) };
          })()
        : (() => {
            const a = tree.groups.flatMap((g) => g.ads).find((x) => x.id === selected.id);
            return { status: a?.status ?? "", published: Boolean(a?.external_id) };
          })();
  const toggle = useMutation({
    mutationFn: (resume: boolean) => setPlatformStatus(selected.level, selected.id, resume),
    onSettled: () => void queryClient.invalidateQueries({ queryKey: adsKeys.tree(tree.campaign.id) }),
  });
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 text-[13px]">
      <span className={STATUS_CLASS[node.status] ?? "badge badge-neutral"}>{node.status}</span>
      {node.published && <span className="text-xs text-muted">On {platform.label}</span>}
      {node.published && ["running", "scheduled"].includes(node.status) && (
        <button type="button" className="btn btn-secondary btn-sm" disabled={toggle.isPending} onClick={() => toggle.mutate(false)}>
          Pause
        </button>
      )}
      {node.published && node.status === "paused" && (
        <button type="button" className="btn btn-secondary btn-sm" disabled={toggle.isPending} onClick={() => toggle.mutate(true)}>
          Resume
        </button>
      )}
      {toggle.isError && <span className="text-xs text-danger">{errorText(toggle.error)}</span>}
    </div>
  );
}

function PlatformEditor() {
  const { tree, selected } = usePlatformBuilder();
  if (selected.level === "campaign") return <PlatformCampaignForm />;
  const group = selected.level === "group" ? tree.groups.find((g) => g.id === selected.id) : tree.groups.find((g) => g.ads.some((a) => a.id === selected.id));
  if (!group) return null;
  if (selected.level === "group") return <PlatformGroupForm key={group.id} group={group} />;
  const ad = group.ads.find((a) => a.id === selected.id);
  return ad ? <PlatformAdForm key={ad.id} ad={ad} /> : null;
}

// Right column: what still blocks publishing, and a summary of the selected ad.
function PlatformChecklist() {
  const { tree, selected, select, platform } = usePlatformBuilder();
  const ad = selected.level === "ad" ? tree.groups.flatMap((g) => g.ads).find((a) => a.id === selected.id) : undefined;
  const texts = ad
    ? Object.entries(ad.creative).filter(([k, v]) => k !== "format" && k !== "media" && (typeof v === "string" ? v.trim() : Array.isArray(v) && v.some((x) => typeof x === "string" && x.trim())))
    : [];
  return (
    <aside className="card" style={{ padding: 12 }}>
      <h3 className="mt-0 text-[14px]">Checklist</h3>
      {tree.issues.length === 0 ? (
        <p className="m-0 text-xs text-success">Nothing missing. Validate to run {platform.label}&apos;s own checks too.</p>
      ) : (
        <ul className="m-0 pl-4 text-xs">
          {tree.issues.map((i, k) => (
            <li key={k} className={i.severity === "error" ? "text-danger" : "text-warn"}>
              <button type="button" className="text-left underline" onClick={() => i.id && select({ level: i.level, id: i.id })}>
                {i.message}
              </button>
            </li>
          ))}
        </ul>
      )}
      {ad && (
        <>
          <h3 className="mb-1 mt-4 text-[14px]">Ad summary</h3>
          <p className="m-0 text-xs text-muted">
            {platform.label} · {FORMAT_LABEL[String(ad.creative.format)] ?? String(ad.creative.format ?? "no format")}
          </p>
          <dl className="m-0 mt-2 text-xs">
            {texts.map(([k, v]) => (
              <div key={k} className="mb-1">
                <dt className="font-semibold">{k.replace(/_/g, " ")}</dt>
                <dd className="m-0 break-words">{Array.isArray(v) ? (v as string[]).filter(Boolean).join(" | ") : String(v)}</dd>
              </div>
            ))}
          </dl>
          <p className="m-0 mt-2 text-xs text-muted">{platform.label} shows its own preview after publishing.</p>
        </>
      )}
    </aside>
  );
}

// Same stepper for the other platforms, labelled with the platform's own
// hierarchy names (e.g. TikTok "Ad group", LinkedIn "Campaign group").
function PlatformSteps() {
  const { tree, selected, select, platform } = usePlatformBuilder();
  const { reviewing, setReviewing, middle } = useBuilderPlace(`platform-builder:${tree.campaign.id}`, selected, select, (s) =>
    s.level === "campaign" ? s.id === tree.campaign.id : s.level === "group" ? tree.groups.some((g) => g.id === s.id) : tree.groups.some((g) => g.ads.some((a) => a.id === s.id)),
  );
  const firstGroup = tree.groups[0];
  const firstAd = tree.groups.flatMap((g) => g.ads)[0];
  const current: Step = reviewing ? "review" : selected.level;
  const onStep = (s: Step) => {
    if (s === "review") {
      setReviewing(true);
      return;
    }
    setReviewing(false);
    if (s === "campaign") select({ level: "campaign", id: tree.campaign.id });
    else if (s === "group" && firstGroup) select({ level: "group", id: firstGroup.id });
    else if (s === "ad" && firstAd) select({ level: "ad", id: firstAd.id });
  };
  const labels = { campaign: platform.hierarchy.campaign, group: platform.hierarchy.group, ad: platform.hierarchy.ad, review: "Review" };
  return (
    <>
      <Stepper labels={labels} current={current} onStep={onStep} disabled={{ group: !firstGroup, ad: !firstAd }} />
      <div className={`grid gap-4 ${GRID_FIXED} lg:grid-cols-[260px_1fr_300px]`}>
        <div className={COLUMN} onClickCapture={() => setReviewing(false)}>
          <PlatformTreeView />
        </div>
        <div ref={middle} className={`${COLUMN} lg:pr-1`}>
          {reviewing ? (
            <PlatformReview tree={tree} platform={platform} />
          ) : (
            <>
              <PlatformNodeStatus />
              <PlatformEditor />
            </>
          )}
        </div>
        <div className={COLUMN}>
          <PlatformChecklist />
        </div>
      </div>
    </>
  );
}

function PlatformFooter() {
  const { tree, run, busy, error, select, platform } = usePlatformBuilder();
  const [menu, setMenu] = useState(false);
  const [issues, setIssues] = useState<PlatformIssue[] | null>(null);
  const validate = useMutation({ mutationFn: () => validatePlatformCampaign(tree.campaign.id), onSuccess: (r) => setIssues(r.issues) });
  const draft = tree.campaign.status === "draft";
  const notBuilt = tree.connection.publishing === "not_built";
  const canPublish = draft && !tree.campaign.pending_approval_id && tree.connection.connected && !notBuilt;
  const publish = (mode: "active" | "paused") => {
    setMenu(false);
    void run(() => publishPlatformCampaign(tree.campaign.id, mode));
  };
  return (
    <div className="card sticky bottom-0 z-10 mt-4" style={{ padding: 12 }}>
      {issues && issues.length > 0 && (
        <ul className="m-0 mb-2 max-h-32 overflow-y-auto pl-4 text-xs text-danger">
          {issues.map((i, k) => (
            <li key={k}>
              <button type="button" className="text-left underline" onClick={() => i.id && select({ level: i.level, id: i.id })}>
                {i.path}: {i.message}
              </button>
            </li>
          ))}
        </ul>
      )}
      {issues && issues.length === 0 && <p className="m-0 mb-2 text-xs text-success">Validation passed.</p>}
      {tree.campaign.last_error && <p className="m-0 mb-2 text-xs text-danger">Last publish error: {tree.campaign.last_error}</p>}
      {tree.campaign.pending_approval_id && <p className="m-0 mb-2 text-xs text-warn">Sent to the owner for approval — see Command Chat › Pending Approvals.</p>}
      {draft && notBuilt && <p className="m-0 mb-2 text-xs text-warn">{tree.connection.message} Your draft is saved.</p>}
      {draft && !notBuilt && !tree.connection.connected && (
        <p className="m-0 mb-2 text-xs text-warn">
          Connect {platform.label} in{" "}
          <Link href="/integrations" className="underline">
            Integrations
          </Link>{" "}
          to publish.
        </p>
      )}
      {error && (
        <p className="m-0 mb-2 text-xs text-danger" role="alert">
          {error}
        </p>
      )}
      <div className="flex flex-wrap items-center justify-end gap-2">
        <span className="mr-auto text-xs text-muted">{busy ? "Saving…" : "All changes saved to the draft"}</span>
        <button type="button" className="btn btn-secondary btn-sm" disabled={validate.isPending || !draft} onClick={() => validate.mutate()}>
          {validate.isPending ? "Validating…" : "Validate"}
        </button>
        {draft && !tree.campaign.pending_approval_id && (
          <div className="relative">
            <button type="button" className="btn btn-sm" disabled={busy || !canPublish} aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu((m) => !m)}>
              Publish ▾
            </button>
            {menu && (
              <div role="menu" className="absolute bottom-full right-0 mb-1 w-64 rounded-md border border-border bg-panel p-1 shadow">
                <button role="menuitem" type="button" className="block w-full rounded px-2 py-1.5 text-left text-[13px] hover:bg-bg" onClick={() => publish("active")}>
                  Publish now
                </button>
                <button role="menuitem" type="button" className="block w-full rounded px-2 py-1.5 text-left text-[13px] hover:bg-bg" onClick={() => publish("paused")}>
                  Publish paused (created on {platform.label}, not spending)
                </button>
              </div>
            )}
          </div>
        )}
      </div>
      {validate.isError && <p className="m-0 mt-1 text-xs text-danger">{errorText(validate.error)}</p>}
    </div>
  );
}

function PlatformCampaignBuilder({ id }: { id: string }) {
  const tree = useQuery({ queryKey: adsKeys.tree(id), queryFn: () => fetchPlatformTree(id) });
  const platforms = useQuery({ queryKey: adsKeys.platforms, queryFn: fetchPlatforms, staleTime: 60_000 });
  if (tree.isPending || platforms.isPending) return <p className="text-[13px] text-muted">Loading campaign…</p>;
  if (tree.isError || platforms.isError) {
    return (
      <p className="text-[13px] text-danger" role="alert">
        Couldn&apos;t load this campaign: {(tree.error ?? platforms.error)?.message}{" "}
        <Link href="/marketing/paid" className="underline">
          Back to campaigns
        </Link>
      </p>
    );
  }
  const t = tree.data;
  const platform = platforms.data.platforms.find((p) => p.key === t.platform);
  if (!platform) return <p className="text-[13px] text-danger">Unknown platform {t.platform}.</p>;
  return (
    <PlatformBuilderProvider tree={t} platform={platform}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <Link href="/marketing/paid" className="text-xs text-muted underline">
            ← Campaigns
          </Link>
          <h1 className="m-0 text-[22px] font-bold">{t.campaign.name}</h1>
          <p className="m-0 text-xs text-muted">
            {platform.label} · {t.campaign.objective_label}
            {t.campaign.campaign_type ? ` · ${platform.campaign_types.find((c) => c.key === t.campaign.campaign_type)?.label ?? t.campaign.campaign_type}` : ""}
            {" · "}
            {t.campaign.status === "draft" ? "Draft (saved here)" : `On ${platform.label} · ${t.campaign.status}`}
            {t.approval?.required && t.campaign.status === "draft" && ` · Publishing needs owner approval: ${t.approval.reason}`}
          </p>
        </div>
        {!t.connection.connected && (
          <Link href="/integrations" className="badge badge-warn">
            Connect {platform.label} to publish
          </Link>
        )}
      </div>
      <PlatformSteps />
      <PlatformFooter />
    </PlatformBuilderProvider>
  );
}

// /marketing/paid/<id>/edit: the multi-platform builder answers 404 for a Meta
// campaign, which then opens the Meta builder (SPEC-FE-045).
export default function CampaignBuilderPage() {
  const { id } = useParams<{ id: string }>();
  const probe = useQuery({ queryKey: adsKeys.tree(id), queryFn: () => fetchPlatformTree(id), retry: false });
  if (probe.isPending) return <p className="text-[13px] text-muted">Loading campaign…</p>;
  if (probe.isError) {
    if (probe.error instanceof ApiError && probe.error.status === 404) return <MetaCampaignBuilder />;
    return (
      <p className="text-[13px] text-danger" role="alert">
        Couldn&apos;t load this campaign: {probe.error.message}{" "}
        <Link href="/marketing/paid" className="underline">
          Back to campaigns
        </Link>
      </p>
    );
  }
  return <PlatformCampaignBuilder id={id} />;
}
