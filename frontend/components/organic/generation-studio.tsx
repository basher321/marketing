"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";

import {
  approveJob,
  cancelJob,
  editJob,
  fetchGenerationReadiness,
  fetchJobs,
  generatePhoto,
  generateVideo,
  generationKeys,
  isRunning,
  regenerateJob,
} from "@/lib/api/generation";
import { useCreatedItemTab } from "@/hooks/use-new-tab";
import { fetchProducts, productKeys } from "@/lib/api/products";
import type { GenerationJob, GenerationKind } from "@/lib/types/generation";
import { PLATFORM_LABEL, PLATFORMS, type SocialPlatform } from "@/lib/types/social";

import MediaPicker from "./media-picker";
import { StatusBadge, errorText } from "./shared";

const PHOTO_RATIOS = ["1:1", "4:5", "9:16", "16:9", "1.91:1"];
const VIDEO_RATIOS = ["9:16", "16:9", "1:1"];

function Elapsed({ since }: { since: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  const s = Math.max(0, Math.round((now - new Date(since).getTime()) / 1000));
  return <span>{s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${s}s`}</span>;
}

function JobCard({ job, kind }: { job: GenerationJob; kind: GenerationKind }) {
  const queryClient = useQueryClient();
  const [prompt, setPrompt] = useState(String(job.request.prompt ?? ""));
  const [editing, setEditing] = useState<"" | "prompt" | "image" | "post">("");
  const [instruction, setInstruction] = useState("");
  const [platforms, setPlatforms] = useState<SocialPlatform[]>(["instagram"]);
  const [caption, setCaption] = useState("");
  const done = () => void queryClient.invalidateQueries({ queryKey: ["generation"] });
  const regen = useMutation({ mutationFn: (changes: Record<string, unknown>) => regenerateJob(job.id, changes), onSuccess: () => { setEditing(""); done(); } });
  const edit = useMutation({ mutationFn: () => editJob(job.id, instruction), onSuccess: () => { setEditing(""); done(); } });
  const cancel = useMutation({ mutationFn: () => cancelJob(job.id), onSuccess: done });
  const newTab = useCreatedItemTab();
  const approve = useMutation({
    mutationFn: (withPost: boolean) =>
      approveJob(job.id, withPost ? { create_content: { caption: caption || null, targets: platforms.map((platform) => ({ platform })), adapt: "rules" } } : {}),
    onSuccess: (j) => {
      done();
      if (j.content_id) newTab.open(`/marketing/organic/content/${j.content_id}`); // SPEC-FE-058
    },
    onError: () => newTab.cancel(),
  });
  const err = regen.error ?? edit.error ?? cancel.error ?? approve.error;
  return (
    <div className="card" data-testid="job-card" style={{ padding: 12 }}>
      <div className="mb-2 flex flex-wrap items-center gap-2 text-[13px]">
        <StatusBadge status={job.status} />
        {isRunning(job) && (
          <span className="text-xs text-muted">
            generating… <Elapsed since={job.created_at} />
          </span>
        )}
        {job.provider && <span className="text-xs text-muted">{job.provider.replace("_", " ")} {job.model ? `· ${job.model}` : ""}</span>}
        {job.parent_job_id && <span className="text-xs text-muted">regenerated</span>}
        {job.approved_at && <span className="badge badge-success">approved</span>}
      </div>
      {job.media ? (
        kind === "video" ? (
          <video src={job.media.url} controls className="w-full rounded-md bg-bg" style={{ maxHeight: 420 }} />
        ) : (
          <img src={job.media.url} alt="" className="w-full rounded-md object-contain" style={{ maxHeight: 420 }} />
        )
      ) : (
        <div className="flex h-40 items-center justify-center rounded-md bg-bg text-xs text-muted">
          {isRunning(job) ? (kind === "video" ? "Video takes a minute or more…" : "Generating…") : job.error ?? job.status}
        </div>
      )}
      <p className="m-0 mt-2 line-clamp-2 text-xs text-muted" title={String(job.request.prompt ?? "")}>
        {String(job.request.edit_instruction ? `Edit: ${job.request.edit_instruction}` : job.request.prompt ?? "")}
      </p>
      {job.effective.duration_s !== undefined && (
        <p className="m-0 text-xs text-muted">
          {String(job.effective.duration_s)} s · {String(job.effective.aspect_ratio ?? "")}
        </p>
      )}
      {job.notes.map((n) => (
        <p key={n} className="m-0 text-xs text-warn">
          {n}
        </p>
      ))}
      {job.status === "failed" && job.error && <p className="m-0 text-xs text-danger">{job.error}</p>}
      <div className="mt-2 flex flex-wrap gap-1.5">
        {isRunning(job) && (
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => cancel.mutate()}>
            Cancel
          </button>
        )}
        {!isRunning(job) && (
          <>
            <button type="button" className="btn btn-secondary btn-sm" disabled={regen.isPending} onClick={() => regen.mutate({})}>
              Regenerate
            </button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditing(editing === "prompt" ? "" : "prompt")}>
              Edit prompt
            </button>
          </>
        )}
        {kind === "image" && job.status === "succeeded" && (
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditing(editing === "image" ? "" : "image")}>
            Edit image
          </button>
        )}
        {job.status === "succeeded" && (
          <>
            {!job.approved_at && (
              <button type="button" className="btn btn-secondary btn-sm" disabled={approve.isPending} onClick={() => approve.mutate(false)}>
                Approve
              </button>
            )}
            <button type="button" className="btn btn-sm" onClick={() => setEditing(editing === "post" ? "" : "post")}>
              {job.content_id ? "Create another post" : "Approve & create post"}
            </button>
            {job.content_id && (
              <Link className="btn btn-secondary btn-sm no-underline" href={`/marketing/organic/content/${job.content_id}`}>
                Open post
              </Link>
            )}
          </>
        )}
      </div>
      {editing === "prompt" && (
        <div className="mt-2">
          <textarea rows={3} className="w-full" value={prompt} onChange={(e) => setPrompt(e.target.value)} aria-label="New prompt" />
          <button type="button" className="btn btn-sm mt-1" disabled={prompt.trim().length < 3 || regen.isPending} onClick={() => regen.mutate({ prompt })}>
            Regenerate with this prompt
          </button>
        </div>
      )}
      {editing === "image" && (
        <div className="mt-2">
          <input className="w-full" value={instruction} onChange={(e) => setInstruction(e.target.value)} placeholder="e.g. make the background white" aria-label="Edit instruction" />
          <button type="button" className="btn btn-sm mt-1" disabled={instruction.trim().length < 3 || edit.isPending} onClick={() => edit.mutate()}>
            Apply edit
          </button>
        </div>
      )}
      {editing === "post" && (
        <div className="mt-2 text-[13px]">
          <div className="mb-1 flex flex-wrap gap-2">
            {PLATFORMS.map((p) => (
              <label key={p} className="flex items-center gap-1">
                <input type="checkbox" checked={platforms.includes(p)} onChange={(e) => setPlatforms((xs) => (e.target.checked ? [...xs, p] : xs.filter((x) => x !== p)))} />
                {PLATFORM_LABEL[p]}
              </label>
            ))}
          </div>
          <textarea rows={2} className="w-full" value={caption} onChange={(e) => setCaption(e.target.value)} placeholder="Caption (leave empty and AI writes it from the prompt)" aria-label="Caption" />
          <button type="button" className="btn btn-sm mt-1" disabled={platforms.length === 0 || approve.isPending} onClick={() => { newTab.begin(); approve.mutate(true); }}>
            {approve.isPending ? "Creating…" : "Approve & open the post editor"}
          </button>
        </div>
      )}
      {err && <p className="m-0 mt-2 text-xs text-danger">{errorText(err)}</p>}
    </div>
  );
}

/**
 * Photo / Video Generation (SPEC-FE-050 + SPEC-BE-077): prompt -> provider ->
 * preview -> regenerate / edit -> approve -> post. Jobs run on the backend;
 * this page only starts them and polls their status.
 */
export default function GenerationStudio({ kind }: { kind: GenerationKind }) {
  const queryClient = useQueryClient();
  const [prompt, setPrompt] = useState("");
  const [productIds, setProductIds] = useState<string[]>([]);
  const [refs, setRefs] = useState<string[]>([]);
  const [ratio, setRatio] = useState("");
  const [style, setStyle] = useState("");
  const [platform, setPlatform] = useState<SocialPlatform | "">("");
  const [count, setCount] = useState(1);
  const [duration, setDuration] = useState(8);
  const [negative, setNegative] = useState("");
  const readiness = useQuery({ queryKey: generationKeys.readiness, queryFn: fetchGenerationReadiness });
  const products = useQuery({ queryKey: productKeys.list, queryFn: fetchProducts });
  const jobs = useQuery({
    queryKey: generationKeys.list(kind),
    queryFn: () => fetchJobs(kind),
    refetchInterval: (q) => (q.state.data?.items.some(isRunning) ? (kind === "video" ? 10_000 : 3_000) : false),
  });
  const start = useMutation({
    mutationFn: () =>
      kind === "image"
        ? generatePhoto({ prompt, product_ids: productIds, reference_media_ids: refs, aspect_ratio: ratio || null, style: style || null, target_platform: platform || null, count })
        : generateVideo({
            prompt,
            product_ids: productIds,
            reference_media_ids: refs,
            aspect_ratio: (ratio || null) as "9:16" | "16:9" | "1:1" | null,
            duration_s: duration,
            style: style || null,
            negative_prompt: negative || null,
            target_platform: platform || null,
          }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: generationKeys.list(kind) }),
  });
  const providers = kind === "image" ? readiness.data?.image : readiness.data?.video;
  const ready = kind === "image" ? readiness.data?.image_ready : readiness.data?.video_ready;
  const refsSupported = (providers ?? []).some((p) => p.ready && p.reference_images);
  const ratios = kind === "image" ? PHOTO_RATIOS : VIDEO_RATIOS;
  return (
    <div className="grid gap-4 lg:grid-cols-[380px_1fr]">
      <div className="card self-start" data-testid="generation-form">
        {readiness.data && !ready && (
          <p className="m-0 mb-3 rounded-md bg-accent-soft p-2 text-xs">
            {readiness.data.setup_hint}{" "}
            <Link href="/integrations" className="underline">
              Open Integrations
            </Link>
          </p>
        )}
        <div className="form-row">
          <label htmlFor="g_prompt">Prompt</label>
          <textarea
            id="g_prompt"
            rows={4}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder={kind === "image" ? "Our linen shirt on a wooden table, soft morning light" : "Slow 360° turn of our linen shirt on a mannequin, studio light"}
          />
        </div>
        <div className="form-row">
          <label htmlFor="g_products">Product / service (optional)</label>
          <select id="g_products" multiple size={3} value={productIds} onChange={(e) => setProductIds(Array.from(e.target.selectedOptions).map((o) => o.value).slice(0, 5))}>
            {(products.data ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.title} ({p.sku})
              </option>
            ))}
          </select>
        </div>
        {refsSupported && (
          <div className="form-row">
            <label>Reference / product image (optional)</label>
            <MediaPicker value={refs} onChange={(ids) => setRefs(ids)} kind="image" max={3} />
          </div>
        )}
        <div className="form-grid-2">
          <div className="form-row">
            <label htmlFor="g_platform">For platform</label>
            <select id="g_platform" value={platform} onChange={(e) => setPlatform(e.target.value as SocialPlatform | "")}>
              <option value="">Any</option>
              {PLATFORMS.map((p) => (
                <option key={p} value={p}>
                  {PLATFORM_LABEL[p]}
                </option>
              ))}
            </select>
          </div>
          <div className="form-row">
            <label htmlFor="g_ratio">Aspect ratio</label>
            <select id="g_ratio" value={ratio} onChange={(e) => setRatio(e.target.value)}>
              <option value="">{platform ? `Best for ${PLATFORM_LABEL[platform]}` : "Default"}</option>
              {ratios.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="form-row">
          <label htmlFor="g_style">Style (optional)</label>
          <input id="g_style" value={style} onChange={(e) => setStyle(e.target.value)} placeholder="minimal, pastel, cinematic…" />
        </div>
        {kind === "video" ? (
          <>
            <div className="form-row">
              <label htmlFor="g_dur">Duration (seconds)</label>
              <input id="g_dur" type="number" min={2} max={60} value={duration} onChange={(e) => setDuration(Number(e.target.value))} />
              <p className="m-0 text-xs text-muted">
                {(providers ?? []).filter((p) => p.ready).map((p) => `${p.label}: ${p.durations.join(", ")} s`).join(" · ") ||
                  "Each provider makes short clips; the nearest supported length is used and shown."}
              </p>
            </div>
            <div className="form-row">
              <label htmlFor="g_neg">Avoid (optional)</label>
              <input id="g_neg" value={negative} onChange={(e) => setNegative(e.target.value)} placeholder="text overlays, blur" />
            </div>
          </>
        ) : (
          <div className="form-row">
            <label htmlFor="g_count">How many</label>
            <select id="g_count" value={count} onChange={(e) => setCount(Number(e.target.value))}>
              {[1, 2, 3, 4].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
        )}
        <button type="button" className="btn w-full" disabled={!ready || prompt.trim().length < 3 || start.isPending} onClick={() => start.mutate()}>
          {start.isPending ? "Starting…" : kind === "image" ? "Generate photo" : "Generate video"}
        </button>
        {start.isError && <p className="m-0 mt-2 text-xs text-danger" role="alert">{errorText(start.error)}</p>}
        {providers && (
          <p className="m-0 mt-2 text-[11px] text-muted">
            Providers, in your order: {providers.map((p) => `${p.label}${p.ready ? "" : " (not set up)"}`).join(" → ") || "none"}
          </p>
        )}
      </div>
      <div>
        {jobs.isPending ? (
          <p className="text-[13px] text-muted">Loading…</p>
        ) : jobs.isError ? (
          <p className="text-[13px] text-danger">{errorText(jobs.error)}</p>
        ) : jobs.data.items.length === 0 ? (
          <p className="card m-0 text-[13px] text-muted">Nothing generated yet.</p>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {jobs.data.items.map((j) => (
              <JobCard key={j.id} job={j} kind={kind} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
