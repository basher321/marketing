"use client";

import { useInfiniteQuery, useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { createPost, fetchLeadForms, fetchPosts, fetchProductSets, metaKeys, updateAd } from "@/lib/api/meta";
import type { AdFields, BuilderAd, BuilderAdSet, Card, Destination, ExistingPost, MediaResult } from "@/lib/types/meta";

import MediaUploader from "./media-uploader";
import { errorText, FieldIssues, useAutosave, useBuilder } from "./tree";

// Meta's recommended lengths (text beyond them may be truncated in placements).
const LIMITS = { primary_text: 125, headline: 40, description: 30 } as const;

function Counter({ value, limit }: { value: string; limit: number }) {
  return <span className={`text-[11px] ${value.length > limit ? "text-warn" : "text-muted"}`}>{value.length}/{limit} recommended</span>;
}

function buildUtm(campaign: string): string {
  return `utm_source=facebook&utm_medium=paid&utm_campaign=${encodeURIComponent(campaign.toLowerCase().replace(/\s+/g, "_"))}&utm_content={{ad.name}}`;
}

// "Ad setup" (SPEC-FE-053): the three Ads Manager formats. "Single" is stored as
// format image or video, picked from the uploaded file's type.
type SetupKind = "single" | "carousel" | "existing_post";
const SETUP: { key: SetupKind; title: string; hint: string }[] = [
  { key: "single", title: "Single image or video", hint: "One image or one video" },
  { key: "carousel", title: "Carousel", hint: "2 to 10 scrollable images or videos" },
  { key: "existing_post", title: "Use existing post", hint: "A post from your Facebook Page or Instagram" },
];

function Choice({ name, checked, disabled, onSelect, title, hint }: { name: string; checked: boolean; disabled: boolean; onSelect: () => void; title: string; hint?: string }) {
  return (
    <label className={`flex cursor-pointer items-start gap-2 rounded-md border p-3 text-[13px] ${checked ? "border-accent bg-accent-soft" : "border-border"} ${disabled ? "opacity-60" : ""}`}>
      <input type="radio" name={name} className="mt-0.5" checked={checked} disabled={disabled} onChange={onSelect} />
      <span>
        <b>{title}</b>
        {hint && <span className="block text-xs text-muted">{hint}</span>}
      </span>
    </label>
  );
}

// Graph sends "+0000" offsets, which not every browser's Date parses.
function postDate(value?: string | null): string {
  if (!value) return "";
  const d = new Date(value.replace(/([+-]\d{2})(\d{2})$/, "$1:$2"));
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString();
}

function PostRow({ post, selected, onClick }: { post: ExistingPost; selected?: boolean; onClick?: () => void }) {
  const body = (
    <>
      {post.picture ? <img src={post.picture} alt="" className="h-12 w-12 shrink-0 rounded object-cover" /> : <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded bg-bg text-[11px] text-muted">text</span>}
      <span className="min-w-0 flex-1">
        <span className="line-clamp-2 block">{post.message || <em className="text-muted">(no text)</em>}</span>
        <span className="text-xs text-muted">
          {post.platform === "instagram" ? "Instagram" : "Facebook"}
          {postDate(post.created_time) && ` · ${postDate(post.created_time)}`}
        </span>
      </span>
    </>
  );
  return (
    <div className={`flex items-center gap-2 rounded-md border p-2 text-[13px] ${selected ? "border-accent bg-accent-soft" : "border-border"}`}>
      {onClick ? (
        <button type="button" className="flex min-w-0 flex-1 items-center gap-2 text-left" onClick={onClick}>
          {body}
        </button>
      ) : (
        <span className="flex min-w-0 flex-1 items-center gap-2">{body}</span>
      )}
      {post.permalink_url && (
        <a href={post.permalink_url} target="_blank" rel="noreferrer" className="text-xs text-accent">
          View post
        </a>
      )}
    </div>
  );
}

// "Use existing post": pick a Facebook/Instagram post, or publish a new Page post and use it.
function PostPicker({ value, disabled, onPick }: { value: ExistingPost | null; disabled: boolean; onPick: (post: ExistingPost) => void }) {
  const [changing, setChanging] = useState(!value);
  const [mode, setMode] = useState<"select" | "create">("select");
  const [platform, setPlatform] = useState<ExistingPost["platform"]>("facebook");
  const [draft, setDraft] = useState({ message: "", link: "", image_url: "" });
  const open = changing || !value;
  const posts = useInfiniteQuery({
    queryKey: [...metaKeys.lookup("posts", platform)],
    queryFn: ({ pageParam }) => fetchPosts(platform, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    enabled: open && mode === "select" && !disabled,
    retry: false,
  });
  const create = useMutation({
    mutationFn: createPost,
    onSuccess: (post) => {
      setDraft({ message: "", link: "", image_url: "" });
      pick(post);
      void posts.refetch();
    },
  });
  const pick = (post: ExistingPost) => {
    onPick(post);
    setChanging(false);
  };

  if (!open && value) {
    return (
      <div className="grid gap-2">
        <PostRow post={value} selected />
        <div>
          <button type="button" className="btn btn-secondary btn-sm" disabled={disabled} onClick={() => setChanging(true)}>
            Change
          </button>
        </div>
      </div>
    );
  }
  const items = posts.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <div className="grid gap-3">
      <div className="grid gap-2 sm:grid-cols-2">
        <Choice name="post_mode" checked={mode === "select"} disabled={disabled} onSelect={() => setMode("select")} title="Select post" />
        <Choice name="post_mode" checked={mode === "create"} disabled={disabled} onSelect={() => setMode("create")} title="Create post" />
      </div>
      {mode === "select" ? (
        <div className="grid gap-2">
          <div className="flex gap-2">
            {(["facebook", "instagram"] as const).map((p) => (
              <button key={p} type="button" className={`btn btn-sm ${platform === p ? "" : "btn-secondary"}`} onClick={() => setPlatform(p)}>
                {p === "facebook" ? "Facebook" : "Instagram"}
              </button>
            ))}
          </div>
          {posts.isPending && !disabled && <p className="m-0 text-xs text-muted">Loading posts…</p>}
          {posts.isError && (
            <p className="m-0 text-xs text-danger" role="alert">
              {errorText(posts.error)}
            </p>
          )}
          {posts.isSuccess && !items.length && <p className="m-0 text-xs text-muted">No posts found on this account.</p>}
          {items.map((post) => (
            <PostRow key={post.id} post={post} selected={value?.id === post.id} onClick={disabled ? undefined : () => pick(post)} />
          ))}
          {posts.hasNextPage && (
            <div>
              <button type="button" className="btn btn-secondary btn-sm" disabled={posts.isFetchingNextPage} onClick={() => void posts.fetchNextPage()}>
                {posts.isFetchingNextPage ? "Loading…" : "Load more"}
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className="grid gap-2">
          <p className="m-0 text-xs text-muted">This post will be published on your Facebook Page, then used as the ad.</p>
          <div className="form-row">
            <label htmlFor="post_message">Post text</label>
            <textarea id="post_message" rows={3} disabled={disabled} value={draft.message} onChange={(e) => setDraft({ ...draft, message: e.target.value })} />
          </div>
          <div className="form-row">
            <label htmlFor="post_link">Link (optional)</label>
            <input id="post_link" disabled={disabled || Boolean(draft.image_url)} placeholder="https://" value={draft.link} onChange={(e) => setDraft({ ...draft, link: e.target.value })} />
          </div>
          <div className="form-row">
            <label>Image (optional)</label>
            {draft.image_url && (
              <div className="mb-2 flex items-center gap-2 text-[13px]">
                <img src={draft.image_url} alt="" className="h-16 w-16 rounded object-cover" />
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => setDraft({ ...draft, image_url: "" })}>
                  Remove
                </button>
              </div>
            )}
            <MediaUploader accept="image" disabled={disabled} label="Drop a JPG/PNG image (a photo post can't also carry a link)" onUploaded={(m) => m.thumbnail_url && setDraft({ ...draft, link: "", image_url: m.thumbnail_url })} />
          </div>
          {create.isError && (
            <p className="m-0 text-xs text-danger" role="alert">
              {errorText(create.error)}
            </p>
          )}
          <div>
            <button
              type="button"
              className="btn btn-sm"
              disabled={disabled || !draft.message.trim() || create.isPending}
              onClick={() => create.mutate({ message: draft.message.trim(), link: draft.link.trim() || null, image_url: draft.image_url || null })}
            >
              {create.isPending ? "Publishing…" : "Create post"}
            </button>
          </div>
        </div>
      )}
      {value && (
        <div>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setChanging(false)}>
            Keep the current post
          </button>
        </div>
      )}
    </div>
  );
}

// Ad level (SPEC-FE-039): identity, ad setup (format + media), text, CTA,
// destination, URL parameters (tracking), and AI copy import.
export default function AdForm({ ad, adSet }: { ad: BuilderAd; adSet: BuilderAdSet }) {
  const { tree, objectives, editable } = useBuilder();
  const published = Boolean(ad.external_ad_id);
  const [f, setF] = useState(ad);
  const save = useAutosave<AdFields>((changes) => updateAd(ad.id, changes), ad.id);
  // A newer tree from the server, plus any edits not sent yet.
  useEffect(() => setF({ ...ad, ...save.pending() } as BuilderAd), [ad]);
  const set = (changes: AdFields) => {
    setF((cur) => ({ ...cur, ...changes }) as BuilderAd);
    save(changes);
  };
  const instantForm = adSet.conversion_location === "instant_form";
  const appDest = adSet.conversion_location === "app" || tree.campaign.objective === "app_promotion";
  const forms = useQuery({ queryKey: metaKeys.lookup("lead-forms"), queryFn: fetchLeadForms, enabled: instantForm, retry: false });
  const conn = objectives?.connection;
  const draftOnly = !editable || published;
  const setDest = (patch: Partial<Destination>) => set({ destination: { ...f.destination, ...patch } });
  const setCard = (i: number, patch: Partial<Card>) => set({ cards: f.cards.map((c, j) => (j === i ? { ...c, ...patch } : c)) });

  const kind: SetupKind = f.format === "carousel" ? "carousel" : f.format === "existing_post" ? "existing_post" : "single";
  const isPost = f.format === "existing_post";
  const fromProductSet = f.format === "carousel" && f.carousel_source === "product_set";
  const sets = useQuery({ queryKey: metaKeys.lookup("product-sets"), queryFn: fetchProductSets, enabled: fromProductSet, retry: false });
  // Each format keeps its own data on the ad, so switching back loses nothing.
  const choose = (k: SetupKind) => set({ format: k === "single" ? (f.media[0]?.type ?? "image") : k });
  // MediaUploader reports a video twice (uploaded, then processed): update that card, don't add another.
  const addCard = (m: MediaResult) => {
    const at = m.video_id ? f.cards.findIndex((c) => c.video_id === m.video_id) : -1;
    if (at >= 0) return setCard(at, { thumbnail_url: m.thumbnail_url, status: m.status });
    const base = { thumbnail_url: m.thumbnail_url, headline: "", description: "", link: null };
    if (m.type === "video" && m.video_id) set({ cards: [...f.cards, { ...base, type: "video", video_id: m.video_id, status: m.status }] });
    else if (m.image_hash) set({ cards: [...f.cards, { ...base, type: "image", image_hash: m.image_hash }] });
  };
  const single = f.media[0];

  return (
    <div className="grid gap-4">
      <div className="card">
        <h3 className="mt-0">Ad</h3>
        <div className="form-row">
          <label htmlFor="ad_name">Ad name</label>
          <input id="ad_name" disabled={!editable} value={f.name} onChange={(e) => set({ name: e.target.value })} />
        </div>
        {(f.last_error || f.review_feedback) && (
          <p className="text-xs text-danger">
            {f.last_error}
            {f.review_feedback && !f.last_error && JSON.stringify(f.review_feedback)}
          </p>
        )}
        <div className="form-row">
          <label>Identity</label>
          <span className="text-[13px]">
            Facebook Page: <b>{conn?.page_id ?? "not connected"}</b>
            {conn?.instagram_id && (
              <>
                {" "}· Instagram account: <b>{conn.instagram_id}</b>
              </>
            )}
          </span>
          <label className="flex items-center gap-2 text-[13px]">
            <input type="checkbox" disabled={draftOnly} checked={f.use_instagram} onChange={(e) => set({ use_instagram: e.target.checked })} />
            Use the Instagram account for Instagram placements
          </label>
          <FieldIssues level="ad" id={ad.id} field="identity" />
        </div>
      </div>

      <div className="card">
        <h3 className="mt-0">Ad setup</h3>
        <div className="form-row">
          <label>Format</label>
          <div className="grid gap-2 sm:grid-cols-3" role="radiogroup" aria-label="Ad format">
            {SETUP.map((o) => (
              <Choice key={o.key} name={`setup_${ad.id}`} checked={kind === o.key} disabled={draftOnly} onSelect={() => choose(o.key)} title={o.title} hint={o.hint} />
            ))}
          </div>
        </div>

        {kind === "single" && (
          <div className="form-row">
            <label>Image or video</label>
            {single && (
              <div className="mb-2 flex items-center gap-2 text-[13px]">
                {single.thumbnail_url && <img src={single.thumbnail_url} alt="" className="h-16 w-16 rounded object-cover" />}
                <span>
                  {single.type === "video" ? "Video" : "Image"}: {single.name || single.type} {single.status && single.status !== "ready" && <em className="text-muted">({single.status})</em>}
                </span>
              </div>
            )}
            <MediaUploader
              accept="both"
              disabled={draftOnly}
              label={`${single ? "Replace: drop" : "Drop"} a JPG/PNG image (up to 30 MB) or an MP4/MOV video (up to 1 GB), or click to choose`}
              // The "processed" report for a video has no file name: keep the uploaded one.
              onUploaded={(m) => set({ format: m.type, media: [{ type: m.type, image_hash: m.image_hash, video_id: m.video_id, thumbnail_url: m.thumbnail_url, name: m.name || (m.video_id && single?.video_id === m.video_id ? single.name : ""), status: m.status }] })}
            />
            <FieldIssues level="ad" id={ad.id} field="media" />
          </div>
        )}

        {kind === "carousel" && (
          <>
            <div className="form-row">
              <label>Cards</label>
              <div className="grid gap-2 sm:grid-cols-2">
                <Choice name={`carousel_${ad.id}`} checked={!fromProductSet} disabled={draftOnly} onSelect={() => set({ carousel_source: "manual" })} title="Choose images, videos and links manually" />
                <Choice
                  name={`carousel_${ad.id}`}
                  checked={fromProductSet}
                  disabled={draftOnly}
                  onSelect={() => set({ carousel_source: "product_set" })}
                  title="Fill carousel cards dynamically from a product set"
                  hint="Needs a Sales campaign and a Meta catalog"
                />
              </div>
            </div>
            {fromProductSet ? (
              <div className="form-row">
                <label htmlFor="ad_product_set">Product set</label>
                <select
                  id="ad_product_set"
                  disabled={draftOnly}
                  value={f.product_set?.id ?? ""}
                  onChange={(e) => set({ product_set: sets.data?.find((p) => p.id === e.target.value) ?? null })}
                >
                  <option value="">{sets.isPending ? "Loading product sets…" : "Choose a product set…"}</option>
                  {f.product_set && !sets.data?.some((p) => p.id === f.product_set?.id) && <option value={f.product_set.id}>{f.product_set.name}</option>}
                  {sets.data?.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} — {p.catalog_name}
                      {p.product_count != null ? ` (${p.product_count} products)` : ""}
                    </option>
                  ))}
                </select>
                {sets.isError && <span className="text-xs text-danger">{errorText(sets.error)}</span>}
                {sets.isSuccess && !sets.data.length && <span className="text-xs text-muted">No product sets found. Create a catalog and a product set in Meta Commerce Manager first.</span>}
                <span className="text-xs text-muted">Meta builds one card per product, with the product&apos;s image, name and price from the catalog.</span>
                <FieldIssues level="ad" id={ad.id} field="product_set" />
              </div>
            ) : (
              <div className="form-row">
                {f.cards.map((card, i) => (
                  // Thumbnail | stacked fields | remove: three inputs side by side don't fit the builder's middle column.
                  <div key={i} className="mb-2 grid grid-cols-[64px_minmax(0,1fr)_auto] items-start gap-2 rounded-md border border-border p-2">
                    <span className="relative">
                      {card.thumbnail_url ? <img src={card.thumbnail_url} alt="" className="h-16 w-16 rounded object-cover" /> : <span className="text-xs text-muted">{card.type}</span>}
                      <span className="text-[11px] text-muted">
                        {card.type === "video" ? "Video" : "Image"}
                        {card.status && card.status !== "ready" && ` (${card.status})`}
                      </span>
                    </span>
                    <span className="grid min-w-0 gap-2">
                      <input className="min-w-0" aria-label={`Card ${i + 1} headline`} disabled={draftOnly} placeholder="Headline" value={card.headline} onChange={(e) => setCard(i, { headline: e.target.value })} />
                      <input className="min-w-0" aria-label={`Card ${i + 1} description`} disabled={draftOnly} placeholder="Description" value={card.description} onChange={(e) => setCard(i, { description: e.target.value })} />
                      <input className="min-w-0" aria-label={`Card ${i + 1} link`} disabled={draftOnly} placeholder="https:// (optional)" value={card.link ?? ""} onChange={(e) => setCard(i, { link: e.target.value || null })} />
                    </span>
                    <button type="button" className="btn btn-secondary btn-sm" aria-label={`Remove card ${i + 1}`} disabled={draftOnly} onClick={() => set({ cards: f.cards.filter((_, j) => j !== i) })}>
                      ✕
                    </button>
                  </div>
                ))}
                {f.cards.length < 10 && <MediaUploader accept="both" disabled={draftOnly} label="Add a card: drop a JPG/PNG image or an MP4/MOV video" onUploaded={addCard} />}
                <FieldIssues level="ad" id={ad.id} field="cards" />
              </div>
            )}
          </>
        )}

        {kind === "existing_post" && (
          <div className="form-row">
            <label>Post</label>
            <PostPicker value={f.existing_post} disabled={draftOnly} onPick={(post) => set({ existing_post: post })} />
            <span className="text-xs text-muted">Text, media and button come from the post.</span>
            <FieldIssues level="ad" id={ad.id} field="existing_post" />
          </div>
        )}

        {!isPost && (
          <>
            <div className="form-row">
              <label htmlFor="ad_text">Primary text</label>
              <textarea id="ad_text" rows={3} disabled={!editable} value={f.primary_text} onChange={(e) => set({ primary_text: e.target.value })} />
              <Counter value={f.primary_text} limit={LIMITS.primary_text} />
              <FieldIssues level="ad" id={ad.id} field="primary_text" />
            </div>
            {f.format !== "carousel" && (
              <div className="grid gap-x-4 sm:grid-cols-2">
                <div className="form-row">
                  <label htmlFor="ad_head">Headline</label>
                  <input id="ad_head" disabled={!editable} value={f.headline} onChange={(e) => set({ headline: e.target.value })} />
                  <Counter value={f.headline} limit={LIMITS.headline} />
                  <FieldIssues level="ad" id={ad.id} field="headline" />
                </div>
                <div className="form-row">
                  <label htmlFor="ad_desc">Description (optional)</label>
                  <input id="ad_desc" disabled={!editable} value={f.description} onChange={(e) => set({ description: e.target.value })} />
                  <Counter value={f.description} limit={LIMITS.description} />
                </div>
              </div>
            )}
            <div className="form-row">
              <label htmlFor="ad_cta">Call to action</label>
              <select id="ad_cta" disabled={!editable} value={f.call_to_action} onChange={(e) => set({ call_to_action: e.target.value })}>
                {(objectives?.calls_to_action ?? [f.call_to_action]).map((cta) => (
                  <option key={cta} value={cta}>
                    {cta.replace(/_/g, " ").toLowerCase()}
                  </option>
                ))}
              </select>
            </div>
          </>
        )}
      </div>

      <div className="card">
        <h3 className="mt-0">Destination &amp; tracking</h3>
        {isPost ? (
          <p className="text-[13px] text-muted">People go where the post&apos;s own link or button sends them.</p>
        ) : instantForm ? (
          <div className="form-row">
            <label htmlFor="ad_form">Instant form</label>
            <select id="ad_form" disabled={draftOnly} value={f.destination.lead_form_id ?? ""} onChange={(e) => setDest({ type: "instant_form", lead_form_id: e.target.value || null })}>
              <option value="">Choose a form…</option>
              {forms.data?.map((form) => (
                <option key={form.id} value={form.id}>
                  {form.name}
                </option>
              ))}
            </select>
            {forms.isError && <span className="text-xs text-danger">{forms.error.message}</span>}
            <FieldIssues level="ad" id={ad.id} field="destination" />
          </div>
        ) : appDest ? (
          <p className="text-[13px] text-muted">People go to the app store link set on the ad set ({adSet.app_store_url ?? "not set"}).</p>
        ) : (
          <div className="form-row">
            <label htmlFor="ad_url">Website URL</label>
            <input id="ad_url" disabled={draftOnly} placeholder="https://your-store.com/product" value={f.destination.url ?? ""} onChange={(e) => setDest({ type: "website", url: e.target.value || null })} />
            <FieldIssues level="ad" id={ad.id} field="destination" />
          </div>
        )}
        <div className="form-row">
          <label htmlFor="ad_utm">URL parameters</label>
          <div className="flex gap-2">
            <input id="ad_utm" disabled={draftOnly} value={f.url_tags} onChange={(e) => set({ url_tags: e.target.value })} />
            <button type="button" className="btn btn-secondary btn-sm" disabled={draftOnly} onClick={() => set({ url_tags: buildUtm(tree.campaign.name) })}>
              Build UTM
            </button>
          </div>
          <span className="text-xs text-muted">Added to the link so your analytics can attribute visits (Meta fills {"{{ad.name}}"}).</span>
        </div>
        {adSet.pixel_id || objectives?.connection.pixel_id ? (
          <p className="m-0 text-xs text-muted">Conversions are tracked with pixel {adSet.pixel_id ?? objectives?.connection.pixel_id} (set on the ad set).</p>
        ) : null}
      </div>
      {published && <p className="m-0 text-xs text-muted">Published: changing the text or call to action creates a new creative on Meta, and Meta reviews the ad again.</p>}
    </div>
  );
}
