"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { adsKeys, platformLookup } from "@/lib/api/ads";

import { TARGETING, errorText, useBuilder, type TargetSection } from "./tree";

type Entry = { id: string | null; name: string; match?: string };
type Targeting = Record<string, unknown>;

const MATCH = [
  { value: "BROAD", label: "Broad" },
  { value: "PHRASE", label: "Phrase" },
  { value: "EXACT", label: "Exact" },
];

// One targeting list: chips + a search box. Connected -> the platform's own
// catalog (GET /ads/{platform}/lookup/{kind}); otherwise, or when the lookup
// isn't available, typed text is added with id null and flagged so it can be
// picked from the platform's list after connecting. Keywords are always typed.
function Section({ section, entries, onChange, disabled }: { section: TargetSection; entries: Entry[]; onChange: (e: Entry[]) => void; disabled: boolean }) {
  const { tree, platform } = useBuilder();
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [match, setMatch] = useState("BROAD");
  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 350);
    return () => clearTimeout(t);
  }, [q]);
  const searchable = Boolean(section.lookup) && section.key !== "keywords" && tree.connection.connected && tree.connection.publishing === "available";
  const results = useQuery({
    queryKey: adsKeys.lookup(tree.platform, section.lookup ?? "", debounced),
    queryFn: () => platformLookup(tree.platform, section.lookup as string, debounced),
    enabled: searchable && debounced.length >= 2,
    retry: false,
  });
  const add = (e: Entry) => {
    if (!entries.some((x) => x.name.toLowerCase() === e.name.toLowerCase() && x.id === e.id)) onChange([...entries, e]);
    setQ("");
  };
  const id = `tg_${section.key}`;
  return (
    <div className="form-row">
      <label htmlFor={id}>{section.label}</label>
      {entries.length > 0 && (
        <div className="mb-1 flex flex-wrap gap-1">
          {entries.map((e, i) => (
            <span key={`${e.id ?? e.name}_${i}`} className={`badge ${e.id ? "badge-neutral" : "badge-warn"}`} title={e.id ? undefined : `Typed while not connected: pick it from ${platform.label}'s list after connecting`}>
              {e.name}
              {e.match ? ` · ${e.match.toLowerCase()}` : ""}
              {!e.id && section.key !== "keywords" && section.key !== "negative_keywords" ? " *" : ""}
              {!disabled && (
                <button type="button" className="ml-1" aria-label={`Remove ${e.name}`} onClick={() => onChange(entries.filter((_, j) => j !== i))}>
                  ✕
                </button>
              )}
            </span>
          ))}
        </div>
      )}
      {!disabled && (
        <div className="flex gap-1">
          <input
            id={id}
            value={q}
            placeholder={searchable ? `Search ${platform.label}…` : "Type and press Enter"}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && q.trim()) {
                e.preventDefault();
                add({ id: null, name: q.trim(), ...(section.match ? { match } : {}) });
              }
            }}
          />
          {section.match && (
            <select aria-label="Match type" value={match} onChange={(e) => setMatch(e.target.value)}>
              {MATCH.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          )}
        </div>
      )}
      {searchable && results.data && results.data.length > 0 && (
        <ul className="m-0 mt-1 max-h-40 overflow-y-auto rounded border border-border p-1 text-[13px]">
          {results.data.map((r) => (
            <li key={r.id}>
              <button type="button" className="w-full rounded px-1 text-left hover:bg-bg" onClick={() => add({ id: r.id, name: r.name })}>
                {r.name}
                {r.type ? <span className="text-xs text-muted"> · {r.type}</span> : null}
              </button>
            </li>
          ))}
        </ul>
      )}
      {searchable && results.isError && <span className="text-xs text-warn">{errorText(results.error)} Typed entries are kept.</span>}
    </div>
  );
}

export default function TargetingEditor({ value, onChange, disabled }: { value: Targeting; onChange: (changes: Targeting) => void; disabled: boolean }) {
  const { tree, platform } = useBuilder();
  const cfg = TARGETING[tree.platform];
  const list = (key: string) => (Array.isArray(value[key]) ? (value[key] as Entry[]) : []);
  const genders = Array.isArray(value.genders) ? (value.genders as string[]) : [];
  return (
    <fieldset className="mb-3 rounded border border-border p-3">
      <legend className="px-1 text-[13px] font-semibold">Audience</legend>
      {!tree.connection.connected && (
        <p className="m-0 mb-2 text-xs text-warn">
          Connect {platform.label} in Integrations to search its catalog. Until then, typed entries are saved and marked *.
        </p>
      )}
      {cfg.sections.map((s) => (
        <Section key={s.key} section={s} entries={list(s.key)} disabled={disabled} onChange={(entries) => onChange({ [s.key]: entries })} />
      ))}
      {cfg.demographics && (
        <div className="grid gap-x-4 sm:grid-cols-3">
          <div className="form-row">
            <label htmlFor="tg_age_min">Age from</label>
            <input id="tg_age_min" type="number" min={13} max={65} disabled={disabled} value={(value.age_min as number | undefined) ?? ""} onChange={(e) => onChange({ age_min: e.target.value === "" ? null : Number(e.target.value) })} />
          </div>
          <div className="form-row">
            <label htmlFor="tg_age_max">Age to (65 = 65+)</label>
            <input id="tg_age_max" type="number" min={13} max={65} disabled={disabled} value={(value.age_max as number | undefined) ?? ""} onChange={(e) => onChange({ age_max: e.target.value === "" ? null : Number(e.target.value) })} />
          </div>
          <fieldset className="form-row">
            <legend className="text-xs font-semibold">Gender</legend>
            {["female", "male"].map((g) => (
              <label key={g} className="mr-3 inline-flex items-center gap-1 text-[13px]">
                <input type="checkbox" disabled={disabled} checked={genders.includes(g)} onChange={(e) => onChange({ genders: e.target.checked ? [...genders, g] : genders.filter((x) => x !== g) })} />
                {g === "female" ? "Women" : "Men"}
              </label>
            ))}
            <span className="block text-xs text-muted">None ticked = all</span>
          </fieldset>
        </div>
      )}
    </fieldset>
  );
}
