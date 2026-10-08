"use client";

import { useEffect, useState } from "react";

import { updatePlatformAd } from "@/lib/api/ads";
import type { AdFields, TreeAd } from "@/lib/types/ads";

import { AD_FIELDS, FORMAT_LABEL, FieldInput, formatsFor, useAutosave, useBuilder, visible } from "./tree";

// Ad level: the format (only this platform's, narrowed by Google's campaign
// type), then that format's fields with live character counters.
export default function AdForm({ ad }: { ad: TreeAd }) {
  const { tree, platform, editable } = useBuilder();
  const [a, setA] = useState(ad);
  const save = useAutosave<AdFields>((changes) => updatePlatformAd(ad.id, changes), ad.id);
  // A newer tree from the server, plus any edits not sent yet.
  useEffect(() => {
    const p = save.pending();
    setA({ ...ad, ...(p.name !== undefined ? { name: p.name } : {}), ...(p.creative ? { creative: { ...ad.creative, ...p.creative } } : {}) });
  }, [ad]);
  const setCreative = (changes: Record<string, unknown>) => {
    setA((cur) => ({ ...cur, creative: { ...cur.creative, ...changes } }));
    save({ creative: changes });
  };
  const disabled = !editable;
  const formats = formatsFor(platform, tree.campaign.campaign_type);
  const format = typeof a.creative.format === "string" ? a.creative.format : "";
  return (
    <div className="card">
      <h3 className="mt-0">{tree.hierarchy.ad}</h3>
      <div className="form-row">
        <label htmlFor="pa_name">Name</label>
        <input
          id="pa_name"
          maxLength={255}
          disabled={disabled}
          value={a.name}
          onChange={(e) => {
            const v = e.target.value;
            setA((cur) => ({ ...cur, name: v }));
            if (v.trim()) save({ name: v });
          }}
        />
      </div>
      <div className="form-row">
        <label htmlFor="pa_format">Format</label>
        <select id="pa_format" disabled={disabled} value={format} onChange={(e) => setCreative({ format: e.target.value })}>
          {!formats.includes(format) && <option value={format}>{format ? `${FORMAT_LABEL[format] ?? format} (not for this campaign type)` : "Choose…"}</option>}
          {formats.map((f) => (
            <option key={f} value={f}>
              {FORMAT_LABEL[f] ?? f}
            </option>
          ))}
        </select>
      </div>
      {AD_FIELDS[tree.platform]
        .filter((spec) => visible(spec, a.creative, format))
        .map((spec) => (
          <FieldInput key={`${spec.key}_${spec.formats?.join() ?? ""}`} spec={spec} idPrefix="pa" disabled={disabled} value={a.creative[spec.key]} onChange={(v) => setCreative({ [spec.key]: v })} />
        ))}
    </div>
  );
}
