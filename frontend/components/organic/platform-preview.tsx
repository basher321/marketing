"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchPreview, organicKeys } from "@/lib/api/organic";
import type { Preview } from "@/lib/types/organic";
import { PLATFORM_LABEL } from "@/lib/types/social";

import { errorText } from "./shared";

// A mock-up of the post as it will look on each platform (SPEC-FE-050). The
// text is the backend's composed text - exactly what is sent - and the
// "…more" cut-off approximates where the feed truncates it.
const FRAME: Record<string, { ratio: string; tone: string }> = {
  facebook: { ratio: "aspect-[4/5]", tone: "Facebook feed" },
  instagram: { ratio: "aspect-[4/5]", tone: "Instagram feed" },
  tiktok: { ratio: "aspect-[9/16]", tone: "TikTok" },
  linkedin: { ratio: "aspect-[1.91/1]", tone: "LinkedIn feed" },
};

function Body({ p }: { p: Preview }) {
  const [more, setMore] = useState(false);
  const cut = p.more_cutoff && p.text.length > p.more_cutoff && !more ? p.more_cutoff : null;
  return (
    <p className="m-0 whitespace-pre-wrap break-words text-[13px]">
      {cut ? p.text.slice(0, cut) : p.text}
      {cut && (
        <button type="button" className="ml-1 text-muted underline" onClick={() => setMore(true)}>
          …more
        </button>
      )}
    </p>
  );
}

export function PreviewCard({ p }: { p: Preview }) {
  const frame = FRAME[p.platform] ?? FRAME.facebook;
  const first = p.media[0];
  const vertical = p.platform === "tiktok" || p.post_format === "reel" || p.post_format === "story";
  const name = p.account.account_name || PLATFORM_LABEL[p.platform];
  return (
    <div className="mx-auto max-w-[360px] overflow-hidden rounded-lg border border-border bg-panel" data-testid={`preview-${p.platform}`}>
      <div className="flex items-center gap-2 p-2.5">
        {p.account.avatar_url ? (
          <img src={p.account.avatar_url} alt="" className="h-8 w-8 rounded-full object-cover" />
        ) : (
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold">{name.slice(0, 1)}</div>
        )}
        <div className="min-w-0">
          <div className="truncate text-[13px] font-semibold">{name}</div>
          <div className="text-[11px] text-muted">
            {p.account.handle ? `@${p.account.handle} · ` : ""}
            {frame.tone} · {p.post_format}
          </div>
        </div>
      </div>
      {p.platform === "linkedin" || p.platform === "facebook" ? <div className="px-2.5 pb-2"><Body p={p} /></div> : null}
      {first ? (
        <div className={`relative bg-bg ${vertical ? "aspect-[9/16]" : frame.ratio}`}>
          {first.kind === "video" ? (
            <video src={first.url} className="h-full w-full object-cover" controls muted preload="metadata" />
          ) : (
            <img src={first.url} alt="" className="h-full w-full object-cover" />
          )}
          {p.media.length > 1 && <span className="absolute right-2 top-2 rounded bg-black/60 px-1.5 text-[11px] text-white">1/{p.media.length}</span>}
        </div>
      ) : (
        p.link_url && (
          <div className="mx-2.5 mb-2 rounded border border-border p-2 text-xs text-muted">
            Link preview: {p.link_url}
          </div>
        )
      )}
      {p.platform === "instagram" || p.platform === "tiktok" ? (
        <div className="p-2.5">
          {p.title && <div className="mb-1 text-[13px] font-semibold">{p.title}</div>}
          <Body p={p} />
        </div>
      ) : null}
      <div className="border-t border-border px-2.5 py-1.5 text-[11px] text-muted">
        {p.text.length.toLocaleString()} / {p.caption_max.toLocaleString()} characters
      </div>
    </div>
  );
}

export default function PlatformPreview({ versionId }: { versionId: string }) {
  const preview = useQuery({ queryKey: organicKeys.preview(versionId), queryFn: () => fetchPreview(versionId) });
  if (preview.isPending) return <p className="text-xs text-muted">Loading preview…</p>;
  if (preview.isError) return <p className="text-xs text-danger">{errorText(preview.error)}</p>;
  const p = preview.data;
  return (
    <div>
      <PreviewCard p={p} />
      {p.errors.length > 0 && (
        <ul className="m-0 mt-2 pl-4 text-xs text-danger" data-testid="preview-errors">
          {p.errors.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      )}
      {p.warnings.length > 0 && (
        <ul className="m-0 mt-2 pl-4 text-xs text-warn">
          {p.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
