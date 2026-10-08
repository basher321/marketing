"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { previewAd } from "@/lib/api/meta";

import { errorText, useBuilder } from "./tree";

const FORMAT_LABEL: Record<string, string> = {
  MOBILE_FEED_STANDARD: "Facebook feed (mobile)",
  DESKTOP_FEED_STANDARD: "Facebook feed (desktop)",
  INSTAGRAM_STANDARD: "Instagram feed",
  INSTAGRAM_STORY: "Instagram Stories",
  FACEBOOK_STORY_MOBILE: "Facebook Stories",
  INSTAGRAM_REELS: "Instagram Reels",
};

// Meta's only allowed origin for the preview iframe markup (SPEC-FE-039).
function safeIframe(html: string): string | null {
  const src = /src="([^"]+)"/.exec(html)?.[1]?.replace(/&amp;/g, "&");
  if (!src) return null;
  try {
    const url = new URL(src);
    return url.protocol === "https:" && (url.hostname === "www.facebook.com" || url.hostname.endsWith(".facebook.com")) ? url.toString() : null;
  } catch {
    return null;
  }
}

// Real Meta preview of the selected ad (Meta's generatepreviews), never
// rendered by us: only the iframe URL Meta returns is used, in a sandbox.
export default function PreviewPanel() {
  const { tree, selected, objectives } = useBuilder();
  const adId =
    selected.level === "ad"
      ? selected.id
      : selected.level === "ad_set"
        ? tree.ad_sets.find((s) => s.id === selected.id)?.ads[0]?.id
        : tree.ad_sets[0]?.ads[0]?.id;
  const [format, setFormat] = useState("MOBILE_FEED_STANDARD");
  const [requested, setRequested] = useState(0);
  const preview = useQuery({
    queryKey: ["meta", "preview", adId, format, requested],
    queryFn: () => previewAd(adId as string, format),
    enabled: Boolean(adId) && requested > 0,
    retry: false,
  });
  const src = preview.data ? safeIframe(preview.data.iframe_html) : null;

  return (
    <div className="card" style={{ position: "sticky", top: 16 }}>
      <h3 className="mt-0">Preview</h3>
      <select aria-label="Preview format" value={format} onChange={(e) => setFormat(e.target.value)}>
        {(objectives?.preview_formats ?? Object.keys(FORMAT_LABEL)).map((f) => (
          <option key={f} value={f}>
            {FORMAT_LABEL[f] ?? f}
          </option>
        ))}
      </select>
      <button type="button" className="btn btn-secondary btn-sm mt-2 w-full" disabled={!adId || !objectives?.connection.connected} onClick={() => setRequested((n) => n + 1)}>
        {preview.isFetching ? "Loading Meta preview…" : "Show Meta preview"}
      </button>
      {!objectives?.connection.connected && <p className="text-xs text-muted">Connect Meta in Integrations to see Meta&apos;s own preview.</p>}
      {preview.isError && <p className="text-xs text-danger">{errorText(preview.error)}</p>}
      {src && (
        <iframe
          title="Meta ad preview"
          src={src}
          sandbox="allow-scripts allow-same-origin allow-popups"
          className="mt-3 w-full rounded border border-border"
          style={{ height: 520 }}
        />
      )}
      {preview.data && !src && <p className="text-xs text-danger">Meta returned a preview from an unexpected address; it wasn&apos;t shown.</p>}
    </div>
  );
}
