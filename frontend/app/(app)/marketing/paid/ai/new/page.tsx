"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";

import { errorText } from "@/components/campaigns/platform-builder/tree";
import { aiCampaignKeys, fetchReadiness, startRun } from "@/lib/api/ai-campaigns";
import type { PlatformKey } from "@/lib/types/ads";
import type { AICampaignCreate, Readiness } from "@/lib/types/ai-campaigns";

const COUNTRY: Record<string, string> = { BD: "Bangladesh", IN: "India", PK: "Pakistan", US: "the United States", GB: "the United Kingdom", AE: "the UAE" };
const YOUTUBE_LINK = /^(https:\/\/(www\.)?(youtube\.com\/(watch\?v=|shorts\/)|youtu\.be\/)[A-Za-z0-9_-]{11}|[A-Za-z0-9_-]{11})/;

function money(n: number, currency: string): string {
  return `${n.toLocaleString("en-US", { maximumFractionDigits: 2 })} ${currency}`;
}

/** Example prompts from the company's own active products and real prices:
 * a discount is mentioned only when the product's compare-at price shows one. */
function examples(r: Readiness): string[] {
  const where = COUNTRY[r.country] ? ` in ${COUNTRY[r.country]}` : "";
  return r.products
    .filter((p) => p.selectable)
    .slice(0, 3)
    .map((p) =>
      p.discount_pct > 0
        ? `Promote our ${p.title}, now ${money(p.price, p.currency)} (${p.discount_pct}% off ${money(p.compare_at ?? p.price, p.currency)}), to shoppers${where}.`
        : `Promote our ${p.title} at ${money(p.price, p.currency)} to shoppers${where} who would value it.`,
    );
}

function toIso(local: string): string | null {
  return local ? new Date(local).toISOString() : null;
}

// Create with AI (SPEC-FE-046 + its 2026-10-02 amendment): every option is
// offered only when it can really work, from GET /ai-campaigns/readiness, and
// the "Before you start" list says what is missing. The server enforces the
// same rules. The AI prepares drafts; the run always stops for review.
export default function NewAICampaignPage() {
  const router = useRouter();
  const ready = useQuery({ queryKey: aiCampaignKeys.readiness, queryFn: fetchReadiness });
  const [prompt, setPrompt] = useState("");
  const [chosen, setChosen] = useState<PlatformKey[]>([]);
  const [goal, setGoal] = useState<AICampaignCreate["goal"]>(null);
  const [amount, setAmount] = useState("");
  const [budgetMode, setBudgetMode] = useState<"daily" | "total">("total");
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [skus, setSkus] = useState<string[]>([]);
  const [landing, setLanding] = useState("https://");
  const [visuals, setVisuals] = useState<AICampaignCreate["visuals"]>("builder");
  const [youtube, setYoutube] = useState("");
  const [variants, setVariants] = useState(2);
  const [tried, setTried] = useState(false);

  const r = ready.data;
  const picked = (r?.products ?? []).filter((p) => skus.includes(p.sku));
  const photosOk = picked.length > 0 && picked.every((p) => p.has_photo);

  // Field checks, the same rules the server applies.
  const errors = useMemo(() => {
    const e: Record<string, string> = {};
    const text = prompt.trim();
    if (text.length < 10) e.prompt = "Describe what you want to advertise in at least 10 characters.";
    if (text.length > 2000) e.prompt = "Keep it under 2000 characters.";
    if (chosen.length === 0) e.platforms = "Pick 1 to 3 connected platforms.";
    const n = Number(amount);
    if (!amount || !Number.isFinite(n) || n <= 0) e.budget = "Enter a budget above 0.";
    else if (!/^\d+(\.\d{1,2})?$/.test(amount)) e.budget = "Use at most 2 decimals.";
    const now = Date.now();
    if (startsAt && new Date(startsAt).getTime() < now - 5 * 60_000) e.start = "The start can't be in the past.";
    if (endsAt && new Date(endsAt).getTime() <= now) e.end = "The end must be in the future.";
    if (startsAt && endsAt && new Date(endsAt) <= new Date(startsAt)) e.end = "The end must be after the start.";
    try {
      const u = new URL(landing.trim());
      if (u.protocol !== "https:" || !u.hostname.includes(".")) e.landing = "Use a full https:// address of your page.";
    } catch {
      e.landing = "Use a full https:// address of your page.";
    }
    if (chosen.includes("youtube") && !YOUTUBE_LINK.test(youtube.trim())) e.youtube = "Paste a youtube.com or youtu.be link to your video.";
    if (visuals === "products" && !photosOk) e.visuals = "Every featured product needs a photo for this option.";
    if (visuals === "generate" && r && !r.image_ai.ready) e.visuals = r.image_ai.reason ?? "No image source is ready.";
    return e;
  }, [prompt, chosen, amount, startsAt, endsAt, landing, youtube, visuals, photosOk, r]);

  // "Before you start": what blocks Start that the person can't fix in the form.
  const blockers: { text: string; href?: string; link?: string }[] = [];
  if (r) {
    if (!r.platforms.some((p) => p.usable)) blockers.push({ text: "No ad platform is connected with real credentials.", href: "/integrations", link: "Connect one in Integrations" });
    if (!r.text_ai.ready) blockers.push({ text: r.text_ai.reason ?? "No AI model is ready.", href: "/integrations", link: "Open AI Models" });
  }
  const formOk = Object.keys(errors).length === 0;
  const canStart = Boolean(r) && blockers.length === 0 && formOk;

  const start = useMutation({
    mutationFn: () =>
      startRun({
        prompt: prompt.trim(),
        platforms: chosen,
        goal,
        budget: { amount, mode: budgetMode },
        schedule: { starts_at: toIso(startsAt), ends_at: toIso(endsAt) },
        skus,
        landing_url: landing.trim(),
        visuals,
        youtube_video: chosen.includes("youtube") ? youtube.trim() : null,
        variants_per_group: variants,
      }),
    onSuccess: (run) => router.push(`/marketing/paid/ai/${run.id}`),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTried(true);
    if (canStart) start.mutate();
  };
  const toggle = (key: PlatformKey) => setChosen((cur) => (cur.includes(key) ? cur.filter((k) => k !== key) : cur.length >= 3 ? cur : [...cur, key]));
  // An error shows once its field was edited (or after a Start attempt).
  const edited: Record<string, boolean> = {
    prompt: prompt !== "", budget: amount !== "", start: startsAt !== "", end: endsAt !== "", landing: landing !== "https://",
    youtube: youtube !== "", visuals: true, platforms: false,
  };
  const show = (key: string) => ((tried || edited[key]) && errors[key] ? <span className="block text-xs text-danger" data-error={key}>{errors[key]}</span> : null);

  if (ready.isPending) return <p className="text-[13px] text-muted">Checking what&apos;s set up…</p>;
  if (ready.isError || !r) return <p className="text-[13px] text-danger" role="alert">{ready.error?.message ?? "Couldn't load."}</p>;
  const exampleList = examples(r);

  return (
    <form onSubmit={submit} className="mx-auto max-w-[820px]" noValidate>
      <Link href="/marketing/paid/ad-manager" className="mb-3 inline-block text-[13px] text-accent underline">
        ← Back to the Ad Manager
      </Link>
      <h1 className="m-0 mb-1 text-[22px] font-bold">Create a campaign with AI</h1>
      <p className="m-0 mb-4 text-muted">Describe what you want to promote. The AI plans the campaign, finds the audience, writes the ads and makes the images, using only your real products, prices and brand rules.</p>
      <p className="m-0 mb-4 rounded border border-border bg-accent-soft p-2 text-[13px]" data-testid="review-note">
        AI prepares everything; <b>you review and publish</b>. Nothing goes live until you click Publish.
      </p>

      {blockers.length > 0 && (
        <div className="card mb-4" data-testid="checklist" style={{ borderColor: "var(--warn)" }}>
          <h3 className="mb-1 mt-0 text-[14px]">Before you start</h3>
          <ul className="m-0 pl-4 text-[13px]">
            {blockers.map((b, i) => (
              <li key={i} className="mb-1" data-blocker={i}>
                {b.text}{" "}
                {b.href && (
                  <Link href={b.href} className="text-accent underline">
                    {b.link}
                  </Link>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="form-row">
        <label htmlFor="ai_prompt">What do you want to advertise?</label>
        <textarea id="ai_prompt" rows={4} maxLength={2000} value={prompt} onChange={(e) => setPrompt(e.target.value)}
          placeholder="Your product or offer, who it's for, where, and why now. Don't mention prices or discounts that aren't in your product list." />
        <span className="text-xs text-muted">{prompt.trim().length}/2000</span>
        {show("prompt")}
        {exampleList.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1" data-testid="examples">
            <span className="text-xs text-muted">From your products:</span>
            {exampleList.map((ex) => (
              <button key={ex} type="button" className="btn btn-ghost btn-sm text-left text-xs" onClick={() => setPrompt(ex)}>
                {ex.length > 60 ? `${ex.slice(0, 58)}…` : ex}
              </button>
            ))}
          </div>
        )}
      </div>

      <fieldset className="form-row">
        <legend className="text-xs font-semibold">Platforms (1 to 3)</legend>
        <div className="flex flex-wrap gap-2">
          {r.platforms.map((p) => (
            <label key={p.key} className={`inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-[13px] ${p.usable ? "" : "opacity-50"}`} title={p.reason ?? undefined}>
              <input type="checkbox" disabled={!p.usable} checked={chosen.includes(p.key)} onChange={() => toggle(p.key)} data-platform={p.key} />
              {p.label}
              {!p.usable && <span className="text-xs text-muted">({p.reason})</span>}
            </label>
          ))}
        </div>
        {show("platforms")}
      </fieldset>

      <div className="grid gap-x-4 sm:grid-cols-3">
        <div className="form-row">
          <label htmlFor="ai_goal">Goal</label>
          <select id="ai_goal" value={goal ?? ""} onChange={(e) => setGoal((e.target.value || null) as AICampaignCreate["goal"])}>
            <option value="">Let the AI decide</option>
            <option value="sales">Sales</option>
            <option value="traffic">Website traffic</option>
            <option value="leads">Leads</option>
            <option value="awareness">Awareness</option>
            <option value="app">App installs</option>
          </select>
        </div>
        <div className="form-row">
          <label htmlFor="ai_budget">Budget ({r.currency})</label>
          <input id="ai_budget" type="number" min={1} step="0.01" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
          {show("budget")}
        </div>
        <div className="form-row">
          <label htmlFor="ai_budget_mode">Budget type</label>
          <select id="ai_budget_mode" value={budgetMode} onChange={(e) => setBudgetMode(e.target.value as "daily" | "total")}>
            <option value="total">Total for the campaign</option>
            <option value="daily">Per day</option>
          </select>
        </div>
        <div className="form-row">
          <label htmlFor="ai_start">Start (empty = in 1 hour)</label>
          <input id="ai_start" type="datetime-local" value={startsAt} onChange={(e) => setStartsAt(e.target.value)} />
          {show("start")}
        </div>
        <div className="form-row">
          <label htmlFor="ai_end">End (empty = 7 days after the start)</label>
          <input id="ai_end" type="datetime-local" value={endsAt} onChange={(e) => setEndsAt(e.target.value)} />
          {show("end")}
        </div>
        <div className="form-row">
          <label htmlFor="ai_variants">Ads per audience</label>
          <select id="ai_variants" value={variants} onChange={(e) => setVariants(Number(e.target.value))}>
            <option value={1}>1</option>
            <option value={2}>2</option>
            <option value={3}>3</option>
          </select>
        </div>
      </div>

      <div className="form-row">
        <label htmlFor="ai_landing">Landing page (where the ads send people)</label>
        <input id="ai_landing" type="url" value={landing} onChange={(e) => setLanding(e.target.value)} />
        {show("landing")}
      </div>

      <fieldset className="form-row">
        <legend className="text-xs font-semibold">Products to feature (optional; the AI uses only their real details)</legend>
        {r.products.length === 0 ? (
          <span className="text-xs text-muted">No products yet.</span>
        ) : (
          <div className="grid gap-1 sm:grid-cols-2" data-testid="products">
            {r.products.map((p) => (
              <label key={p.sku} className={`inline-flex items-center gap-1 text-[13px] ${p.selectable ? "" : "opacity-50"}`} title={p.reason ?? undefined} data-sku={p.sku}>
                <input type="checkbox" disabled={!p.selectable} checked={skus.includes(p.sku)}
                  onChange={(e) => setSkus((cur) => (e.target.checked ? [...cur, p.sku].slice(0, 10) : cur.filter((s) => s !== p.sku)))} />
                {p.title} · {money(p.price, p.currency)}
                {p.discount_pct > 0 && <span className="text-xs text-success">({p.discount_pct}% off)</span>}
                {!p.has_photo && <span className="text-xs text-muted">· no photo</span>}
                {p.reason && <span className="text-xs text-warn">· {p.reason}</span>}
              </label>
            ))}
          </div>
        )}
      </fieldset>

      <fieldset className="form-row">
        <legend className="text-xs font-semibold">Images</legend>
        {(
          [
            ["generate", "Generate with AI", r.image_ai.ready ? `(${r.image_ai.sources.map((s) => s.label).join(", ")})` : null, !r.image_ai.ready, r.image_ai.reason],
            ["products", "Use the featured products' photos", null, !photosOk, picked.length === 0 ? "Pick products first." : "Some picked products have no photo."],
            ["builder", "I'll add images in the builder", null, false, null],
          ] as const
        ).map(([value, text, note, disabled, reason]) => (
          <label key={value} className={`mr-4 block text-[13px] ${disabled ? "opacity-50" : ""}`} data-visuals={value}>
            <input type="radio" name="ai_visuals" disabled={disabled} checked={visuals === value} onChange={() => setVisuals(value)} /> {text}{" "}
            {note && <span className="text-xs text-muted">{note}</span>}
            {disabled && reason && <span className="text-xs text-warn">— {reason}</span>}
          </label>
        ))}
        {show("visuals")}
      </fieldset>

      {chosen.includes("youtube") && (
        <div className="form-row">
          <label htmlFor="ai_youtube">Your YouTube video (link)</label>
          <input id="ai_youtube" value={youtube} onChange={(e) => setYoutube(e.target.value)} placeholder="https://youtu.be/…" />
          {show("youtube")}
        </div>
      )}

      {tried && !formOk && <p className="text-xs text-danger" role="alert">Fix the highlighted fields first.</p>}
      {start.isError && <p className="text-xs text-danger" role="alert">{errorText(start.error)}</p>}
      <div className="flex items-center gap-2">
        <button type="submit" className="btn" disabled={start.isPending || blockers.length > 0}>
          {start.isPending ? "Starting…" : "Start"}
        </button>
        <Link href="/marketing/paid/ad-manager" className="btn btn-secondary">
          Cancel
        </Link>
        {blockers.length > 0 && <span className="text-xs text-muted">Start is available once the items under “Before you start” are done.</span>}
      </div>
    </form>
  );
}
