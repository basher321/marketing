"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { fetchAudiences } from "@/lib/api/campaigns";
import { fetchCustomAudiences, metaKeys, searchTargeting } from "@/lib/api/meta";
import type { LookupItem, TargetRef, Targeting } from "@/lib/types/meta";

// Meta search box: type to search Meta's own targeting catalog, click to add.
function MetaSearch({
  kind,
  placeholder,
  onPick,
  disabled,
}: {
  kind: "adgeolocation" | "adinterest" | "adlocale" | "adTargetingCategory";
  placeholder: string;
  onPick: (item: LookupItem) => void;
  disabled?: boolean;
}) {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 350);
    return () => clearTimeout(t);
  }, [q]);
  const results = useQuery({
    queryKey: metaKeys.lookup(kind, debounced),
    queryFn: () => searchTargeting(kind, debounced),
    enabled: debounced.length >= 2,
    staleTime: 60_000,
  });
  return (
    <div className="relative">
      <input disabled={disabled} placeholder={placeholder} value={q} onChange={(e) => setQ(e.target.value)} aria-label={placeholder} />
      {debounced.length >= 2 && (results.data?.length || results.isError) ? (
        <div className="absolute z-10 mt-1 max-h-56 w-full overflow-y-auto rounded-md border border-border bg-panel shadow">
          {results.isError && <div className="p-2 text-xs text-danger">{results.error.message}</div>}
          {results.data?.map((r) => (
            <button
              key={`${r.type}-${r.id}`}
              type="button"
              className="block w-full px-2 py-1.5 text-left text-[13px] hover:bg-bg"
              onClick={() => {
                onPick(r);
                setQ("");
              }}
            >
              {r.name} <span className="text-[11px] text-muted">{r.type}{typeof r.extra.country_code === "string" ? ` · ${r.extra.country_code}` : ""}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function Chips({ items, onRemove, label }: { items: TargetRef[]; onRemove: (key: string) => void; label?: (t: TargetRef) => string }) {
  if (!items.length) return null;
  return (
    <div className="mt-1 flex flex-wrap gap-1">
      {items.map((t) => (
        <span key={`${t.type}-${t.key}`} className="badge badge-neutral">
          {label ? label(t) : t.name || t.key}
          <button type="button" className="ml-1" aria-label={`Remove ${t.name}`} onClick={() => onRemove(t.key)}>
            ✕
          </button>
        </span>
      ))}
    </div>
  );
}

const ref = (i: LookupItem, extra: Partial<TargetRef> = {}): TargetRef => ({ key: i.id, name: i.name, type: i.type, ...extra });

// Ad set audience (SPEC-FE-039): locations, age, gender, languages, detailed
// targeting, custom/lookalike include/exclude, Advantage+ audience, and
// "load saved audience". Every entry carries Meta's own id.
export default function AudienceEditor({
  value,
  onChange,
  onLoadSaved,
  disabled,
  restricted,
}: {
  value: Targeting;
  onChange: (t: Targeting) => void;
  onLoadSaved: (audienceId: string) => void;
  disabled?: boolean;
  /** Special ad category: no age/gender/zip targeting, no lookalikes. */
  restricted?: boolean;
}) {
  const saved = useQuery({ queryKey: ["campaigns", "audiences"], queryFn: fetchAudiences, staleTime: 60_000 });
  const custom = useQuery({ queryKey: metaKeys.lookup("custom-audiences"), queryFn: fetchCustomAudiences, staleTime: 60_000, retry: false });
  const set = (patch: Partial<Targeting>) => onChange({ ...value, ...patch });

  const addLocation = (i: LookupItem) => {
    if (i.type === "country") return set({ countries: Array.from(new Set([...value.countries, String(i.extra.country_code ?? i.id).toUpperCase()])) });
    if (i.type === "city") return set({ cities: [...value.cities, ref(i, { radius: 10, distance_unit: "kilometer" })] });
    if (i.type === "zip") return set({ zips: [...value.zips, ref(i)] });
    return set({ regions: [...value.regions, ref(i)] });
  };

  return (
    <fieldset disabled={disabled} className="grid gap-2">
      <div className="form-row">
        <label htmlFor="aud_saved">Start from a saved audience</label>
        <select id="aud_saved" value="" onChange={(e) => e.target.value && onLoadSaved(e.target.value)}>
          <option value="">Choose…</option>
          {saved.data?.items.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
      </div>
      {value.pending_terms && value.pending_terms.length > 0 && (
        <p className="m-0 text-xs text-warn">Pick these from Meta&apos;s list below: {value.pending_terms.join(", ")}</p>
      )}
      <div className="form-row">
        <label>Locations</label>
        <MetaSearch kind="adgeolocation" placeholder="Search countries, regions, cities or zip codes" onPick={addLocation} />
        <div className="mt-1 flex flex-wrap gap-1">
          {value.countries.map((c) => (
            <span key={c} className="badge badge-neutral">
              {c}
              <button type="button" className="ml-1" aria-label={`Remove ${c}`} onClick={() => set({ countries: value.countries.filter((x) => x !== c) })}>
                ✕
              </button>
            </span>
          ))}
        </div>
        <Chips items={value.regions} onRemove={(k) => set({ regions: value.regions.filter((r) => r.key !== k) })} />
        <Chips
          items={value.cities}
          label={(t) => `${t.name} +${t.radius ?? 10} km`}
          onRemove={(k) => set({ cities: value.cities.filter((r) => r.key !== k) })}
        />
        {value.cities.length > 0 && (
          <label className="text-xs">
            City radius (km){" "}
            <input
              type="number"
              min={1}
              max={80}
              className="w-20"
              value={value.cities[0].radius ?? 10}
              onChange={(e) => set({ cities: value.cities.map((c) => ({ ...c, radius: Number(e.target.value), distance_unit: "kilometer" })) })}
            />
          </label>
        )}
        <Chips items={value.zips} onRemove={(k) => set({ zips: value.zips.filter((r) => r.key !== k) })} />
      </div>
      <div className="grid gap-x-4 sm:grid-cols-3">
        <div className="form-row">
          <label htmlFor="aud_age_min">Age from</label>
          <input id="aud_age_min" type="number" min={18} max={65} disabled={restricted} value={value.age_min} onChange={(e) => set({ age_min: Number(e.target.value) })} />
        </div>
        <div className="form-row">
          <label htmlFor="aud_age_max">Age to (65 = 65+)</label>
          <input id="aud_age_max" type="number" min={18} max={65} disabled={restricted} value={value.age_max} onChange={(e) => set({ age_max: Number(e.target.value) })} />
        </div>
        <div className="form-row">
          <label htmlFor="aud_gender">Gender</label>
          <select id="aud_gender" disabled={restricted} value={value.genders} onChange={(e) => set({ genders: e.target.value as Targeting["genders"] })}>
            <option value="all">All</option>
            <option value="male">Men</option>
            <option value="female">Women</option>
          </select>
        </div>
      </div>
      <div className="form-row">
        <label>Languages</label>
        <MetaSearch kind="adlocale" placeholder="Search languages" onPick={(i) => set({ locales: [...value.locales, ref(i)] })} />
        <Chips items={value.locales} onRemove={(k) => set({ locales: value.locales.filter((r) => r.key !== k) })} />
      </div>
      <div className="form-row">
        <label>Detailed targeting</label>
        <MetaSearch kind="adinterest" placeholder="Search interests" onPick={(i) => set({ detailed: [...value.detailed, ref(i, { type: "interests" })] })} />
        <MetaSearch kind="adTargetingCategory" placeholder="Search behaviors" onPick={(i) => set({ detailed: [...value.detailed, ref(i, { type: "behaviors" })] })} />
        <Chips items={value.detailed} label={(t) => `${t.name} (${t.type})`} onRemove={(k) => set({ detailed: value.detailed.filter((r) => r.key !== k) })} />
      </div>
      <div className="grid gap-x-4 sm:grid-cols-2">
        {(["custom_audiences", "excluded_custom_audiences"] as const).map((field) => (
          <div className="form-row" key={field}>
            <label htmlFor={`aud_${field}`}>{field === "custom_audiences" ? "Custom audiences (include)" : "Exclude audiences"}</label>
            <select
              id={`aud_${field}`}
              value=""
              onChange={(e) => {
                const hit = custom.data?.find((c) => c.id === e.target.value);
                if (hit) set({ [field]: [...value[field], ref(hit)] });
              }}
            >
              <option value="">{custom.isError ? "Not available" : "Add…"}</option>
              {custom.data
                ?.filter((c) => !(restricted && c.type === "LOOKALIKE"))
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} {c.type ? `(${c.type.toLowerCase()})` : ""}
                  </option>
                ))}
            </select>
            <Chips items={value[field]} onRemove={(k) => set({ [field]: value[field].filter((r) => r.key !== k) })} />
          </div>
        ))}
      </div>
      <label className="flex items-center gap-2 text-[13px]">
        <input type="checkbox" checked={value.advantage_audience} onChange={(e) => set({ advantage_audience: e.target.checked })} />
        Advantage+ audience (let Meta go beyond these settings when it&apos;s likely to improve performance)
      </label>
    </fieldset>
  );
}
