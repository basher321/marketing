"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { fetchGenerationReadiness, generationKeys } from "@/lib/api/generation";
import { createAI, createManual } from "@/lib/api/organic";
import { fetchProducts, productKeys } from "@/lib/api/products";
import { fetchSocialAccounts, socialKeys } from "@/lib/api/social";
import type { AICreate } from "@/lib/types/organic";
import { PLATFORM_LABEL, PLATFORMS, type SocialPlatform } from "@/lib/types/social";
import { useCreatedItemTab } from "@/hooks/use-new-tab";

import MediaPicker from "./media-picker";
import { errorText } from "./shared";

const LIMITS: Record<SocialPlatform, number> = { facebook: 63206, instagram: 2200, tiktok: 2200, linkedin: 3000 };

function PlatformChooser({ value, onChange }: { value: SocialPlatform[]; onChange: (p: SocialPlatform[]) => void }) {
  const accounts = useQuery({ queryKey: socialKeys.accounts, queryFn: fetchSocialAccounts });
  return (
    <div className="flex flex-wrap gap-2" data-testid="platform-chooser">
      {PLATFORMS.map((p) => {
        const acct = accounts.data?.items.find((a) => a.platform === p);
        const ok = acct?.status === "connected";
        const why = !acct ? "" : acct.status === "not_connected" ? "not connected" : acct.status.replace(/_/g, " ");
        return (
          <label key={p} className={`card flex cursor-pointer items-center gap-2 text-[13px] ${ok ? "" : "opacity-70"}`} style={{ padding: "8px 10px" }} title={ok ? acct?.account_name ?? "" : `${PLATFORM_LABEL[p]}: ${why}`}>
            <input type="checkbox" checked={value.includes(p)} onChange={(e) => onChange(e.target.checked ? [...value, p] : value.filter((x) => x !== p))} />
            <span>
              {PLATFORM_LABEL[p]}
              <span className="block text-[11px] text-muted">{ok ? acct?.account_name ?? "connected" : why || "…"}</span>
            </span>
          </label>
        );
      })}
      <Link href="/marketing/organic/accounts" className="self-center text-xs text-accent underline">
        Manage accounts
      </Link>
    </div>
  );
}

function ManualForm() {
  const [caption, setCaption] = useState("");
  const [hashtags, setHashtags] = useState("");
  const [cta, setCta] = useState("");
  const [link, setLink] = useState("");
  const [media, setMedia] = useState<string[]>([]);
  const [platforms, setPlatforms] = useState<SocialPlatform[]>(["facebook", "instagram"]);
  const [adapt, setAdapt] = useState<"rules" | "ai">("rules");
  const strictest = platforms.length ? Math.min(...platforms.map((p) => LIMITS[p])) : 0;
  const newTab = useCreatedItemTab();
  const create = useMutation({
    mutationFn: () =>
      createManual({
        caption,
        hashtags: hashtags.split(/[\s,]+/).filter(Boolean),
        cta: cta || null,
        link_url: link || null,
        media_ids: media,
        targets: platforms.map((platform) => ({ platform })),
        adapt,
      }),
    onSuccess: (c) => newTab.open(`/marketing/organic/content/${c.id}`), // SPEC-FE-058
    onError: () => newTab.cancel(),
  });
  return (
    <div className="card" data-testid="manual-form">
      <div className="form-row">
        <label htmlFor="c_caption">Caption</label>
        <textarea id="c_caption" rows={6} value={caption} onChange={(e) => setCaption(e.target.value)} placeholder="Write your post…" />
        {strictest > 0 && (
          <p className={`m-0 text-xs ${caption.length > strictest ? "text-danger" : "text-muted"}`}>
            {caption.length.toLocaleString()} / {strictest.toLocaleString()} (the strictest selected platform; longer text is shortened per platform)
          </p>
        )}
      </div>
      <div className="form-grid-2">
        <div className="form-row">
          <label htmlFor="c_tags">Hashtags</label>
          <input id="c_tags" value={hashtags} onChange={(e) => setHashtags(e.target.value)} placeholder="newarrivals summer" />
        </div>
        <div className="form-row">
          <label htmlFor="c_cta">Call to action</label>
          <input id="c_cta" value={cta} onChange={(e) => setCta(e.target.value)} placeholder="Shop now" />
        </div>
      </div>
      <div className="form-row">
        <label htmlFor="c_link">Link (optional, https)</label>
        <input id="c_link" value={link} onChange={(e) => setLink(e.target.value)} placeholder="https://your-shop.com/product" />
      </div>
      <div className="form-row">
        <label>Image or video</label>
        <MediaPicker value={media} onChange={(ids) => setMedia(ids)} />
      </div>
      <div className="form-row">
        <label>Platforms</label>
        <PlatformChooser value={platforms} onChange={setPlatforms} />
      </div>
      <div className="form-row">
        <label htmlFor="c_adapt">Platform versions</label>
        <select id="c_adapt" value={adapt} onChange={(e) => setAdapt(e.target.value as "rules" | "ai")}>
          <option value="rules">Adapt by each platform&apos;s rules (no AI)</option>
          <option value="ai">Adapt with AI (tone, hashtags and CTA per platform)</option>
        </select>
      </div>
      <button type="button" className="btn" disabled={!caption.trim() || platforms.length === 0 || create.isPending} onClick={() => { newTab.begin(); create.mutate(); }}>
        {create.isPending ? "Creating…" : "Create versions & preview"}
      </button>
      {create.isError && <p className="m-0 mt-2 text-xs text-danger" role="alert">{errorText(create.error)}</p>}
    </div>
  );
}

function AIForm() {
  const [prompt, setPrompt] = useState("");
  const [productIds, setProductIds] = useState<string[]>([]);
  const [tone, setTone] = useState("");
  const [link, setLink] = useState("");
  const [platforms, setPlatforms] = useState<SocialPlatform[]>(["facebook", "instagram"]);
  const [mediaMode, setMediaMode] = useState<AICreate["media"]["mode"]>("none");
  const [media, setMedia] = useState<string[]>([]);
  const [ratio, setRatio] = useState("");
  const [duration, setDuration] = useState(8);
  const products = useQuery({ queryKey: productKeys.list, queryFn: fetchProducts });
  const readiness = useQuery({ queryKey: generationKeys.readiness, queryFn: fetchGenerationReadiness });
  const newTab = useCreatedItemTab();
  const create = useMutation({
    mutationFn: () =>
      createAI({
        prompt,
        product_ids: productIds,
        tone: tone || null,
        link_url: link || null,
        targets: platforms.map((platform) => ({ platform })),
        media: {
          mode: mediaMode,
          media_ids: mediaMode === "use" ? media : [],
          generation: mediaMode.startsWith("generate") ? { ...(ratio ? { aspect_ratio: ratio } : {}), ...(mediaMode === "generate_video" ? { duration_s: duration } : {}) } : {},
        },
      }),
    onSuccess: (c) => newTab.open(`/marketing/organic/content/${c.id}`), // SPEC-FE-058
    onError: () => newTab.cancel(),
  });
  const genReady = mediaMode === "generate_photo" ? readiness.data?.image_ready : mediaMode === "generate_video" ? readiness.data?.video_ready : true;
  return (
    <div className="card" data-testid="ai-form">
      <div className="form-row">
        <label htmlFor="a_prompt">What should the post be about?</label>
        <textarea id="a_prompt" rows={4} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Announce our new summer collection: light linen shirts, 20% off this week" />
      </div>
      <div className="form-grid-2">
        <div className="form-row">
          <label htmlFor="a_products">Products (optional)</label>
          <select
            id="a_products"
            multiple
            size={4}
            value={productIds}
            onChange={(e) => setProductIds(Array.from(e.target.selectedOptions).map((o) => o.value).slice(0, 10))}
          >
            {(products.data ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.title} ({p.sku})
              </option>
            ))}
          </select>
        </div>
        <div>
          <div className="form-row">
            <label htmlFor="a_tone">Tone (optional)</label>
            <input id="a_tone" value={tone} onChange={(e) => setTone(e.target.value)} placeholder="friendly, excited" />
          </div>
          <div className="form-row">
            <label htmlFor="a_link">Link (optional, https)</label>
            <input id="a_link" value={link} onChange={(e) => setLink(e.target.value)} placeholder="https://…" />
          </div>
        </div>
      </div>
      <div className="form-row">
        <label>Platforms</label>
        <PlatformChooser value={platforms} onChange={setPlatforms} />
      </div>
      <div className="form-row">
        <label htmlFor="a_media">Image or video</label>
        <select id="a_media" value={mediaMode} onChange={(e) => setMediaMode(e.target.value as AICreate["media"]["mode"])}>
          <option value="none">No media (text post)</option>
          <option value="use">Use media from my library</option>
          <option value="generate_photo">Generate a photo with AI</option>
          <option value="generate_video">Generate a video with AI</option>
        </select>
      </div>
      {mediaMode === "use" && <MediaPicker value={media} onChange={(ids) => setMedia(ids)} />}
      {mediaMode.startsWith("generate") && (
        <div className="form-grid-2">
          <div className="form-row">
            <label htmlFor="a_ratio">Aspect ratio</label>
            <select id="a_ratio" value={ratio} onChange={(e) => setRatio(e.target.value)}>
              <option value="">Best for the first platform</option>
              {(mediaMode === "generate_video" ? ["9:16", "16:9", "1:1"] : ["1:1", "4:5", "9:16", "16:9"]).map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>
          {mediaMode === "generate_video" && (
            <div className="form-row">
              <label htmlFor="a_dur">Duration (seconds)</label>
              <input id="a_dur" type="number" min={2} max={60} value={duration} onChange={(e) => setDuration(Number(e.target.value))} />
              <p className="m-0 text-xs text-muted">
                Supported:{" "}
                {(readiness.data?.video ?? []).filter((p) => p.ready).map((p) => `${p.label} ${p.durations.join("/")} s`).join("; ") || "no video model set up"}
              </p>
            </div>
          )}
        </div>
      )}
      {!genReady && (
        <p className="m-0 mb-2 text-xs text-warn">
          {readiness.data?.setup_hint}{" "}
          <Link href="/integrations" className="underline">
            Integrations
          </Link>
        </p>
      )}
      <button type="button" className="btn" disabled={prompt.trim().length < 3 || platforms.length === 0 || !genReady || create.isPending} onClick={() => { newTab.begin(); create.mutate(); }}>
        {create.isPending ? "Writing…" : "Generate"}
      </button>
      <p className="m-0 mt-2 text-xs text-muted">AI drafts always stop for your review and approval before anything is published.</p>
      {create.isError && <p className="m-0 mt-2 text-xs text-danger" role="alert">{errorText(create.error)}</p>}
    </div>
  );
}

export default function CreateForm() {
  const params = useSearchParams();
  const router = useRouter();
  const mode = params.get("mode") === "ai" ? "ai" : "manual";
  return (
    <>
      <div className="tabs mb-3" role="tablist">
        <button type="button" role="tab" aria-selected={mode === "manual"} className={mode === "manual" ? "tab active" : "tab"} onClick={() => router.replace("/marketing/organic/create?mode=manual")}>
          Manual
        </button>
        <button type="button" role="tab" aria-selected={mode === "ai"} className={mode === "ai" ? "tab active" : "tab"} onClick={() => router.replace("/marketing/organic/create?mode=ai")}>
          AI / Prompt
        </button>
      </div>
      {mode === "ai" ? <AIForm /> : <ManualForm />}
    </>
  );
}
