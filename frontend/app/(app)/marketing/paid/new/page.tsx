"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Suspense, useState, type FormEvent } from "react";

import { useCreatedItemTab } from "@/hooks/use-new-tab";
import { errorText } from "@/components/campaigns/builder/tree";
import { adsKeys, createPlatformCampaign, fetchPlatforms } from "@/lib/api/ads";
import { createBuilderCampaign, fetchObjectives, metaKeys } from "@/lib/api/meta";
import type { BuilderPlatform, PlatformObjective } from "@/lib/types/ads";
import type { BuilderObjective } from "@/lib/types/meta";

const ICON: Record<string, string> = {
  awareness: "📢",
  traffic: "🖱️",
  engagement: "💬",
  leads: "🧲",
  app_promotion: "📱",
  sales: "🛍️",
};

const BACK = (
  <Link href="/marketing/paid/ad-manager" className="mb-3 inline-block text-[13px] text-accent underline">
    ← Choose another platform
  </Link>
);

// New campaign (SPEC-FE-039): Ads Manager's first step - choose the objective
// (six outcome objectives, unavailable ones disabled with Meta's reason) and a
// name. Creates a draft with one ad set and one ad, then opens the builder.
function MetaNewCampaign() {
  const router = useRouter();
  const objectives = useQuery({ queryKey: metaKeys.objectives, queryFn: fetchObjectives });
  const [objective, setObjective] = useState<BuilderObjective | null>(null);
  const [name, setName] = useState("");
  const newTab = useCreatedItemTab();
  const create = useMutation({
    mutationFn: () => createBuilderCampaign(name.trim(), objective as BuilderObjective),
    onSuccess: (tree) => newTab.open(`/marketing/paid/${tree.campaign.id}/edit`), // SPEC-FE-058
    onError: () => newTab.cancel(),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (objective && name.trim()) {
      newTab.begin();
      create.mutate();
    }
  };
  return (
    <form onSubmit={submit} className="mx-auto max-w-[760px]">
      {BACK}
      <h1 className="m-0 mb-1 text-[22px] font-bold">Create new campaign</h1>
      <p className="m-0 mb-5 text-muted">Choose a campaign objective.</p>
      {objectives.isError && <p className="text-[13px] text-danger">{objectives.error.message}</p>}
      <div className="grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="Campaign objective">
        {(objectives.data?.objectives ?? []).map((o) => (
          <button
            key={o.key}
            type="button"
            role="radio"
            aria-checked={objective === o.key}
            disabled={!o.available}
            title={o.reason ?? undefined}
            className={`card text-left ${objective === o.key ? "ring-2 ring-accent" : ""} ${o.available ? "" : "opacity-50"}`}
            onClick={() => setObjective(o.key)}
          >
            <div className="text-[15px] font-semibold">
              {ICON[o.key]} {o.label}
            </div>
            <div className="mt-1 text-xs text-muted">{o.description}</div>
            {o.reason && <div className="mt-1 text-xs text-warn">{o.reason}</div>}
          </button>
        ))}
      </div>
      <div className="form-row mt-4">
        <label htmlFor="new_name">Campaign name</label>
        <input id="new_name" required maxLength={255} placeholder="e.g. Eid sale — Sales" value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      {create.isError && <p className="text-xs text-danger">{errorText(create.error)}</p>}
      <div className="flex gap-2">
        <button type="submit" className="btn" disabled={!objective || !name.trim() || create.isPending}>
          {create.isPending ? "Creating…" : "Continue"}
        </button>
        <button type="button" className="btn btn-secondary" onClick={() => router.push("/marketing/paid")}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function ObjectiveGrid({ label, options, value, onPick }: { label: string; options: PlatformObjective[]; value: string | null; onPick: (key: string) => void }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.key}
          type="button"
          role="radio"
          aria-checked={value === o.key}
          disabled={!o.available}
          title={o.reason ?? undefined}
          className={`card text-left ${value === o.key ? "ring-2 ring-accent" : ""} ${o.available ? "" : "opacity-50"}`}
          onClick={() => onPick(o.key)}
        >
          <div className="text-[15px] font-semibold">{o.label}</div>
          <div className="mt-1 text-xs text-muted">{o.description}</div>
          {o.reason && <div className="mt-1 text-xs text-warn">{o.reason}</div>}
        </button>
      ))}
    </div>
  );
}

// Any other platform (SPEC-FE-044): the same layout with that platform's own
// objectives (and Google's campaign type), creating a draft through the
// multi-platform builder (SPEC-BE-062).
function PlatformNewCampaign({ platform }: { platform: string }) {
  const router = useRouter();
  const platforms = useQuery({ queryKey: adsKeys.platforms, queryFn: fetchPlatforms });
  const [objective, setObjective] = useState<string | null>(null);
  const [campaignType, setCampaignType] = useState<string | null>(null);
  const [name, setName] = useState("");
  const p = platforms.data?.platforms.find((x) => x.key === platform);
  const needsType = (p?.campaign_types.length ?? 0) > 0;
  const newTab = useCreatedItemTab();
  const create = useMutation({
    mutationFn: () =>
      createPlatformCampaign(platform as BuilderPlatform, { name: name.trim(), objective: objective as string, campaign_type: needsType ? campaignType : null }),
    onSuccess: (tree) => newTab.open(`/marketing/paid/${tree.campaign.id}/edit`), // SPEC-FE-058
    onError: () => newTab.cancel(),
  });
  if (platforms.isPending) return <p className="text-[13px] text-muted">Loading…</p>;
  if (platforms.isError) return <p className="text-[13px] text-danger">{platforms.error.message}</p>;
  if (!p) {
    return (
      <div className="mx-auto max-w-[760px]">
        <h1 className="m-0 mb-2 text-[22px] font-bold">Unknown platform</h1>
        <Link href="/marketing/paid/ad-manager" className="text-accent underline">
          Back to the Ad Manager
        </Link>
      </div>
    );
  }
  const ready = Boolean(objective && name.trim() && (!needsType || campaignType));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (ready) {
      newTab.begin();
      create.mutate();
    }
  };
  return (
    <form onSubmit={submit} className="mx-auto max-w-[760px]">
      {BACK}
      <h1 className="m-0 mb-1 text-[22px] font-bold">Create new {p.label} campaign</h1>
      <p className="m-0 mb-5 text-muted">
        Runs on {p.runs_on}. {p.connected ? `Connected: ${p.account_name ?? p.label}.` : p.connect_hint}
      </p>
      <h2 className="m-0 mb-2 text-[15px] font-semibold">Objective</h2>
      <ObjectiveGrid label="Campaign objective" options={p.objectives} value={objective} onPick={setObjective} />
      {needsType && (
        <>
          <h2 className="m-0 mb-2 mt-5 text-[15px] font-semibold">Campaign type</h2>
          <ObjectiveGrid label="Campaign type" options={p.campaign_types} value={campaignType} onPick={setCampaignType} />
        </>
      )}
      <div className="form-row mt-4">
        <label htmlFor="new_name">Campaign name</label>
        <input id="new_name" required maxLength={255} placeholder={`e.g. Eid sale — ${p.label}`} value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      {create.isError && <p className="text-xs text-danger">{errorText(create.error)}</p>}
      <div className="flex gap-2">
        <button type="submit" className="btn" disabled={!ready || create.isPending}>
          {create.isPending ? "Creating…" : "Continue"}
        </button>
        <button type="button" className="btn btn-secondary" onClick={() => router.push("/marketing/paid")}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function NewCampaignSwitch() {
  const platform = useSearchParams().get("platform");
  return !platform || platform === "meta" ? <MetaNewCampaign /> : <PlatformNewCampaign platform={platform} />;
}

// useSearchParams needs a Suspense boundary in the App Router.
export default function NewCampaignPage() {
  return (
    <Suspense fallback={<p className="text-[13px] text-muted">Loading…</p>}>
      <NewCampaignSwitch />
    </Suspense>
  );
}
