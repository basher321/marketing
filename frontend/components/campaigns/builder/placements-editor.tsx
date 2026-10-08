"use client";

import type { Placements } from "@/lib/types/meta";

const PLATFORM_LABEL: Record<string, string> = {
  facebook: "Facebook",
  instagram: "Instagram",
  messenger: "Messenger",
  audience_network: "Audience Network",
};

// Placements (SPEC-FE-039): Advantage+ (Meta chooses) or manual platforms ->
// positions per platform -> devices. Positions come from the backend's list.
export default function PlacementsEditor({
  value,
  onChange,
  positions,
  disabled,
}: {
  value: Placements;
  onChange: (p: Placements) => void;
  positions: Record<string, string[]>;
  disabled?: boolean;
}) {
  const set = (patch: Partial<Placements>) => onChange({ ...value, ...patch });
  const togglePlatform = (p: Placements["platforms"][number], on: boolean) => {
    const platforms = on ? [...value.platforms, p] : value.platforms.filter((x) => x !== p);
    const nextPositions = { ...value.positions };
    if (!on) delete nextPositions[p];
    set({ platforms, positions: nextPositions });
  };
  return (
    <fieldset disabled={disabled} className="grid gap-2">
      <label className="flex items-center gap-2 text-[13px]">
        <input type="radio" name="placements" checked={value.mode === "advantage"} onChange={() => set({ mode: "advantage" })} />
        Advantage+ placements (recommended) — Meta places ads where they&apos;re likely to perform best
      </label>
      <label className="flex items-center gap-2 text-[13px]">
        <input type="radio" name="placements" checked={value.mode === "manual"} onChange={() => set({ mode: "manual" })} />
        Manual placements
      </label>
      {value.mode === "manual" && (
        <div className="grid gap-2 pl-5">
          <div className="text-xs text-muted">Devices</div>
          <div className="flex gap-3 text-[13px]">
            {(["mobile", "desktop"] as const).map((d) => (
              <label key={d} className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={value.devices.length === 0 || value.devices.includes(d)}
                  onChange={(e) => {
                    const all = value.devices.length === 0 ? ["mobile", "desktop"] : value.devices;
                    const next = (e.target.checked ? Array.from(new Set([...all, d])) : all.filter((x) => x !== d)) as Placements["devices"];
                    set({ devices: next.length === 2 ? [] : next });
                  }}
                />
                {d === "mobile" ? "Mobile" : "Desktop"}
              </label>
            ))}
          </div>
          {Object.keys(PLATFORM_LABEL).map((p) => {
            const platform = p as Placements["platforms"][number];
            const on = value.platforms.includes(platform);
            const chosen = value.positions[p] ?? [];
            return (
              <div key={p}>
                <label className="flex items-center gap-1.5 text-[13px] font-semibold">
                  <input type="checkbox" checked={on} onChange={(e) => togglePlatform(platform, e.target.checked)} />
                  {PLATFORM_LABEL[p]}
                </label>
                {on && (
                  <div className="flex flex-wrap gap-3 pl-5 text-xs">
                    {(positions[p] ?? []).map((pos) => (
                      <label key={pos} className="flex items-center gap-1">
                        <input
                          type="checkbox"
                          checked={chosen.length === 0 || chosen.includes(pos)}
                          onChange={(e) => {
                            const all = chosen.length === 0 ? positions[p] ?? [] : chosen;
                            const next = e.target.checked ? Array.from(new Set([...all, pos])) : all.filter((x) => x !== pos);
                            set({ positions: { ...value.positions, [p]: next.length === (positions[p] ?? []).length ? [] : next } });
                          }}
                        />
                        {pos.replace(/_/g, " ")}
                      </label>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </fieldset>
  );
}
