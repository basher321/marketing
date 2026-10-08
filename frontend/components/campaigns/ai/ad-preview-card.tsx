"use client";

import type { PreviewAd, SafetyIssue } from "@/lib/types/ai-campaigns";

const FIELD_LABEL: Record<string, string> = {
  primary_text: "Primary text",
  ad_text: "Ad text",
  intro_text: "Intro text",
  long_headline: "Long headline",
  long_headlines: "Long headlines",
  card_headline: "Card headline",
  business_name: "Business name",
  display_name: "Display name",
  brand_name: "Brand name",
  alt_text: "Alt text",
};

function label(key: string): string {
  return FIELD_LABEL[key] ?? key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

// One generated ad: images, every text with its character count, and the
// safety issues that point at it. Regenerate is offered while in review.
export default function AdPreviewCard({
  ad,
  issues,
  busy,
  onRegenerate,
}: {
  ad: PreviewAd;
  issues: SafetyIssue[];
  busy: boolean;
  onRegenerate?: (what: "copy" | "image") => void;
}) {
  const texts = Object.entries(ad.copy).filter(([, v]) => (Array.isArray(v) ? v.length > 0 : Boolean(v)));
  return (
    <div className="card" data-ad={ad.ref} style={{ padding: 12 }}>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="text-[13px] font-semibold">
          {ad.group} · {ad.format.replace(/_/g, " ")}
        </div>
        {ad.angle && <span className="text-xs text-muted">Angle: {ad.angle}</span>}
      </div>
      {ad.images.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {ad.images.map((img, i) =>
            img.preview ? (
              // A data: URL or an external product image, so next/image optimisation does not apply.
              <img key={i} src={img.preview} alt={`Generated image ${img.ratio ?? ""}`} className="h-28 rounded border border-border object-cover" />
            ) : (
              <div key={i} className="flex h-28 w-28 items-center justify-center rounded border border-border text-xs text-muted">
                {img.ratio} · uploaded
              </div>
            ),
          )}
        </div>
      )}
      <dl className="m-0 text-xs">
        {texts.map(([k, v]) => (
          <div key={k} className="mb-1.5">
            <dt className="font-semibold">{label(k)}</dt>
            {Array.isArray(v) ? (
              <dd className="m-0">
                <ul className="m-0 pl-4">
                  {v.map((item, i) => (
                    <li key={i}>
                      {item} <span className="text-muted">({item.length})</span>
                    </li>
                  ))}
                </ul>
              </dd>
            ) : (
              <dd className="m-0 break-words">
                {v} <span className="text-muted">({String(v).length})</span>
              </dd>
            )}
          </div>
        ))}
      </dl>
      {issues.length > 0 && (
        <ul className="m-0 mt-2 pl-4 text-xs">
          {issues.map((i, k) => (
            <li key={k} className={i.severity === "error" ? "text-danger" : "text-warn"}>
              {i.message}
            </li>
          ))}
        </ul>
      )}
      {onRegenerate && (
        <div className="mt-2 flex gap-2">
          <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => onRegenerate("copy")}>
            New copy
          </button>
          {ad.images.some((i) => i.source && i.source !== "catalog" && i.source !== "brand logo") && (
            <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => onRegenerate("image")}>
              New image
            </button>
          )}
        </div>
      )}
    </div>
  );
}
