"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";

import { StepNav, errorText } from "@/components/campaigns/wizard";
import { updateDraft } from "@/lib/api/campaigns";
import { createManualCreative, editVariant, fetchCreative, generateCreatives, selectVariant } from "@/lib/api/content";
import { fetchProducts, productKeys } from "@/lib/api/products";
import type { CampaignDetail } from "@/lib/types/campaigns";
import { ApiError } from "@/lib/types/common";
import type { CreativeAsset, CreativeVariant } from "@/lib/types/content";

// The mockup's three placeholder gradients (Tailwind defaults with the mockup's
// exact values: amber-400 #fbbf24 -> red-500 #ef4444, emerald-500 #10b981 ->
// cyan-500 #06b6d4, indigo-500 #6366f1 -> pink-500 #ec4899). Variants are
// text-only (no image field), so a colored block stands in for imagery rather
// than any fabricated picture.
const GRADIENTS = ["from-amber-400 to-red-500", "from-emerald-500 to-cyan-500", "from-indigo-500 to-pink-500"];

const NO_LLM =
  "AI generation isn't set up (no AI model configured). Write your own variants instead, or add an AI model in Integrations › AI Models.";
const FORBIDDEN = "Only managers and above can create or edit creatives.";

type Mode = "write" | "ai";

function VariantCard({
  asset,
  variant,
  i,
  busy,
  onSelect,
  onEdited,
}: {
  asset: CreativeAsset;
  variant: CreativeVariant;
  i: number;
  busy: boolean;
  onSelect: () => void;
  onEdited: (a: CreativeAsset) => void;
}) {
  const selected = asset.selected_variant_index === variant.index;
  const [editing, setEditing] = useState(false);
  const [headline, setHeadline] = useState(variant.headline);
  const [description, setDescription] = useState(variant.description);
  const save = useMutation({
    mutationFn: () => editVariant(asset.id, variant.index, { headline: headline.trim(), description: description.trim() }),
    onSuccess: (a) => {
      onEdited(a);
      setEditing(false);
    },
  });
  return (
    <div className={`rounded-lg p-[14px] ${selected ? "border-2 border-accent" : "border border-border"}`}>
      <div
        className={`mb-2.5 flex h-[120px] items-center justify-center rounded-md bg-gradient-to-br font-semibold text-white ${GRADIENTS[i % GRADIENTS.length]}`}
      >
        Variant {variant.index + 1}
      </div>
      {editing ? (
        <>
          <input
            aria-label={`Variant ${variant.index + 1} headline`}
            className="mb-1.5 w-full rounded-md border border-border bg-panel px-2 py-1.5 text-[13px] text-text"
            maxLength={120}
            value={headline}
            onChange={(e) => setHeadline(e.target.value)}
          />
          <textarea
            aria-label={`Variant ${variant.index + 1} description`}
            className="w-full rounded-md border border-border bg-panel px-2 py-1.5 text-xs text-text"
            rows={2}
            maxLength={500}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <div className="mt-1.5 flex gap-1.5">
            <button type="button" className="btn btn-sm" disabled={save.isPending || !headline.trim()} onClick={() => save.mutate()}>
              {save.isPending ? "Saving…" : "Save"}
            </button>
            <button type="button" className="btn btn-secondary btn-sm" disabled={save.isPending} onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
          {save.isError && (
            <p className="mb-0 mt-1.5 text-xs text-danger" role="alert">
              {errorText(save.error, FORBIDDEN)}
            </p>
          )}
        </>
      ) : (
        <>
          <p className="m-0 mb-1 font-medium">&ldquo;{variant.headline}&rdquo;</p>
          <p className="m-0 text-xs text-muted">{variant.description}</p>
          <button
            type="button"
            className="btn btn-ghost btn-sm mt-1 px-0"
            onClick={() => {
              setHeadline(variant.headline);
              setDescription(variant.description);
              setEditing(true);
            }}
          >
            Edit
          </button>
        </>
      )}
      <button
        type="button"
        className={`btn btn-sm mt-2.5 w-full ${selected ? "" : "btn-secondary"}`}
        aria-pressed={selected}
        disabled={busy || selected}
        onClick={onSelect}
      >
        {selected ? "✓ Selected" : "Select"}
      </button>
    </div>
  );
}

// Campaign Wizard step 3 (SPEC-FE-031): the mockup's "AI-Generated Creative
// Variants" card, attached to the campaign draft. Variants come from "Write
// your own" (works without an LLM) or "Generate with AI" (needs a configured
// provider). "✓ Selected" reflects the persisted selected_variant_index.
export default function CreativeVariants({
  draft,
  onBack,
  onSaved,
}: {
  draft: CampaignDetail;
  onBack: () => void;
  onSaved: (d: CampaignDetail) => void;
}) {
  const channel = draft.channels[0] ?? "instagram";
  const existing = useQuery({
    queryKey: ["content", "creative", draft.creative_asset_id],
    queryFn: () => fetchCreative(draft.creative_asset_id!),
    enabled: !!draft.creative_asset_id,
  });
  const [asset, setAsset] = useState<CreativeAsset | null>(null);
  useEffect(() => {
    if (existing.data && !asset) setAsset(existing.data);
  }, [existing.data, asset]);

  const [mode, setMode] = useState<Mode>("write");
  const [notice, setNotice] = useState<string | null>(null);

  // "Write your own": up to 3 headline/description pairs.
  const [pairs, setPairs] = useState([
    { headline: "", description: "" },
    { headline: "", description: "" },
    { headline: "", description: "" },
  ]);
  const setPair = (i: number, key: "headline" | "description", v: string) =>
    setPairs((cur) => cur.map((p, j) => (j === i ? { ...p, [key]: v } : p)));
  const filled = pairs.filter((p) => p.headline.trim());
  const write = useMutation({
    mutationFn: () =>
      createManualCreative({
        channel,
        campaign_id: draft.id,
        title: draft.name,
        variants: filled.map((p) => ({ headline: p.headline.trim(), description: p.description.trim() })),
      }),
    onSuccess: (a) => setAsset(a),
  });

  // "Generate with AI": the objective comes from the draft.
  const products = useQuery({ queryKey: productKeys.list, queryFn: fetchProducts, enabled: mode === "ai" });
  const [brief, setBrief] = useState("");
  const [skus, setSkus] = useState<string[]>([]);
  const generate = useMutation({
    mutationFn: () => generateCreatives({ objective: draft.objective, skus, brief, channel, campaign_id: draft.id, title: draft.name }),
    onSuccess: (a) => setAsset(a),
    onError: (err) => {
      if (err instanceof ApiError && err.status === 503) {
        setNotice(NO_LLM);
        setMode("write");
      }
    },
  });
  const toggleSku = (sku: string) => setSkus((cur) => (cur.includes(sku) ? cur.filter((s) => s !== sku) : [...cur, sku]));

  const select = useMutation({ mutationFn: (index: number) => selectVariant(asset!.id, index), onSuccess: (a) => setAsset(a) });
  const save = useMutation({ mutationFn: () => updateDraft(draft.id, { creative_asset_id: asset!.id }), onSuccess: onSaved });

  return (
    <form
      className="card"
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <h3 className="mt-0">AI-Generated Creative Variants</h3>
      <p className="text-muted">Pick one or edit before continuing. All variants use your brand voice.</p>

      <div className="tabs" role="tablist">
        {(["write", "ai"] as Mode[]).map((m) => (
          <div
            key={m}
            role="tab"
            tabIndex={0}
            aria-selected={mode === m}
            className={mode === m ? "tab active" : "tab"}
            onClick={() => setMode(m)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") setMode(m);
            }}
          >
            {m === "write" ? "Write your own" : "Generate with AI"}
          </div>
        ))}
      </div>
      {notice && (
        <p className="mt-0 text-[13px] text-warn" role="note">
          {notice}
        </p>
      )}

      {mode === "write" ? (
        <div>
          {pairs.map((p, i) => (
            <div key={i} className="form-grid-2">
              <div className="form-row">
                <label htmlFor={`cv_h_${i}`}>Variant {i + 1} headline{i === 0 ? "" : " (optional)"}</label>
                <input id={`cv_h_${i}`} maxLength={120} value={p.headline} onChange={(e) => setPair(i, "headline", e.target.value)} />
              </div>
              <div className="form-row">
                <label htmlFor={`cv_d_${i}`}>Description</label>
                <input id={`cv_d_${i}`} maxLength={500} value={p.description} onChange={(e) => setPair(i, "description", e.target.value)} />
              </div>
            </div>
          ))}
          <button type="button" className="btn btn-sm" disabled={write.isPending || filled.length === 0} onClick={() => write.mutate()}>
            {write.isPending ? "Saving…" : asset ? "Replace with these variants" : "Use these variants"}
          </button>
          {write.isError && (
            <p className="mb-0 mt-3 text-xs text-danger" role="alert">
              {errorText(write.error, FORBIDDEN)}
            </p>
          )}
        </div>
      ) : (
        <div>
          <fieldset className="form-row border-none p-0">
            <legend className="mb-1.5 text-[13px] font-medium">Products</legend>
            {products.isPending ? (
              <span className="text-[13px] text-muted">Loading products…</span>
            ) : products.isError ? (
              <span className="text-[13px] text-danger">Failed to load products: {products.error.message}</span>
            ) : (
              <div className="flex flex-wrap gap-3 text-[13px]">
                {products.data.map((p) => (
                  <label key={p.id} className="flex items-center gap-1 font-normal">
                    <input type="checkbox" checked={skus.includes(p.sku)} onChange={() => toggleSku(p.sku)} />
                    {p.title}
                  </label>
                ))}
              </div>
            )}
          </fieldset>
          <div className="form-row">
            <label htmlFor="cv_brief">Brief</label>
            <textarea id="cv_brief" rows={2} value={brief} onChange={(e) => setBrief(e.target.value)} />
          </div>
          <button
            type="button"
            className="btn btn-sm"
            disabled={generate.isPending || skus.length === 0 || !brief.trim()}
            onClick={() => {
              setNotice(null);
              generate.mutate();
            }}
          >
            {generate.isPending ? "Generating…" : "Generate Variants"}
          </button>
          {generate.isError && !(generate.error instanceof ApiError && generate.error.status === 503) && (
            <p className="mb-0 mt-3 text-xs text-danger" role="alert">
              {errorText(generate.error, FORBIDDEN)}
            </p>
          )}
        </div>
      )}

      {existing.isPending && draft.creative_asset_id && <p className="mt-4 text-[13px] text-muted">Loading creative…</p>}
      {asset && asset.variants.length === 0 && (
        <p className="mt-4 text-[13px] text-muted">No variants were generated. Try a different brief.</p>
      )}
      {asset && asset.variants.length > 0 && (
        <div className="grid-3" style={{ marginTop: 16 }}>
          {asset.variants.map((v, i) => (
            <VariantCard
              key={`${asset.id}-${v.index}`}
              asset={asset}
              variant={v}
              i={i}
              busy={select.isPending}
              onSelect={() => select.mutate(v.index)}
              onEdited={setAsset}
            />
          ))}
        </div>
      )}
      {select.isError && (
        <p className="mb-0 mt-3 text-xs text-danger" role="alert">
          {errorText(select.error, FORBIDDEN)}
        </p>
      )}
      {save.isError && (
        <p className="mb-0 mt-3 text-xs text-danger" role="alert">
          {errorText(save.error)}
        </p>
      )}
      <StepNav
        onBack={onBack}
        next="Continue to Budget →"
        busy={save.isPending}
        disabled={!asset || asset.selected_variant_index === null}
        hint={!asset || asset.variants.length === 0 ? "Add variants to continue" : "Select a variant to continue"}
      />
    </form>
  );
}
