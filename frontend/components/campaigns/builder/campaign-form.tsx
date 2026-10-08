"use client";

import { useEffect, useState } from "react";

import { updateCampaign } from "@/lib/api/meta";
import type { BidStrategy, CampaignFields } from "@/lib/types/meta";

import { FieldIssues, useAutosave, useBuilder } from "./tree";

const BID_LABEL: Record<BidStrategy, string> = {
  LOWEST_COST_WITHOUT_CAP: "Highest volume (lowest cost)",
  LOWEST_COST_WITH_BID_CAP: "Bid cap",
  COST_CAP: "Cost per result goal",
  LOWEST_COST_WITH_MIN_ROAS: "ROAS goal",
};
const CATEGORY_LABEL: Record<string, string> = {
  HOUSING: "Housing",
  EMPLOYMENT: "Employment",
  FINANCIAL_PRODUCTS_SERVICES: "Financial products and services",
  ISSUES_ELECTIONS_POLITICS: "Social issues, elections or politics",
};

// Campaign level (SPEC-FE-039): name, objective (read-only after creation is
// allowed to change; incompatible ad set goals are flagged), special ad
// categories, buying type, Advantage+ campaign budget, bid strategy, spend limit.
export default function CampaignForm() {
  const { tree, objectives, editable } = useBuilder();
  const c = tree.campaign;
  const published = Boolean(tree.meta?.published);
  const [f, setF] = useState(c);
  const save = useAutosave<CampaignFields>((changes) => updateCampaign(c.id, changes), c.id);
  // A newer tree from the server, plus any edits not sent yet.
  useEffect(() => setF({ ...tree.campaign, ...save.pending() } as typeof c), [tree.campaign]);
  const set = (changes: CampaignFields) => {
    setF((cur) => ({ ...cur, ...changes }) as typeof cur);
    save(changes);
  };
  const objective = objectives?.objectives.find((o) => o.key === f.objective);
  const cbo = f.budget_mode === "campaign";
  const disabled = !editable;

  return (
    <div className="card">
      <h3 className="mt-0">Campaign</h3>
      <div className="form-row">
        <label htmlFor="c_name">Campaign name</label>
        <input id="c_name" disabled={disabled} value={f.name} maxLength={255} onChange={(e) => set({ name: e.target.value })} />
        <FieldIssues level="campaign" id={c.id} field="name" />
      </div>
      <div className="form-row">
        <label htmlFor="c_obj">Objective</label>
        <select id="c_obj" disabled={disabled || published} value={f.objective} onChange={(e) => set({ objective: e.target.value as CampaignFields["objective"] })}>
          {objectives?.objectives.map((o) => (
            <option key={o.key} value={o.key} disabled={!o.available}>
              {o.label}
              {!o.available ? " (unavailable)" : ""}
            </option>
          )) ?? <option value={f.objective}>{f.objective}</option>}
        </select>
        {objective && <span className="text-xs text-muted">{objective.description}</span>}
        <FieldIssues level="campaign" id={c.id} field="objective" />
      </div>

      <fieldset className="form-row" disabled={disabled || published}>
        <label>Special ad categories</label>
        <span className="text-xs text-muted">Declare these if the ads are about credit, employment, housing or politics. Targeting is restricted (no age, gender or zip targeting; no lookalikes).</span>
        <div className="flex flex-wrap gap-3 text-[13px]">
          {(objectives?.special_ad_categories ?? Object.keys(CATEGORY_LABEL)).map((cat) => (
            <label key={cat} className="flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={f.special_ad_categories.includes(cat)}
                onChange={(e) =>
                  set({ special_ad_categories: e.target.checked ? [...f.special_ad_categories, cat] : f.special_ad_categories.filter((x) => x !== cat) })
                }
              />
              {CATEGORY_LABEL[cat] ?? cat}
            </label>
          ))}
        </div>
        {f.special_ad_categories.length > 0 && (
          <input
            aria-label="Special ad category countries"
            placeholder="Countries (e.g. BD, US)"
            value={f.special_ad_category_country.join(", ")}
            onChange={(e) => set({ special_ad_category_country: e.target.value.split(",").map((s) => s.trim().toUpperCase()).filter(Boolean) })}
          />
        )}
        <FieldIssues level="campaign" id={c.id} field="special_ad_category_country" />
      </fieldset>

      <div className="form-row">
        <label htmlFor="c_buy">Buying type</label>
        <select id="c_buy" disabled value="AUCTION">
          <option value="AUCTION">Auction</option>
          <option value="RESERVATION">Reservation (needs Meta allow-listing)</option>
        </select>
      </div>

      <div className="form-row">
        <label className="flex items-center gap-2">
          <input type="checkbox" disabled={disabled || published} checked={cbo} onChange={(e) => set({ budget_mode: e.target.checked ? "campaign" : "ad_set" })} />
          Advantage+ campaign budget
        </label>
        <span className="text-xs text-muted">One budget for the whole campaign, shared across ad sets by Meta. Off = each ad set has its own budget.</span>
      </div>
      {cbo && (
        <div className="grid gap-x-4 sm:grid-cols-3">
          <div className="form-row">
            <label htmlFor="c_btype">Budget</label>
            <select id="c_btype" disabled={disabled || published} value={f.budget_type} onChange={(e) => set({ budget_type: e.target.value as "daily" | "lifetime" })}>
              <option value="daily">Daily budget</option>
              <option value="lifetime">Lifetime budget</option>
            </select>
          </div>
          <div className="form-row">
            <label htmlFor="c_budget">Amount ({c.currency})</label>
            <input id="c_budget" type="number" min={1} step="0.01" disabled={disabled} value={f.budget ?? ""} onChange={(e) => set({ budget: e.target.value === "" ? null : Number(e.target.value) })} />
            <FieldIssues level="campaign" id={c.id} field="budget" />
          </div>
          <div className="form-row">
            <label htmlFor="c_bid">Bid strategy</label>
            <select id="c_bid" disabled={disabled || published} value={f.bid_strategy} onChange={(e) => set({ bid_strategy: e.target.value as BidStrategy })}>
              {(objectives?.bid_strategies ?? (Object.keys(BID_LABEL) as BidStrategy[])).map((b) => (
                <option key={b} value={b}>
                  {BID_LABEL[b]}
                </option>
              ))}
            </select>
          </div>
          {(f.bid_strategy === "LOWEST_COST_WITH_BID_CAP" || f.bid_strategy === "COST_CAP") && (
            <div className="form-row">
              <label htmlFor="c_bidamt">{f.bid_strategy === "COST_CAP" ? "Cost per result goal" : "Bid cap"} ({c.currency})</label>
              <input id="c_bidamt" type="number" min={0.01} step="0.01" disabled={disabled} value={f.bid_amount ?? ""} onChange={(e) => set({ bid_amount: e.target.value === "" ? null : Number(e.target.value) })} />
              <FieldIssues level="campaign" id={c.id} field="bid_amount" />
            </div>
          )}
          {f.bid_strategy === "LOWEST_COST_WITH_MIN_ROAS" && (
            <div className="form-row">
              <label htmlFor="c_roas">Minimum ROAS (e.g. 2.5)</label>
              <input id="c_roas" type="number" min={0.01} step="0.01" disabled={disabled || published} value={f.roas_floor ?? ""} onChange={(e) => set({ roas_floor: e.target.value === "" ? null : Number(e.target.value) })} />
              <FieldIssues level="campaign" id={c.id} field="roas_floor" />
            </div>
          )}
        </div>
      )}
      <div className="form-row">
        <label htmlFor="c_cap">Campaign spending limit (optional, {c.currency})</label>
        <input id="c_cap" type="number" min={1} step="0.01" disabled={disabled} value={f.spend_cap ?? ""} onChange={(e) => set({ spend_cap: e.target.value === "" ? null : Number(e.target.value) })} />
      </div>
      {published && <p className="mb-0 text-xs text-muted">Published: only the name, budget, bid amount and spending limit can change here (sent to Meta first).</p>}
    </div>
  );
}
