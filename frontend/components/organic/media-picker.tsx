"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { fetchMedia, mediaKeys, uploadMedia } from "@/lib/api/media";
import type { MediaItem, MediaKind } from "@/lib/types/media";

import { errorText } from "./shared";

export function MediaThumb({ item, size = 72 }: { item: { kind: string; url: string; duration_ms?: number | null }; size?: number }) {
  return item.kind === "video" ? (
    <div className="relative overflow-hidden rounded-md bg-bg" style={{ width: size, height: size }}>
      <video src={item.url} className="h-full w-full object-cover" muted preload="metadata" />
      <span className="absolute bottom-0.5 right-1 rounded bg-black/60 px-1 text-[10px] text-white">
        ▶ {item.duration_ms ? `${Math.round(item.duration_ms / 1000)}s` : ""}
      </span>
    </div>
  ) : (
    <img src={item.url} alt="" className="rounded-md object-cover" style={{ width: size, height: size }} />
  );
}

/**
 * Media library picker (SPEC-FE-050): upload (images and videos, sent to the
 * backend media library) or pick existing items. `value` is the ordered list
 * of selected media ids.
 */
export default function MediaPicker({
  value,
  onChange,
  kind,
  max = 10,
}: {
  value: string[];
  onChange: (ids: string[], items: MediaItem[]) => void;
  kind?: MediaKind;
  max?: number;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const [known, setKnown] = useState<Record<string, MediaItem>>({});
  const library = useQuery({ queryKey: mediaKeys.list(kind ?? ""), queryFn: () => fetchMedia(kind ?? ""), enabled: open });
  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      const out: MediaItem[] = [];
      for (const f of files) out.push(await uploadMedia(f));
      return out;
    },
    onSuccess: (items) => {
      const merged = { ...known, ...Object.fromEntries(items.map((i) => [i.id, i])) };
      setKnown(merged);
      const ids = [...value, ...items.map((i) => i.id).filter((id) => !value.includes(id))].slice(0, max);
      onChange(ids, ids.map((id) => merged[id]).filter(Boolean));
      void queryClient.invalidateQueries({ queryKey: ["media"] });
    },
  });
  const all = { ...Object.fromEntries((library.data?.items ?? []).map((i) => [i.id, i])), ...known };
  const toggle = (item: MediaItem) => {
    const merged = { ...all, [item.id]: item };
    setKnown((k) => ({ ...k, [item.id]: item }));
    const ids = value.includes(item.id) ? value.filter((v) => v !== item.id) : [...value, item.id].slice(0, max);
    onChange(ids, ids.map((id) => merged[id]).filter(Boolean));
  };
  const accept = kind === "image" ? "image/jpeg,image/png,image/webp" : kind === "video" ? "video/mp4,video/quicktime" : "image/jpeg,image/png,image/webp,video/mp4,video/quicktime";
  return (
    <div data-testid="media-picker">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        {value.map((id) =>
          all[id] ? (
            <button key={id} type="button" title="Remove" onClick={() => toggle(all[id])} className="relative">
              <MediaThumb item={all[id]} />
              <span className="absolute -right-1 -top-1 rounded-full bg-danger px-1 text-[10px] text-white">✕</span>
            </button>
          ) : (
            <span key={id} className="text-xs text-muted">
              1 item
            </span>
          ),
        )}
        <button type="button" className="btn btn-secondary btn-sm" disabled={upload.isPending} onClick={() => fileRef.current?.click()}>
          {upload.isPending ? "Uploading…" : "Upload"}
        </button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          {open ? "Close library" : "From library"}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept={accept}
          multiple
          hidden
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            if (files.length) upload.mutate(files);
            e.target.value = "";
          }}
        />
      </div>
      {upload.isError && <p className="m-0 mb-2 text-xs text-danger">{errorText(upload.error)}</p>}
      {open && (
        <div className="card mb-2" style={{ padding: 10 }}>
          {library.isPending ? (
            <p className="m-0 text-xs text-muted">Loading…</p>
          ) : library.isError ? (
            <p className="m-0 text-xs text-danger">{errorText(library.error)}</p>
          ) : library.data.items.length === 0 ? (
            <p className="m-0 text-xs text-muted">The library is empty. Upload, or generate in Photo / Video Generation.</p>
          ) : (
            <div className="flex max-h-64 flex-wrap gap-2 overflow-y-auto">
              {library.data.items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => toggle(item)}
                  aria-pressed={value.includes(item.id)}
                  title={`${item.name ?? item.kind} · ${item.width ?? "?"}×${item.height ?? "?"} · ${item.source.replace("_", " ")}`}
                  className={`rounded-md border-2 ${value.includes(item.id) ? "border-accent" : "border-transparent"}`}
                >
                  <MediaThumb item={item} />
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
