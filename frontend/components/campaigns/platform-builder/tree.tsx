"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import {
  uploadPlatformMedia,
  addGroup,
  addPlatformAd,
  adsKeys,
  deleteGroup,
  deletePlatformAd,
  duplicateGroup,
  duplicatePlatformAd,
} from "@/lib/api/ads";
import { ApiError } from "@/lib/types/common";
import type { BuilderPlatform, Level, Platform, PlatformTree } from "@/lib/types/ads";

// ---------------------------------------------------------------------------
// Field definitions per platform (SPEC-FE-045). The keys are the ones the
// platform adapters read (SPEC-BE-063..068); each form renders only its own
// platform's list, so the builder is one component for seven platforms.
// ---------------------------------------------------------------------------
export type Option = { value: string; label: string };
export type FieldSpec = {
  key: string;
  label: string;
  kind: "text" | "textarea" | "number" | "select" | "multiselect" | "checkbox" | "list" | "media" | "url";
  options?: Option[];
  /** list: how many entries the platform needs. */
  min?: number;
  max?: number;
  /** ad fields: only for these formats (all formats when omitted). */
  formats?: string[];
  /** shown only when another field has one of these values. */
  when?: { key: string; in: string[] };
  hint?: string;
};

const o = (...pairs: [string, string][]): Option[] => pairs.map(([value, label]) => ({ value, label }));

export const CAMPAIGN_FIELDS: Record<BuilderPlatform, FieldSpec[]> = {
  tiktok: [{ key: "budget_optimization", label: "Campaign budget optimisation (TikTok spreads the campaign budget across ad groups)", kind: "checkbox" }],
  google: [
    { key: "bidding", label: "Bidding", kind: "select", options: o(["MAXIMIZE_CLICKS", "Maximize clicks"], ["MAXIMIZE_CONVERSIONS", "Maximize conversions"], ["MAXIMIZE_CONVERSION_VALUE", "Maximize conversion value"], ["TARGET_IMPRESSION_SHARE", "Target impression share (Search)"]) },
    { key: "target_cpa", label: "Target cost per action (optional)", kind: "number", when: { key: "bidding", in: ["MAXIMIZE_CONVERSIONS"] } },
    { key: "target_roas", label: "Target ROAS % (optional)", kind: "number", when: { key: "bidding", in: ["MAXIMIZE_CONVERSION_VALUE"] } },
    { key: "search_partners", label: "Include Google search partners", kind: "checkbox", when: { key: "campaign_type", in: ["SEARCH"] } },
    { key: "display_network", label: "Include the Display Network", kind: "checkbox", when: { key: "campaign_type", in: ["SEARCH"] } },
  ],
  youtube: [
    // YouTube ads publish as Demand Gen campaigns, which take these bid strategies.
    { key: "bidding", label: "Bidding", kind: "select", options: o(["MAXIMIZE_CONVERSIONS", "Maximize conversions"], ["MAXIMIZE_CONVERSION_VALUE", "Maximize conversion value"], ["MAXIMIZE_CLICKS", "Maximize clicks"]) },
    { key: "target_cpa", label: "Target cost per action (optional)", kind: "number", when: { key: "bidding", in: ["MAXIMIZE_CONVERSIONS"] } },
  ],
  linkedin: [],
  x: [{ key: "funding_instrument_id", label: "Funding source ID (optional)", kind: "text", hint: "Empty uses the ad account's first active funding source." }],
  snapchat: [],
  pinterest: [{ key: "budget_optimization", label: "Campaign budget optimisation", kind: "checkbox" }],
};

const BID = { key: "bid_amount", label: "Bid amount", kind: "number" } as const;
export const GROUP_FIELDS: Record<BuilderPlatform, FieldSpec[]> = {
  tiktok: [
    { key: "placement", label: "Placements", kind: "select", options: o(["AUTOMATIC", "Automatic placement (recommended)"], ["SELECT", "Select placements"]) },
    { key: "placements", label: "Where", kind: "multiselect", options: o(["TIKTOK", "TikTok"], ["PANGLE", "Pangle"], ["GLOBAL_APP_BUNDLE", "Global App Bundle"]), when: { key: "placement", in: ["SELECT"] } },
    { key: "optimization_goal", label: "Optimisation goal", kind: "select", options: o(["CLICK", "Clicks"], ["CONVERT", "Conversions"], ["REACH", "Reach"], ["VIDEO_VIEW", "Video views"], ["LEAD_GENERATION", "Leads"], ["INSTALL", "App installs"]) },
    { key: "bid_strategy", label: "Bid strategy", kind: "select", options: o(["LOWEST_COST", "Lowest cost"], ["COST_CAP", "Cost cap"], ["BID_CAP", "Bid cap"]) },
    { ...BID, when: { key: "bid_strategy", in: ["COST_CAP", "BID_CAP"] } },
    { key: "pixel_id", label: "TikTok pixel ID (website conversions)", kind: "text" },
    { key: "optimization_event", label: "Optimisation event (e.g. COMPLETE_PAYMENT)", kind: "text" },
    { key: "app_id", label: "App ID (app promotion)", kind: "text" },
  ],
  google: [{ key: "default_cpc", label: "Default max cost per click (optional)", kind: "number" }],
  youtube: [],
  linkedin: [
    { key: "bid_strategy", label: "Bidding", kind: "select", options: o(["MAXIMUM_DELIVERY", "Maximum delivery"], ["COST_CAP", "Cost cap"], ["MANUAL_CPC", "Manual CPC"], ["MANUAL_CPM", "Manual CPM"]) },
    { ...BID, when: { key: "bid_strategy", in: ["COST_CAP", "MANUAL_CPC", "MANUAL_CPM"] } },
    { key: "audience_expansion", label: "Audience Expansion", kind: "checkbox" },
    { key: "lead_form_id", label: "Lead Gen Form ID (lead generation)", kind: "text" },
    { key: "conversion_ids", label: "Conversion IDs (comma-separated)", kind: "text" },
  ],
  x: [
    { key: "placements", label: "Placements", kind: "multiselect", options: o(["ALL_ON_TWITTER", "X (timelines, search, profiles)"], ["PUBLISHER_NETWORK", "X Audience Platform"]) },
    { key: "bid_strategy", label: "Bid strategy", kind: "select", options: o(["AUTO", "Automatic bid"], ["MAX", "Maximum bid"], ["TARGET", "Target bid"]) },
    { ...BID, when: { key: "bid_strategy", in: ["MAX", "TARGET"] } },
  ],
  snapchat: [
    { key: "placement", label: "Placement", kind: "select", options: o(["AUTOMATIC", "Automatic (recommended)"], ["CONTENT", "Between content: Stories, Discover, Spotlight"]) },
    { key: "optimization_goal", label: "Optimisation goal", kind: "select", options: o(["IMPRESSIONS", "Impressions"], ["SWIPES", "Swipe ups"], ["PIXEL_PURCHASE", "Purchases (Snap Pixel)"], ["APP_INSTALLS", "App installs"], ["LEADS", "Leads"]) },
    { key: "bid_strategy", label: "Bid strategy", kind: "select", options: o(["AUTO_BID", "Auto bid"], ["LOWEST_COST_WITH_MAX_BID", "Max bid"], ["TARGET_COST", "Target cost"]) },
    { ...BID, when: { key: "bid_strategy", in: ["LOWEST_COST_WITH_MAX_BID", "TARGET_COST"] } },
    { key: "pixel_id", label: "Snap Pixel ID (sales)", kind: "text" },
  ],
  pinterest: [
    { key: "placement", label: "Placement", kind: "select", options: o(["ALL", "All (browse and search)"], ["BROWSE", "Browse"], ["SEARCH", "Search"]) },
    { key: "bid_strategy", label: "Bid strategy", kind: "select", options: o(["AUTOMATIC_BID", "Automatic bid"], ["MAX_BID", "Maximum bid"], ["TARGET_AVG", "Target average cost"]) },
    { ...BID, when: { key: "bid_strategy", in: ["MAX_BID", "TARGET_AVG"] } },
    { key: "conversion_tag_id", label: "Pinterest tag ID (conversions)", kind: "text" },
  ],
};

export type TargetSection = { key: string; label: string; lookup?: string; match?: boolean };
const LOC: TargetSection = { key: "locations", label: "Locations", lookup: "locations" };
const LANG: TargetSection = { key: "languages", label: "Languages", lookup: "languages" };
const AUD: TargetSection = { key: "audiences", label: "Custom audiences", lookup: "audiences" };
const INT: TargetSection = { key: "interests", label: "Interests", lookup: "interests" };
const KW: TargetSection = { key: "keywords", label: "Keywords", lookup: "keywords" };
export const TARGETING: Record<BuilderPlatform, { sections: TargetSection[]; demographics: boolean }> = {
  tiktok: { sections: [LOC, LANG, INT, AUD], demographics: true },
  google: { sections: [LOC, LANG, { ...KW, match: true }, { key: "negative_keywords", label: "Negative keywords", match: true }, AUD], demographics: true },
  youtube: { sections: [LOC, LANG, KW, { key: "topics", label: "Topics", lookup: "topics" }, AUD], demographics: true },
  linkedin: {
    sections: [
      LOC, LANG,
      { key: "job_titles", label: "Job titles", lookup: "titles" },
      { key: "industries", label: "Industries", lookup: "industries" },
      { key: "company_sizes", label: "Company sizes", lookup: "company_sizes" },
      { key: "seniorities", label: "Seniorities", lookup: "seniorities" },
      { key: "skills", label: "Skills", lookup: "skills" },
      AUD,
    ],
    demographics: false,
  },
  x: { sections: [LOC, LANG, INT, KW, AUD], demographics: true },
  snapchat: { sections: [LOC, LANG, INT, AUD], demographics: true },
  pinterest: { sections: [LOC, LANG, INT, KW, AUD], demographics: true },
};

const URL_F: FieldSpec = { key: "destination_url", label: "Destination URL", kind: "url" };
const ctas = (...v: string[]) => v.map((x) => ({ value: x, label: x.replace(/_/g, " ").toLowerCase().replace(/^./, (c) => c.toUpperCase()) }));
export const AD_FIELDS: Record<BuilderPlatform, FieldSpec[]> = {
  tiktok: [
    { key: "identity_id", label: "Identity (the TikTok account the ad shows as)", kind: "text" },
    { key: "existing_post_id", label: "TikTok post ID to boost", kind: "text", formats: ["spark_ad"] },
    { key: "display_name", label: "Display name", kind: "text", formats: ["single_video", "single_image"] },
    { key: "ad_text", label: "Ad text", kind: "textarea" },
    { key: "media", label: "Video or image", kind: "media", formats: ["single_video", "single_image"] },
    { key: "cta", label: "Call to action", kind: "select", options: ctas("LEARN_MORE", "SHOP_NOW", "SIGN_UP", "DOWNLOAD", "CONTACT_US", "ORDER_NOW", "BOOK_NOW", "APPLY_NOW") },
    URL_F,
  ],
  google: [
    { key: "headlines", label: "Headlines", kind: "list", min: 3, max: 15, formats: ["responsive_search", "asset_group"] },
    { key: "headlines", label: "Headlines", kind: "list", min: 1, max: 5, formats: ["responsive_display", "demand_gen"] },
    { key: "long_headlines", label: "Long headlines", kind: "list", min: 1, max: 5, formats: ["responsive_display", "demand_gen", "asset_group"] },
    { key: "descriptions", label: "Descriptions", kind: "list", min: 2, max: 4, formats: ["responsive_search"] },
    { key: "descriptions", label: "Descriptions", kind: "list", min: 1, max: 5, formats: ["responsive_display", "demand_gen", "asset_group"] },
    { key: "path1", label: "Display path 1", kind: "text", formats: ["responsive_search"] },
    { key: "path2", label: "Display path 2", kind: "text", formats: ["responsive_search"] },
    { key: "business_name", label: "Business name", kind: "text", formats: ["responsive_display", "demand_gen", "asset_group"] },
    { key: "media", label: "Images and logo", kind: "media", formats: ["responsive_display", "demand_gen", "asset_group"] },
    { key: "youtube_videos", label: "YouTube video links (optional)", kind: "list", min: 0, max: 5, formats: ["asset_group", "demand_gen"] },
    { key: "cta", label: "Call to action", kind: "select", options: ctas("LEARN_MORE", "SHOP_NOW", "SIGN_UP", "GET_QUOTE", "CONTACT_US", "BOOK_NOW", "DOWNLOAD"), formats: ["demand_gen"] },
    { ...URL_F, label: "Final URL" },
  ],
  youtube: [
    { key: "youtube_video", label: "YouTube video (link or ID; public or unlisted)", kind: "text", hint: "Shorts are vertical videos." },
    { key: "headline", label: "Headline", kind: "text" },
    { key: "long_headline", label: "Long headline", kind: "text", formats: ["in_feed", "shorts", "skippable_in_stream"] },
    { key: "description", label: "Description", kind: "text" },
    { key: "business_name", label: "Business name", kind: "text" },
    { key: "media", label: "Logo image (square, required by Google)", kind: "media" },
    { key: "cta", label: "Call to action", kind: "select", options: ctas("LEARN_MORE", "SHOP_NOW", "SIGN_UP", "SUBSCRIBE", "WATCH_MORE", "GET_QUOTE", "BOOK_NOW") },
    { ...URL_F, label: "Final URL" },
  ],
  linkedin: [
    { key: "intro_text", label: "Introductory text", kind: "textarea" },
    { key: "headline", label: "Headline", kind: "text" },
    { key: "description", label: "Description", kind: "text", formats: ["single_image", "video", "carousel", "text_ad"] },
    { key: "media", label: "Image, video or document", kind: "media", formats: ["single_image", "video", "carousel", "document"] },
    { key: "cta", label: "Call to action", kind: "select", options: ctas("LEARN_MORE", "SIGN_UP", "REGISTER", "DOWNLOAD", "APPLY", "SUBSCRIBE", "REQUEST_DEMO", "JOIN") },
    URL_F,
  ],
  x: [
    { key: "existing_post_id", label: "Promote an existing post (ID, optional)", kind: "text" },
    { key: "text", label: "Post text", kind: "textarea" },
    { key: "media", label: "Image or video", kind: "media", formats: ["image", "video", "website_card"] },
    { key: "card_headline", label: "Card headline", kind: "text", formats: ["website_card"] },
    { ...URL_F, formats: ["website_card"] },
  ],
  snapchat: [
    { key: "brand_name", label: "Brand name", kind: "text" },
    { key: "headline", label: "Headline", kind: "text" },
    { key: "media", label: "Vertical image or video (9:16)", kind: "media" },
    { key: "cta", label: "Call to action", kind: "select", options: ctas("MORE", "SHOP_NOW", "SIGN_UP", "INSTALL_NOW", "WATCH", "BOOK_NOW", "ORDER_NOW", "APPLY_NOW") },
    URL_F,
  ],
  pinterest: [
    { key: "existing_pin_id", label: "Pin ID to promote", kind: "text", formats: ["existing_pin"] },
    { key: "board_id", label: "Board ID for the new Pin", kind: "text", formats: ["image_pin", "video_pin"] },
    { key: "title", label: "Title", kind: "text", formats: ["image_pin", "video_pin"] },
    { key: "description", label: "Description", kind: "textarea", formats: ["image_pin", "video_pin"] },
    { key: "alt_text", label: "Alt text", kind: "text", formats: ["image_pin"] },
    // Pinterest has no standalone image upload: image Pins take a public URL.
    { key: "image_url", label: "Image URL (public https, 2:3 recommended)", kind: "url", formats: ["image_pin"] },
    { key: "media", label: "Video", kind: "media", formats: ["video_pin"] },
    URL_F,
  ],
};

export const FORMAT_LABEL: Record<string, string> = {
  single_video: "Single video", single_image: "Single image", spark_ad: "Spark Ad (boost a TikTok post)",
  responsive_search: "Responsive search ad", responsive_display: "Responsive display ad", demand_gen: "Demand Gen ad", asset_group: "Performance Max asset group",
  skippable_in_stream: "Skippable in-stream", in_feed: "In-feed video", shorts: "Shorts",
  video: "Video", carousel: "Carousel", text_ad: "Text ad", document: "Document",
  text: "Text", image: "Image", website_card: "Website card",
  image_pin: "Image Pin", video_pin: "Video Pin", existing_pin: "Existing Pin",
};

/** Formats offered for Google, narrowed by the campaign type. */
export function formatsFor(platform: Platform, campaignType: string | null): string[] {
  const all = platform.creative.formats ?? [];
  if (platform.key !== "google" || !campaignType) return all;
  const byType: Record<string, string[]> = { SEARCH: ["responsive_search"], PERFORMANCE_MAX: ["asset_group"], DISPLAY: ["responsive_display"], DEMAND_GEN: ["demand_gen"] };
  return byType[campaignType] ?? all;
}

export function visible(f: FieldSpec, values: Record<string, unknown>, format?: string): boolean {
  if (f.formats && (!format || !f.formats.includes(format))) return false;
  if (f.when) return f.when.in.includes(String(values[f.when.key] ?? ""));
  return true;
}

// ---------------------------------------------------------------------------
// Builder state
// ---------------------------------------------------------------------------
export type Selection = { level: Level; id: string };

type Ctx = {
  tree: PlatformTree;
  platform: Platform;
  selected: Selection;
  select: (s: Selection) => void;
  /** Runs a call that returns the new tree and stores it (all builder writes do). */
  run: (fn: () => Promise<PlatformTree>) => Promise<void>;
  busy: boolean;
  error: string | null;
  setDirty: (dirty: boolean) => void;
  editable: boolean;
};

const BuilderContext = createContext<Ctx | null>(null);

export function useBuilder(): Ctx {
  const ctx = useContext(BuilderContext);
  if (!ctx) throw new Error("useBuilder outside PlatformBuilderProvider");
  return ctx;
}

export function errorText(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 403) return "Only managers and above can edit campaigns.";
    const detail = (err.body as { detail?: unknown } | undefined)?.detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d: { msg?: string; loc?: unknown[] }) => `${(d.loc ?? []).slice(1).join(".")}: ${(d.msg ?? "").replace(/^Value error, /, "")}`)
        .join(" ");
    }
  }
  return err instanceof Error ? err.message : String(err);
}

export function PlatformBuilderProvider({ tree, platform, children }: { tree: PlatformTree; platform: Platform; children: ReactNode }) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<Selection>({ level: "campaign", id: tree.campaign.id });
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async (fn: () => Promise<PlatformTree>) => {
    setBusy(true);
    setError(null);
    try {
      const next = await fn();
      queryClient.setQueryData(adsKeys.tree(tree.campaign.id), next);
    } catch (err) {
      setError(errorText(err));
      void queryClient.invalidateQueries({ queryKey: adsKeys.tree(tree.campaign.id) });
    } finally {
      setBusy(false);
    }
  };
  // A removed node falls back to the campaign.
  useEffect(() => {
    const ids = new Set([tree.campaign.id, ...tree.groups.map((g) => g.id), ...tree.groups.flatMap((g) => g.ads.map((a) => a.id))]);
    if (!ids.has(selected.id)) setSelected({ level: "campaign", id: tree.campaign.id });
  }, [tree, selected.id]);
  const editable = tree.campaign.status === "draft" && !tree.campaign.pending_approval_id;
  return (
    <BuilderContext.Provider value={{ tree, platform, selected, select: setSelected, run, busy: busy || dirty, error, setDirty, editable }}>
      {children}
    </BuilderContext.Provider>
  );
}

/**
 * Debounced autosave: collects changes and PATCHes them together.
 * `pending()` returns edits not sent yet: a form that resyncs from a newer
 * tree re-applies them, so typing during a save isn't wiped out.
 */
export function useAutosave<T extends object>(
  save: (changes: Partial<T>) => Promise<PlatformTree>,
  resetKey: string,
): ((changes: Partial<T>) => void) & { pending: () => Partial<T> } {
  const { run, setDirty } = useBuilder();
  const pending = useRef<Partial<T>>({});
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const saveRef = useRef(save);
  saveRef.current = save;
  const flush = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    const changes = pending.current;
    pending.current = {};
    if (Object.keys(changes).length) void run(() => saveRef.current(changes)).finally(() => setDirty(false));
  };
  useEffect(() => () => flush(), [resetKey]);
  const queue = (changes: Partial<T>) => {
    // Nested settings (fields / targeting / creative) are merged key by key,
    // so two quick edits inside one object are both saved.
    const next: Record<string, unknown> = { ...pending.current };
    for (const [k, v] of Object.entries(changes)) {
      const prev = next[k];
      const isObj = (x: unknown) => typeof x === "object" && x !== null && !Array.isArray(x);
      next[k] = isObj(prev) && isObj(v) ? { ...(prev as object), ...(v as object) } : v;
    }
    pending.current = next as Partial<T>;
    setDirty(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(flush, 1000);
  };
  return Object.assign(queue, { pending: () => pending.current });
}

// ---------------------------------------------------------------------------
// Left tree: campaign -> groups -> ads, in the platform's own words.
// ---------------------------------------------------------------------------
function Dot({ show }: { show: boolean }) {
  return show ? <span className="ml-1 inline-block h-2 w-2 rounded-full bg-danger" aria-label="has issues" /> : null;
}

export default function PlatformTreeView() {
  const { tree, selected, select, run, editable } = useBuilder();
  const h = tree.hierarchy;
  const issueIds = new Set(tree.issues.map((i) => i.id));
  const act = useMutation({ mutationFn: (fn: () => Promise<PlatformTree>) => run(fn) });
  const item = (active: boolean) => `block w-full rounded px-2 py-1 text-left text-[13px] ${active ? "bg-accent-soft font-semibold" : "hover:bg-bg"}`;
  return (
    <nav className="card" aria-label="Campaign structure" style={{ padding: 10 }}>
      <button type="button" className={item(selected.level === "campaign")} onClick={() => select({ level: "campaign", id: tree.campaign.id })}>
        {h.campaign}: {tree.campaign.name}
        <Dot show={issueIds.has(tree.campaign.id)} />
      </button>
      {tree.groups.map((g) => (
        <div key={g.id} className="ml-2 mt-1 border-l border-border pl-2">
          <div className="flex items-center gap-1">
            <button type="button" className={item(selected.id === g.id)} onClick={() => select({ level: "group", id: g.id })}>
              {h.group}: {g.name}
              <Dot show={issueIds.has(g.id)} />
            </button>
            {editable && (
              <>
                <button type="button" className="text-xs text-muted" title={`Duplicate ${h.group.toLowerCase()}`} aria-label={`Duplicate ${g.name}`} onClick={() => act.mutate(() => duplicateGroup(g.id))}>
                  ⧉
                </button>
                {tree.groups.length > 1 && (
                  <button type="button" className="text-xs text-danger" title={`Delete ${h.group.toLowerCase()}`} aria-label={`Delete ${g.name}`} onClick={() => act.mutate(() => deleteGroup(g.id))}>
                    ✕
                  </button>
                )}
              </>
            )}
          </div>
          {g.ads.map((a) => (
            <div key={a.id} className="ml-3 flex items-center gap-1">
              <button type="button" className={item(selected.id === a.id)} onClick={() => select({ level: "ad", id: a.id })}>
                {a.name}
                <Dot show={issueIds.has(a.id)} />
              </button>
              {editable && (
                <>
                  <button type="button" className="text-xs text-muted" aria-label={`Duplicate ${a.name}`} onClick={() => act.mutate(() => duplicatePlatformAd(a.id))}>
                    ⧉
                  </button>
                  {g.ads.length > 1 && (
                    <button type="button" className="text-xs text-danger" aria-label={`Delete ${a.name}`} onClick={() => act.mutate(() => deletePlatformAd(a.id))}>
                      ✕
                    </button>
                  )}
                </>
              )}
            </div>
          ))}
          {editable && g.ads.length < 10 && (
            <button type="button" className="ml-3 mt-1 text-xs text-accent underline" onClick={() => act.mutate(() => addPlatformAd(g.id))}>
              + {h.ad}
            </button>
          )}
        </div>
      ))}
      {editable && tree.groups.length < 10 && (
        <button type="button" className="mt-2 text-xs text-accent underline" onClick={() => act.mutate(() => addGroup(tree.campaign.id))}>
          + {h.group}
        </button>
      )}
    </nav>
  );
}

// ---------------------------------------------------------------------------
// One input for any FieldSpec, with the platform's character limit counter.
// ---------------------------------------------------------------------------
type MediaRef = { media_id: string; kind: string; name: string };

function Counter({ value, limit }: { value: string; limit?: number }) {
  if (!limit) return null;
  const over = value.length > limit;
  return <span className={`ml-2 text-xs ${over ? "text-danger" : "text-muted"}`}>{value.length}/{limit}</span>;
}

export function FieldInput({ spec, value, onChange, idPrefix, disabled }: { spec: FieldSpec; value: unknown; onChange: (v: unknown) => void; idPrefix: string; disabled?: boolean }) {
  const { platform, tree } = useBuilder();
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const id = `${idPrefix}_${spec.key}`;
  const limit = platform.creative.text_limits?.[spec.key];
  const label = (
    <label htmlFor={id}>
      {spec.label}
      {typeof value === "string" && <Counter value={value} limit={limit} />}
    </label>
  );
  const hint = spec.hint ? <span className="text-xs text-muted">{spec.hint}</span> : null;
  switch (spec.kind) {
    case "checkbox":
      return (
        <label className="mb-3 flex items-center gap-2 text-[13px]">
          <input id={id} type="checkbox" checked={Boolean(value)} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
          {spec.label}
        </label>
      );
    case "select":
      return (
        <div className="form-row">
          {label}
          <select id={id} value={String(value ?? "")} disabled={disabled} onChange={(e) => onChange(e.target.value || null)}>
            <option value="">Choose…</option>
            {spec.options?.map((x) => (
              <option key={x.value} value={x.value}>
                {x.label}
              </option>
            ))}
          </select>
          {hint}
        </div>
      );
    case "multiselect": {
      const chosen = Array.isArray(value) ? (value as string[]) : [];
      return (
        <fieldset className="form-row">
          <legend className="text-xs font-semibold">{spec.label}</legend>
          {spec.options?.map((x) => (
            <label key={x.value} className="mr-3 inline-flex items-center gap-1 text-[13px]">
              <input
                type="checkbox"
                disabled={disabled}
                checked={chosen.includes(x.value)}
                onChange={(e) => onChange(e.target.checked ? [...chosen, x.value] : chosen.filter((c) => c !== x.value))}
              />
              {x.label}
            </label>
          ))}
        </fieldset>
      );
    }
    case "number":
      return (
        <div className="form-row">
          {label}
          <input id={id} type="number" min={0} step="0.01" disabled={disabled} value={value === null || value === undefined ? "" : String(value)} onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))} />
          {hint}
        </div>
      );
    case "textarea":
      return (
        <div className="form-row">
          {label}
          <textarea id={id} rows={3} disabled={disabled} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />
          {hint}
        </div>
      );
    case "list": {
      const items = Array.isArray(value) ? (value as string[]) : [];
      const rows = items.length ? items : [""];
      const max = spec.max ?? 15;
      return (
        <fieldset className="form-row">
          <legend className="text-xs font-semibold">
            {spec.label}{" "}
            <span className="font-normal text-muted">
              ({spec.min ?? 0}–{max}
              {limit ? `, up to ${limit} characters each` : ""})
            </span>
          </legend>
          {rows.map((v, i) => (
            <div key={i} className="mb-1 flex items-center gap-1">
              <input
                aria-label={`${spec.label} ${i + 1}`}
                disabled={disabled}
                value={v}
                onChange={(e) => onChange(rows.map((x, j) => (j === i ? e.target.value : x)))}
              />
              <Counter value={v} limit={limit} />
              {rows.length > 1 && !disabled && (
                <button type="button" className="text-xs text-danger" aria-label={`Remove ${spec.label} ${i + 1}`} onClick={() => onChange(rows.filter((_, j) => j !== i))}>
                  ✕
                </button>
              )}
            </div>
          ))}
          {!disabled && rows.length < max && (
            <button type="button" className="text-xs text-accent underline" onClick={() => onChange([...rows, ""])}>
              + Add
            </button>
          )}
        </fieldset>
      );
    }
    case "media": {
      const media = Array.isArray(value) ? (value as MediaRef[]) : [];
      const hints = Object.values(platform.creative.media ?? {}).join(" · ");
      return (
        <div className="form-row">
          <label htmlFor={id}>{spec.label}</label>
          {media.length > 0 && (
            <ul className="m-0 mb-1 pl-4 text-xs">
              {media.map((m) => (
                <li key={m.media_id}>
                  {m.kind}: {m.name}{" "}
                  {!disabled && (
                    <button type="button" className="text-danger" onClick={() => onChange(media.filter((x) => x.media_id !== m.media_id))}>
                      remove
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
          <input
            id={id}
            type="file"
            accept="image/*,video/*,application/pdf"
            disabled={disabled || uploading}
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (!file) return;
              setUploading(true);
              setUploadError(null);
              uploadPlatformMedia(tree.platform, file)
                .then((r) => onChange([...media, { media_id: r.media_id, kind: r.kind, name: r.name }]))
                .catch((err: unknown) => setUploadError(errorText(err)))
                .finally(() => setUploading(false));
            }}
          />
          {uploading && <span className="text-xs text-muted">Uploading to {platform.label}…</span>}
          {uploadError && <span className="text-xs text-danger">{uploadError}</span>}
          {hints && <span className="text-xs text-muted">{hints}</span>}
        </div>
      );
    }
    default:
      return (
        <div className="form-row">
          {label}
          <input id={id} type={spec.kind === "url" ? "url" : "text"} placeholder={spec.kind === "url" ? "https://" : undefined} disabled={disabled} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />
          {hint}
        </div>
      );
  }
}
