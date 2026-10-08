"use client";

import { useEffect, useState } from "react";

import { updatePlatformCampaign } from "@/lib/api/ads";
import type { BudgetMode, CampaignFields } from "@/lib/types/ads";

import { CAMPAIGN_FIELDS, FieldInput, useAutosave, useBuilder, visible } from "./tree";

/** ISO (UTC) -> the value a datetime-local input shows, in the browser's zone. */
export function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export const fromLocalInput = (v: string): string | null => (v ? new Date(v).toISOString() : null);

type BudgetValues = { budget_mode: BudgetMode; budget: number | null; starts_at: string | null; ends_at: string | null };

// Budget + schedule, shared by the campaign and group forms. "none" means the
// budget lives on the other level (e.g. set per ad group).
export function BudgetSchedule({ values, currency, onChange, idPrefix, noneLabel, disabled }: {
  values: BudgetValues;
  currency: string;
  onChange: (changes: { budget_mode?: BudgetMode; budget?: string | null; starts_at?: string | null; ends_at?: string | null }) => void;
  idPrefix: string;
  noneLabel: string;
  disabled: boolean;
}) {
  return (
    <div className="grid gap-x-4 sm:grid-cols-2">
      <div className="form-row">
        <label htmlFor={`${idPrefix}_bm`}>Budget</label>
        <select id={`${idPrefix}_bm`} value={values.budget_mode} disabled={disabled} onChange={(e) => onChange({ budget_mode: e.target.value as BudgetMode })}>
          <option value="none">{noneLabel}</option>
          <option value="daily">Daily budget</option>
          <option value="total">Total (lifetime) budget</option>
        </select>
      </div>
      {values.budget_mode !== "none" && (
        <div className="form-row">
          <label htmlFor={`${idPrefix}_b`}>Amount ({currency})</label>
          <input
            id={`${idPrefix}_b`}
            type="number"
            min={0}
            step="0.01"
            disabled={disabled}
            value={values.budget ?? ""}
            onChange={(e) => onChange({ budget: e.target.value === "" ? null : e.target.value })}
          />
        </div>
      )}
      <div className="form-row">
        <label htmlFor={`${idPrefix}_s`}>Start</label>
        <input id={`${idPrefix}_s`} type="datetime-local" disabled={disabled} value={toLocalInput(values.starts_at)} onChange={(e) => onChange({ starts_at: fromLocalInput(e.target.value) })} />
      </div>
      <div className="form-row">
        <label htmlFor={`${idPrefix}_e`}>End {values.budget_mode === "total" ? "(required for a total budget)" : "(optional)"}</label>
        <input id={`${idPrefix}_e`} type="datetime-local" disabled={disabled} value={toLocalInput(values.ends_at)} onChange={(e) => onChange({ ends_at: fromLocalInput(e.target.value) })} />
      </div>
    </div>
  );
}

// Campaign level (SPEC-FE-045): name, objective, campaign type (Google,
// YouTube), budget/schedule and the platform's own campaign settings.
export default function CampaignForm() {
  const { tree, platform, editable } = useBuilder();
  const c = tree.campaign;
  const [f, setF] = useState(c);
  const save = useAutosave<CampaignFields>((changes) => updatePlatformCampaign(c.id, changes), c.id);
  const apply = (cur: typeof c, changes: CampaignFields): typeof c => ({
    ...cur,
    ...(changes.name !== undefined ? { name: changes.name } : {}),
    ...(changes.objective !== undefined ? { objective: changes.objective } : {}),
    ...(changes.campaign_type !== undefined ? { campaign_type: changes.campaign_type } : {}),
    ...(changes.budget_mode !== undefined ? { budget_mode: changes.budget_mode } : {}),
    ...(changes.budget !== undefined ? { budget: changes.budget === null ? null : Number(changes.budget) } : {}),
    ...(changes.starts_at !== undefined ? { starts_at: changes.starts_at } : {}),
    ...(changes.ends_at !== undefined ? { ends_at: changes.ends_at } : {}),
    ...(changes.fields ? { fields: { ...cur.fields, ...changes.fields } } : {}),
  });
  // A newer tree from the server, plus any edits not sent yet.
  useEffect(() => setF(apply(tree.campaign, save.pending())), [tree.campaign]);
  const set = (changes: CampaignFields) => {
    setF((cur) => apply(cur, changes));
    save(changes);
  };
  const values = { ...f.fields, campaign_type: f.campaign_type };
  const disabled = !editable;
  return (
    <div className="card">
      <h3 className="mt-0">{tree.hierarchy.campaign}</h3>
      <div className="form-row">
        <label htmlFor="pc_name">Name</label>
        <input id="pc_name" maxLength={255} disabled={disabled} value={f.name}
          onChange={(e) => {
            // An empty name isn't saved (the backend requires one), but can be typed over.
            const v = e.target.value;
            if (v.trim()) set({ name: v });
            else setF((cur) => ({ ...cur, name: v }));
          }}
        />
      </div>
      <div className="grid gap-x-4 sm:grid-cols-2">
        <div className="form-row">
          <label htmlFor="pc_obj">Objective</label>
          <select id="pc_obj" disabled={disabled} value={f.objective} onChange={(e) => set({ objective: e.target.value })}>
            {platform.objectives.map((o) => (
              <option key={o.key} value={o.key} disabled={!o.available}>
                {o.label}
                {o.available ? "" : " (unavailable)"}
              </option>
            ))}
          </select>
        </div>
        {platform.campaign_types.length > 0 && (
          <div className="form-row">
            <label htmlFor="pc_type">Campaign type</label>
            <select id="pc_type" disabled={disabled} value={f.campaign_type ?? ""} onChange={(e) => set({ campaign_type: e.target.value || null })}>
              <option value="">Choose…</option>
              {platform.campaign_types.map((o) => (
                <option key={o.key} value={o.key} disabled={!o.available}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>
      <BudgetSchedule
        values={f}
        currency={c.currency}
        idPrefix="pc"
        noneLabel={`Set per ${tree.hierarchy.group.toLowerCase()}`}
        disabled={disabled}
        onChange={(changes) => set(changes)}
      />
      {CAMPAIGN_FIELDS[tree.platform]
        .filter((spec) => visible(spec, values))
        .map((spec) => (
          <FieldInput key={spec.key} spec={spec} idPrefix="pc" disabled={disabled} value={f.fields[spec.key]} onChange={(v) => set({ fields: { [spec.key]: v } })} />
        ))}
    </div>
  );
}
