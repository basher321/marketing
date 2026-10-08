"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { fetchApps, fetchPixels, metaKeys, reachEstimate, updateAdSet } from "@/lib/api/meta";
import type { AdSetFields, BidStrategy, BuilderAdSet, ConversionLocation, Placements, Targeting } from "@/lib/types/meta";

import AudienceEditor from "./audience-editor";
import PlacementsEditor from "./placements-editor";
import { FieldIssues, useAutosave, useBuilder } from "./tree";

const LOCATION_LABEL: Record<string, string> = {
  none: "No destination (reach people)",
  website: "Website",
  app: "App",
  instant_form: "Instant form",
  on_ad: "On your ad",
  video: "Video views",
  page: "Facebook Page",
};
const GOAL_LABEL: Record<string, string> = {
  REACH: "Maximize reach",
  IMPRESSIONS: "Maximize impressions",
  AD_RECALL_LIFT: "Maximize ad recall lift",
  THRUPLAY: "Maximize ThruPlay views",
  LINK_CLICKS: "Maximize link clicks",
  LANDING_PAGE_VIEWS: "Maximize landing page views",
  POST_ENGAGEMENT: "Maximize engagement",
  PAGE_LIKES: "Maximize Page likes",
  OFFSITE_CONVERSIONS: "Maximize conversions",
  VALUE: "Maximize conversion value",
  LEAD_GENERATION: "Maximize leads",
  QUALITY_LEAD: "Maximize quality leads",
  APP_INSTALLS: "Maximize app installs",
};

// ISO <-> <input type="datetime-local"> in the browser's local time.
const toLocal = (iso: string | null) => {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};
const fromLocal = (v: string) => (v ? new Date(v).toISOString() : null);

// Ad set level (SPEC-FE-039): conversion location, performance goal, tracking
// (pixel + event / app), budget & schedule, audience, placements, reach estimate.
export default function AdSetForm({ adSet }: { adSet: BuilderAdSet }) {
  const { tree, objectives, editable, run } = useBuilder();
  const c = tree.campaign;
  const published = Boolean(adSet.external_id);
  const [f, setF] = useState(adSet);
  const save = useAutosave<AdSetFields>((changes) => updateAdSet(adSet.id, changes), adSet.id);
  // A newer tree from the server, plus any edits not sent yet.
  useEffect(() => setF({ ...adSet, ...save.pending() } as BuilderAdSet), [adSet]);
  const set = (changes: AdSetFields) => {
    setF((cur) => ({ ...cur, ...changes }) as BuilderAdSet);
    save(changes);
  };
  const objective = objectives?.objectives.find((o) => o.key === c.objective);
  const locations = objective?.conversion_locations ?? {};
  const goals = locations[f.conversion_location] ?? [];
  const needsPixel = f.conversion_location === "website" && ["OFFSITE_CONVERSIONS", "VALUE"].includes(f.optimization_goal ?? "");
  const needsApp = f.conversion_location === "app" || c.objective === "app_promotion";
  const pixels = useQuery({ queryKey: metaKeys.lookup("pixels"), queryFn: fetchPixels, enabled: needsPixel, retry: false });
  const apps = useQuery({ queryKey: metaKeys.lookup("apps"), queryFn: fetchApps, enabled: needsApp, retry: false });
  const [debouncedTargeting, setDebouncedTargeting] = useState(f.targeting);
  useEffect(() => {
    const t = setTimeout(() => setDebouncedTargeting(f.targeting), 800);
    return () => clearTimeout(t);
  }, [f.targeting]);
  const reach = useQuery({
    queryKey: ["meta", "reach", adSet.id, JSON.stringify(debouncedTargeting), f.optimization_goal, JSON.stringify(f.placements)],
    queryFn: () => reachEstimate(debouncedTargeting, f.optimization_goal ?? "REACH", f.placements),
    enabled: (debouncedTargeting.countries.length > 0 || debouncedTargeting.regions.length > 0 || debouncedTargeting.cities.length > 0) && Boolean(objectives?.connection.connected),
    staleTime: 60_000,
    retry: false,
  });
  const ownBudget = c.budget_mode === "ad_set";
  const draftOnly = !editable || published;
  const restricted = c.special_ad_categories.length > 0;

  return (
    <div className="grid gap-4">
      <div className="card">
        <h3 className="mt-0">Ad set</h3>
        <div className="form-row">
          <label htmlFor="as_name">Ad set name</label>
          <input id="as_name" disabled={!editable} value={f.name} onChange={(e) => set({ name: e.target.value })} />
        </div>
        {f.last_error && <p className="text-xs text-danger">{f.last_error}</p>}
        <div className="grid gap-x-4 sm:grid-cols-2">
          <div className="form-row">
            <label htmlFor="as_loc">Conversion location</label>
            <select
              id="as_loc"
              disabled={draftOnly}
              value={f.conversion_location}
              onChange={(e) => {
                const loc = e.target.value as ConversionLocation;
                set({ conversion_location: loc, optimization_goal: (locations[loc] ?? [])[0] });
              }}
            >
              {Object.keys(locations).map((loc) => (
                <option key={loc} value={loc}>
                  {LOCATION_LABEL[loc] ?? loc}
                </option>
              ))}
              {Object.entries(objective?.unavailable_locations ?? {}).map(([loc, reason]) => (
                <option key={loc} value={loc} disabled title={reason}>
                  {LOCATION_LABEL[loc] ?? loc} (unavailable)
                </option>
              ))}
            </select>
            <FieldIssues level="ad_set" id={adSet.id} field="conversion_location" />
          </div>
          <div className="form-row">
            <label htmlFor="as_goal">Performance goal</label>
            <select id="as_goal" disabled={draftOnly} value={f.optimization_goal ?? ""} onChange={(e) => set({ optimization_goal: e.target.value })}>
              {goals.map((g) => (
                <option key={g} value={g}>
                  {GOAL_LABEL[g] ?? g}
                </option>
              ))}
            </select>
            <FieldIssues level="ad_set" id={adSet.id} field="optimization_goal" />
          </div>
        </div>
        {needsPixel && (
          <div className="grid gap-x-4 sm:grid-cols-2">
            <div className="form-row">
              <label htmlFor="as_pixel">Pixel / dataset</label>
              <select id="as_pixel" disabled={draftOnly} value={f.pixel_id ?? ""} onChange={(e) => set({ pixel_id: e.target.value || null })}>
                <option value="">{objectives?.connection.pixel_id ? `Connected pixel (${objectives.connection.pixel_id})` : "Choose…"}</option>
                {pixels.data?.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              {pixels.isError && <span className="text-xs text-danger">{pixels.error.message}</span>}
              <FieldIssues level="ad_set" id={adSet.id} field="pixel_id" />
            </div>
            <div className="form-row">
              <label htmlFor="as_event">Conversion event</label>
              <select id="as_event" disabled={draftOnly} value={f.custom_event_type ?? "PURCHASE"} onChange={(e) => set({ custom_event_type: e.target.value })}>
                {(objectives?.event_types ?? ["PURCHASE"]).map((ev) => (
                  <option key={ev} value={ev}>
                    {ev.replace(/_/g, " ").toLowerCase()}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}
        {needsApp && (
          <div className="grid gap-x-4 sm:grid-cols-2">
            <div className="form-row">
              <label htmlFor="as_app">App</label>
              <select
                id="as_app"
                disabled={draftOnly}
                value={f.app_id ?? ""}
                onChange={(e) => {
                  const app = apps.data?.find((a) => a.id === e.target.value);
                  const urls = (app?.extra.object_store_urls ?? {}) as Record<string, string>;
                  set({ app_id: e.target.value || null, app_store_url: Object.values(urls)[0] ?? f.app_store_url });
                }}
              >
                <option value="">Choose…</option>
                {apps.data?.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
              {apps.isError && <span className="text-xs text-danger">{apps.error.message}</span>}
              <FieldIssues level="ad_set" id={adSet.id} field="app_id" />
            </div>
            <div className="form-row">
              <label htmlFor="as_store">App store link (https)</label>
              <input id="as_store" disabled={draftOnly} value={f.app_store_url ?? ""} onChange={(e) => set({ app_store_url: e.target.value || null })} />
            </div>
          </div>
        )}
      </div>

      <div className="card">
        <h3 className="mt-0">Budget &amp; schedule</h3>
        {ownBudget ? (
          <div className="grid gap-x-4 sm:grid-cols-3">
            <div className="form-row">
              <label htmlFor="as_btype">Budget</label>
              <select id="as_btype" disabled={draftOnly} value={f.budget_type} onChange={(e) => set({ budget_type: e.target.value as "daily" | "lifetime" })}>
                <option value="daily">Daily budget</option>
                <option value="lifetime">Lifetime budget</option>
              </select>
            </div>
            <div className="form-row">
              <label htmlFor="as_budget">Amount ({c.currency})</label>
              <input id="as_budget" type="number" min={1} step="0.01" disabled={!editable} value={f.budget ?? ""} onChange={(e) => set({ budget: e.target.value === "" ? null : Number(e.target.value) })} />
              <FieldIssues level="ad_set" id={adSet.id} field="budget" />
            </div>
            <div className="form-row">
              <label htmlFor="as_bid">Bid strategy</label>
              <select id="as_bid" disabled={draftOnly} value={f.bid_strategy ?? "LOWEST_COST_WITHOUT_CAP"} onChange={(e) => set({ bid_strategy: e.target.value as BidStrategy })}>
                <option value="LOWEST_COST_WITHOUT_CAP">Highest volume</option>
                <option value="LOWEST_COST_WITH_BID_CAP">Bid cap</option>
                <option value="COST_CAP">Cost per result goal</option>
              </select>
            </div>
            {(f.bid_strategy === "LOWEST_COST_WITH_BID_CAP" || f.bid_strategy === "COST_CAP") && (
              <div className="form-row">
                <label htmlFor="as_bidamt">Amount ({c.currency})</label>
                <input id="as_bidamt" type="number" min={0.01} step="0.01" disabled={!editable} value={f.bid_amount ?? ""} onChange={(e) => set({ bid_amount: e.target.value === "" ? null : Number(e.target.value) })} />
                <FieldIssues level="ad_set" id={adSet.id} field="bid_amount" />
              </div>
            )}
          </div>
        ) : (
          <p className="text-xs text-muted">This campaign uses an Advantage+ campaign budget (set on the campaign).</p>
        )}
        <div className="grid gap-x-4 sm:grid-cols-2">
          <div className="form-row">
            <label htmlFor="as_start">Start</label>
            <input id="as_start" type="datetime-local" disabled={draftOnly} value={toLocal(f.starts_at)} onChange={(e) => set({ starts_at: fromLocal(e.target.value) })} />
            <FieldIssues level="ad_set" id={adSet.id} field="starts_at" />
          </div>
          <div className="form-row">
            <label htmlFor="as_end">End {f.budget_type === "lifetime" ? "" : "(optional)"}</label>
            <input id="as_end" type="datetime-local" disabled={!editable} value={toLocal(f.ends_at)} onChange={(e) => set({ ends_at: fromLocal(e.target.value) })} />
            <FieldIssues level="ad_set" id={adSet.id} field="ends_at" />
          </div>
        </div>
        <span className="text-xs text-muted">Times are in your browser&apos;s time zone. A future start publishes as Scheduled.</span>
      </div>

      <div className="card">
        <h3 className="mt-0">Audience</h3>
        <FieldIssues level="ad_set" id={adSet.id} field="targeting" />
        <AudienceEditor
          value={f.targeting}
          disabled={draftOnly}
          restricted={restricted}
          onChange={(t: Targeting) => set({ targeting: t })}
          onLoadSaved={(id) => void run(() => updateAdSet(adSet.id, { audience_id: id }))}
        />
        <div className="mt-3 text-[13px]">
          Estimated daily reach:{" "}
          {reach.data?.available ? (
            <b>
              {reach.data.daily_reach_lower?.toLocaleString()}–{reach.data.daily_reach_upper?.toLocaleString()}
            </b>
          ) : (
            <span className="text-muted">{reach.data?.reason ?? (objectives?.connection.connected ? "add a location" : "connect Meta to see an estimate")}</span>
          )}
        </div>
      </div>

      <div className="card">
        <h3 className="mt-0">Placements</h3>
        <FieldIssues level="ad_set" id={adSet.id} field="placements" />
        <PlacementsEditor
          value={f.placements}
          disabled={draftOnly}
          positions={objectives?.placements ?? {}}
          onChange={(p: Placements) => set({ placements: p })}
        />
      </div>
    </div>
  );
}
