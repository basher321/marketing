"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";

import { deriveMedia } from "@/lib/api/media";
import {
  approveContent,
  cancelPost,
  fetchContent,
  organicKeys,
  publishNow,
  regenerateVersion,
  reschedulePost,
  revertVersion,
  scheduleContent,
  setTargets,
  updateContent,
  updateVersion,
} from "@/lib/api/organic";
import type { DeriveRatio } from "@/lib/types/media";
import type { Content, CopyPart, PostFormat, Version } from "@/lib/types/organic";
import { PLATFORM_LABEL, PLATFORMS, type SocialPlatform } from "@/lib/types/social";

import MediaPicker, { MediaThumb } from "./media-picker";
import PlatformPreview from "./platform-preview";
import { StatusBadge, TimezoneField, addDays, errorText, postTime, useCompanyTimezone, ymdIn } from "./shared";

const FORMATS: Record<SocialPlatform, PostFormat[]> = {
  facebook: ["post", "carousel", "video", "reel"],
  instagram: ["post", "carousel", "reel", "story"],
  tiktok: ["video", "carousel"],
  linkedin: ["post", "carousel", "video"],
};
const CROPS: DeriveRatio[] = ["1:1", "4:5", "9:16", "1.91:1"];
const tags = (s: string) => s.split(/[\s,]+/).map((t) => t.replace(/^#/, "").trim()).filter(Boolean);

function useContentMutations(content: Content) {
  const queryClient = useQueryClient();
  const refresh = (c?: Content) => {
    if (c) queryClient.setQueryData(organicKeys.content(c.id), c);
    void queryClient.invalidateQueries({ queryKey: ["organic"] });
  };
  return { refresh, queryClient, id: content.id };
}

function MasterPanel({ content }: { content: Content }) {
  const { refresh } = useContentMutations(content);
  const [caption, setCaption] = useState(content.caption);
  const [hashtags, setHashtags] = useState(content.hashtags.join(" "));
  const [cta, setCta] = useState(content.cta ?? "");
  const [link, setLink] = useState(content.link_url ?? "");
  const [media, setMedia] = useState(content.media.map((m) => m.id));
  const save = useMutation({
    mutationFn: (readapt: boolean) =>
      updateContent(content.id, { caption, hashtags: tags(hashtags), cta: cta || null, link_url: link || null, media_ids: media, readapt }),
    onSuccess: refresh,
  });
  return (
    <section className="card mb-4" data-testid="master-panel">
      <h3 className="mt-0 text-[15px]">Master content</h3>
      <div className="form-row">
        <label htmlFor="m_caption">Caption</label>
        <textarea id="m_caption" rows={5} value={caption} onChange={(e) => setCaption(e.target.value)} />
      </div>
      <div className="form-grid-2">
        <div className="form-row">
          <label htmlFor="m_tags">Hashtags</label>
          <input id="m_tags" value={hashtags} onChange={(e) => setHashtags(e.target.value)} placeholder="summer sale newarrivals" />
        </div>
        <div className="form-row">
          <label htmlFor="m_cta">Call to action</label>
          <input id="m_cta" value={cta} onChange={(e) => setCta(e.target.value)} placeholder="Shop now" />
        </div>
      </div>
      <div className="form-row">
        <label htmlFor="m_link">Link (https)</label>
        <input id="m_link" value={link} onChange={(e) => setLink(e.target.value)} placeholder="https://…" />
      </div>
      <div className="form-row">
        <label>Media</label>
        <MediaPicker value={media} onChange={(ids) => setMedia(ids)} />
      </div>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn btn-secondary btn-sm" disabled={save.isPending} onClick={() => save.mutate(false)}>
          Save master
        </button>
        <button type="button" className="btn btn-sm" disabled={save.isPending} onClick={() => save.mutate(true)} title="Versions you edited by hand are kept">
          Save & re-adapt versions
        </button>
      </div>
      {save.isError && <p className="m-0 mt-2 text-xs text-danger">{errorText(save.error)}</p>}
    </section>
  );
}

function VersionEditor({ content, v, timezone }: { content: Content; v: Version; timezone: string }) {
  const { refresh } = useContentMutations(content);
  const [caption, setCaption] = useState(v.caption);
  const [hashtags, setHashtags] = useState(v.hashtags.join(" "));
  const [cta, setCta] = useState(v.cta ?? "");
  const [title, setTitle] = useState(v.title ?? "");
  const [parts, setParts] = useState<CopyPart[]>(["caption"]);
  const [instruction, setInstruction] = useState("");
  useEffect(() => {
    setCaption(v.caption);
    setHashtags(v.hashtags.join(" "));
    setCta(v.cta ?? "");
    setTitle(v.title ?? "");
  }, [v.caption, v.hashtags, v.cta, v.title, v.variant_index]);
  const save = useMutation({
    mutationFn: () => updateVersion(v.id, { caption, hashtags: tags(hashtags), cta: cta || null, title: title || null }),
    onSuccess: refresh,
  });
  const patch = useMutation({ mutationFn: (body: Parameters<typeof updateVersion>[1]) => updateVersion(v.id, body), onSuccess: refresh });
  const regen = useMutation({ mutationFn: () => regenerateVersion(v.id, parts, instruction), onSuccess: refresh });
  const revert = useMutation({ mutationFn: (i: number) => revertVersion(v.id, i), onSuccess: refresh });
  const crop = useMutation({
    mutationFn: async ({ mediaId, ratio }: { mediaId: string; ratio: DeriveRatio }) => {
      const child = await deriveMedia(mediaId, ratio, "crop");
      return updateVersion(v.id, { media_ids: v.media.map((m) => (m.id === mediaId ? child.id : m.id)) });
    },
    onSuccess: refresh,
  });
  const privacyOptions = ((v.account.extra?.privacy_level_options as string[] | undefined) ?? []).filter(Boolean);
  const locked = v.status === "published" || v.post?.status === "publishing";
  const busy = save.isPending || patch.isPending || regen.isPending || revert.isPending || crop.isPending;
  const err = save.error ?? patch.error ?? regen.error ?? revert.error ?? crop.error;
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
      <div>
        <div className="mb-2 flex flex-wrap items-center gap-2 text-[13px]">
          <StatusBadge status={v.status} />
          {v.edited && <span className="text-xs text-muted">edited by hand</span>}
          <span className="text-xs text-muted">
            Account: {v.account.account_name ?? "not connected"} ({(v.account.status ?? "not_connected").replace(/_/g, " ")})
          </span>
        </div>
        <fieldset disabled={locked || busy} className="m-0 border-0 p-0">
          <div className="form-row">
            <label htmlFor={`cap_${v.id}`}>Caption</label>
            <textarea id={`cap_${v.id}`} rows={6} value={caption} onChange={(e) => setCaption(e.target.value)} />
          </div>
          <div className="form-grid-2">
            <div className="form-row">
              <label htmlFor={`tag_${v.id}`}>Hashtags</label>
              <input id={`tag_${v.id}`} value={hashtags} onChange={(e) => setHashtags(e.target.value)} />
            </div>
            <div className="form-row">
              <label htmlFor={`cta_${v.id}`}>Call to action</label>
              <input id={`cta_${v.id}`} value={cta} onChange={(e) => setCta(e.target.value)} />
            </div>
          </div>
          {v.platform === "tiktok" && (
            <div className="form-row">
              <label htmlFor={`title_${v.id}`}>Title (photo posts, up to 90 characters)</label>
              <input id={`title_${v.id}`} maxLength={90} value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
          )}
          <div className="mb-3 flex flex-wrap gap-2">
            <button type="button" className="btn btn-sm" onClick={() => save.mutate()}>
              Save text
            </button>
            {v.variant_count > 1 && (
              <select
                aria-label="Earlier text"
                value={v.variant_index}
                onChange={(e) => revert.mutate(Number(e.target.value))}
                className="text-[13px]"
              >
                {Array.from({ length: v.variant_count }, (_, i) => (
                  <option key={i} value={i}>
                    Text version {i + 1}
                    {i === v.variant_index ? " (current)" : ""}
                  </option>
                ))}
              </select>
            )}
          </div>
          <div className="card mb-3" style={{ padding: 12 }}>
            <div className="mb-1 text-[13px] font-semibold">Regenerate with AI</div>
            <div className="mb-2 flex flex-wrap gap-3 text-[13px]">
              {(["caption", "hashtags", "cta", "title"] as CopyPart[]).map((p) => (
                <label key={p} className="flex items-center gap-1">
                  <input type="checkbox" checked={parts.includes(p)} onChange={(e) => setParts((xs) => (e.target.checked ? [...xs, p] : xs.filter((x) => x !== p)))} />
                  {p}
                </label>
              ))}
            </div>
            <input value={instruction} onChange={(e) => setInstruction(e.target.value)} placeholder="Optional: e.g. shorter, more playful" className="mb-2 w-full" />
            <button type="button" className="btn btn-secondary btn-sm" disabled={parts.length === 0} onClick={() => regen.mutate()}>
              {regen.isPending ? "Writing…" : "Regenerate"}
            </button>
            <span className="ml-2 text-xs text-muted">The image or video is never changed.</span>
          </div>
          <div className="form-grid-2">
            <div className="form-row">
              <label htmlFor={`fmt_${v.id}`}>Format</label>
              <select id={`fmt_${v.id}`} value={v.post_format} onChange={(e) => patch.mutate({ post_format: e.target.value as PostFormat })}>
                {FORMATS[v.platform].map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
            </div>
            {v.platform === "tiktok" && (
              <div className="form-row">
                <label htmlFor={`priv_${v.id}`}>Who can see it (required)</label>
                <select
                  id={`priv_${v.id}`}
                  value={String(v.platform_options.privacy_level ?? "")}
                  onChange={(e) => patch.mutate({ platform_options: { ...v.platform_options, privacy_level: e.target.value } })}
                >
                  <option value="">Choose…</option>
                  {privacyOptions.map((o) => (
                    <option key={o} value={o}>
                      {o.replace(/_/g, " ").toLowerCase()}
                    </option>
                  ))}
                </select>
                {privacyOptions.length === 0 && <p className="m-0 text-xs text-muted">Connect TikTok to load your account&apos;s options.</p>}
              </div>
            )}
          </div>
          <div className="form-row">
            <label>Media for {PLATFORM_LABEL[v.platform]}</label>
            <MediaPicker value={v.media.map((m) => m.id)} onChange={(ids) => patch.mutate({ media_ids: ids })} />
            {v.media
              .filter((m) => m.kind === "image")
              .map((m) => (
                <div key={m.id} className="mt-1 flex flex-wrap items-center gap-1 text-xs">
                  <MediaThumb item={m} size={32} />
                  <span className="text-muted">
                    {m.width}×{m.height} · crop to:
                  </span>
                  {CROPS.map((r) => (
                    <button key={r} type="button" className="btn btn-secondary btn-sm" onClick={() => crop.mutate({ mediaId: m.id, ratio: r })}>
                      {r}
                    </button>
                  ))}
                </div>
              ))}
          </div>
        </fieldset>
        {locked && <p className="text-xs text-muted">This version is published or publishing; it can&apos;t be edited.</p>}
        {err && <p className="m-0 text-xs text-danger">{errorText(err)}</p>}
        <PostStatusRow v={v} timezone={timezone} onChange={refresh} />
      </div>
      <PlatformPreview key={`${v.id}-${v.variant_index}-${v.media.map((m) => m.id).join()}-${v.caption.length}`} versionId={v.id} />
    </div>
  );
}

function PostStatusRow({ v, timezone, onChange }: { v: Version; timezone: string; onChange: () => void }) {
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const cancel = useMutation({ mutationFn: (id: string) => cancelPost(id), onSuccess: () => onChange() });
  const move = useMutation({ mutationFn: (id: string) => reschedulePost(id, `${date}T${time}`, timezone), onSuccess: () => onChange() });
  const p = v.post;
  if (!p) return null;
  return (
    <div className="card mt-3" style={{ padding: 12 }} data-testid="post-status">
      <div className="flex flex-wrap items-center gap-2 text-[13px]">
        <StatusBadge status={p.status} />
        <span>{p.status === "published" && p.published_at ? `Published ${new Date(p.published_at).toLocaleString()}` : postTime(p)}</span>
        {p.external_url && (
          <a href={p.external_url} target="_blank" rel="noreferrer" className="text-accent underline">
            Open on {PLATFORM_LABEL[p.platform]} ↗
          </a>
        )}
      </div>
      {p.error_message && <p className="m-0 mt-1 text-xs text-danger">{p.error_message}</p>}
      {(p.status === "scheduled" || p.status === "failed") && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <input type="date" aria-label="New date" value={date} onChange={(e) => setDate(e.target.value)} />
          <input type="time" aria-label="New time" value={time} onChange={(e) => setTime(e.target.value)} />
          <button type="button" className="btn btn-secondary btn-sm" disabled={!date || !time || move.isPending} onClick={() => move.mutate(p.id)}>
            Reschedule
          </button>
          {p.status === "scheduled" && (
            <button type="button" className="btn btn-secondary btn-sm" disabled={cancel.isPending} onClick={() => cancel.mutate(p.id)}>
              Cancel post
            </button>
          )}
        </div>
      )}
      {(cancel.error ?? move.error) && <p className="m-0 mt-1 text-xs text-danger">{errorText(cancel.error ?? move.error)}</p>}
    </div>
  );
}

function SchedulePanel({ content, timezone: companyTz }: { content: Content; timezone: string }) {
  const { refresh } = useContentMutations(content);
  const schedulable = content.versions.filter((v) => v.status !== "published" && !(v.post && ["scheduled", "publishing", "pending"].includes(v.post.status)));
  const [selected, setSelected] = useState<string[]>(schedulable.map((v) => v.id));
  const [tz, setTz] = useState(companyTz);
  const [date, setDate] = useState(addDays(ymdIn(companyTz), 1));
  const [time, setTime] = useState("10:00");
  const [perPlatform, setPerPlatform] = useState(false);
  const [times, setTimes] = useState<Record<string, string>>({});
  useEffect(() => setTz(companyTz), [companyTz]);
  const needsApproval = content.status === "needs_approval";
  const pending = content.media_pending.length > 0;
  const schedule = useMutation({
    mutationFn: () =>
      scheduleContent(
        content.id,
        selected.map((id) => ({ version_id: id, scheduled_at_local: `${date}T${(perPlatform && times[id]) || time}`, timezone: tz })),
      ),
    onSuccess: refresh,
  });
  const now = useMutation({
    mutationFn: async () => {
      for (const id of selected) await publishNow(id);
    },
    onSuccess: () => refresh(),
  });
  const blocked = needsApproval ? "Approve this AI-generated content first." : pending ? "Media is still being generated." : null;
  return (
    <section className="card mt-4" data-testid="schedule-panel">
      <h3 className="mt-0 text-[15px]">Schedule</h3>
      {schedulable.length === 0 ? (
        <p className="m-0 text-[13px] text-muted">Every version is already scheduled or published. Use the post controls above to move or cancel.</p>
      ) : (
        <>
          <div className="mb-2 flex flex-wrap gap-3 text-[13px]">
            {schedulable.map((v) => (
              <label key={v.id} className="flex items-center gap-1">
                <input type="checkbox" checked={selected.includes(v.id)} onChange={(e) => setSelected((s) => (e.target.checked ? [...s, v.id] : s.filter((x) => x !== v.id)))} />
                {PLATFORM_LABEL[v.platform]}
                {perPlatform && selected.includes(v.id) && (
                  <input type="time" aria-label={`${PLATFORM_LABEL[v.platform]} time`} value={times[v.id] ?? time} onChange={(e) => setTimes((t) => ({ ...t, [v.id]: e.target.value }))} />
                )}
              </label>
            ))}
          </div>
          <div className="form-grid-2">
            <div className="form-row">
              <label htmlFor="s_date">Date</label>
              <input id="s_date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </div>
            <div className="form-row">
              <label htmlFor="s_time">Time</label>
              <input id="s_time" type="time" value={time} onChange={(e) => setTime(e.target.value)} />
            </div>
          </div>
          <div className="form-row">
            <label htmlFor="s_tz">Timezone</label>
            <TimezoneField id="s_tz" value={tz} onChange={setTz} />
          </div>
          <label className="mb-3 flex items-center gap-1 text-[13px]">
            <input type="checkbox" checked={perPlatform} onChange={(e) => setPerPlatform(e.target.checked)} /> Different time per platform
          </label>
          {blocked && <p className="m-0 mb-2 text-xs text-warn">{blocked}</p>}
          <div className="flex flex-wrap gap-2">
            <span className="mr-auto self-center text-xs text-muted">Drafts are saved automatically.</span>
            <button type="button" className="btn btn-sm" disabled={!!blocked || selected.length === 0 || schedule.isPending} onClick={() => schedule.mutate()} title={blocked ?? undefined}>
              {schedule.isPending ? "Scheduling…" : "Schedule"}
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={!!blocked || selected.length === 0 || now.isPending}
              title={blocked ?? undefined}
              onClick={() => {
                if (window.confirm(`Publish to ${selected.length} platform(s) now?`)) now.mutate();
              }}
            >
              {now.isPending ? "Publishing…" : "Publish now"}
            </button>
          </div>
        </>
      )}
      {(schedule.error ?? now.error) && <p className="m-0 mt-2 text-xs text-danger" role="alert">{errorText(schedule.error ?? now.error)}</p>}
    </section>
  );
}

function TargetsBar({ content }: { content: Content }) {
  const { refresh } = useContentMutations(content);
  const have = content.versions.map((v) => v.platform);
  const change = useMutation({
    mutationFn: ({ add, remove }: { add: SocialPlatform[]; remove: SocialPlatform[] }) => setTargets(content.id, add.map((platform) => ({ platform })), remove),
    onSuccess: refresh,
  });
  return (
    <div className="flex flex-wrap items-center gap-2 text-[13px]">
      {PLATFORMS.filter((p) => !have.includes(p)).map((p) => (
        <button key={p} type="button" className="btn btn-secondary btn-sm" disabled={change.isPending} onClick={() => change.mutate({ add: [p], remove: [] })}>
          + {PLATFORM_LABEL[p]}
        </button>
      ))}
      {change.isError && <span className="text-xs text-danger">{errorText(change.error)}</span>}
    </div>
  );
}

export default function ContentEditor({ id }: { id: string }) {
  const timezone = useCompanyTimezone();
  const query = useQuery({
    queryKey: organicKeys.content(id),
    queryFn: () => fetchContent(id),
    // Generated media arrives in the background: poll while it's pending.
    refetchInterval: (q) => (q.state.data && q.state.data.media_pending.length > 0 ? 5000 : false),
  });
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<string | null>(null);
  const approve = useMutation({
    mutationFn: () => approveContent(id),
    onSuccess: (c) => {
      queryClient.setQueryData(organicKeys.content(id), c);
      void queryClient.invalidateQueries({ queryKey: ["organic"] });
    },
  });
  if (query.isPending) return <p className="text-[13px] text-muted">Loading…</p>;
  if (query.isError) return <p className="text-[13px] text-danger">{errorText(query.error)}</p>;
  const content = query.data;
  const current = content.versions.find((v) => v.id === tab) ?? content.versions[0];
  return (
    <div data-testid="content-editor">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <h2 className="m-0 text-[18px]">{content.title || "Untitled post"}</h2>
        <StatusBadge status={content.status} />
        <span className="badge badge-neutral">{content.mode === "ai" ? "AI" : "Manual"}</span>
        {content.status === "needs_approval" && (
          <button type="button" className="btn btn-sm" disabled={approve.isPending} onClick={() => approve.mutate()} data-testid="approve">
            {approve.isPending ? "Approving…" : "Approve"}
          </button>
        )}
        {approve.isError && <span className="text-xs text-danger">{errorText(approve.error)}</span>}
        <Link href="/marketing/organic" className="ml-auto text-xs text-muted underline">
          ← Back
        </Link>
      </div>
      {content.prompt && <p className="m-0 mb-2 text-xs text-muted">Prompt: {content.prompt}</p>}
      {content.performance_used && <p className="m-0 mb-2 text-xs text-muted">Written with your recent results in mind.</p>}
      {content.media_pending.length > 0 && <p className="m-0 mb-2 text-xs text-warn">Generating media… this page updates when it&apos;s ready.</p>}
      {content.warnings.map((w) => (
        <p key={w} className="m-0 mb-2 text-xs text-warn">
          {w}
        </p>
      ))}
      <MasterPanel key={content.updated_at} content={content} />
      <section className="card">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="tabs m-0" role="tablist">
            {content.versions.map((v) => (
              <button key={v.id} type="button" role="tab" aria-selected={current?.id === v.id} className={current?.id === v.id ? "tab active" : "tab"} onClick={() => setTab(v.id)}>
                {PLATFORM_LABEL[v.platform]}
                {v.warnings.length > 0 ? " ⚠" : ""}
              </button>
            ))}
          </div>
          <TargetsBar content={content} />
        </div>
        {current ? <VersionEditor key={current.id} content={content} v={current} timezone={timezone} /> : <p className="text-[13px] text-muted">Add a platform.</p>}
      </section>
      <SchedulePanel key={`${content.id}-${content.versions.map((v) => v.post?.id ?? v.id).join()}`} content={content} timezone={timezone} />
    </div>
  );
}
