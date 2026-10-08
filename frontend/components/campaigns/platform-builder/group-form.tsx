"use client";

import { useEffect, useState } from "react";

import { updateGroup } from "@/lib/api/ads";
import type { GroupFields, TreeGroup } from "@/lib/types/ads";

import { BudgetSchedule } from "./campaign-form";
import TargetingEditor from "./targeting-editor";
import { FieldInput, GROUP_FIELDS, useAutosave, useBuilder, visible } from "./tree";

// Group level (ad group / ad set / line item / ad squad / LinkedIn campaign):
// name, budget + schedule, audience, and the platform's delivery settings.
export default function GroupForm({ group }: { group: TreeGroup }) {
  const { tree, editable } = useBuilder();
  const [g, setG] = useState(group);
  const save = useAutosave<GroupFields>((changes) => updateGroup(group.id, changes), group.id);
  const apply = (cur: TreeGroup, changes: GroupFields): TreeGroup => ({
    ...cur,
    ...(changes.name !== undefined ? { name: changes.name } : {}),
    ...(changes.budget_mode !== undefined ? { budget_mode: changes.budget_mode } : {}),
    ...(changes.budget !== undefined ? { budget: changes.budget === null ? null : Number(changes.budget) } : {}),
    ...(changes.starts_at !== undefined ? { starts_at: changes.starts_at } : {}),
    ...(changes.ends_at !== undefined ? { ends_at: changes.ends_at } : {}),
    ...(changes.targeting ? { targeting: { ...cur.targeting, ...changes.targeting } } : {}),
    ...(changes.fields ? { fields: { ...cur.fields, ...changes.fields } } : {}),
  });
  // A newer tree from the server, plus any edits not sent yet.
  useEffect(() => setG(apply(group, save.pending())), [group]);
  const set = (changes: GroupFields) => {
    setG((cur) => apply(cur, changes));
    save(changes);
  };
  const disabled = !editable;
  const campaignBudget = tree.campaign.budget_mode !== "none";
  return (
    <div className="card">
      <h3 className="mt-0">{tree.hierarchy.group}</h3>
      <div className="form-row">
        <label htmlFor="pg_name">Name</label>
        <input
          id="pg_name"
          maxLength={255}
          disabled={disabled}
          value={g.name}
          onChange={(e) => {
            const v = e.target.value;
            if (v.trim()) set({ name: v });
            else setG((cur) => ({ ...cur, name: v }));
          }}
        />
      </div>
      {campaignBudget && <p className="m-0 mb-2 text-xs text-muted">The budget is set on the {tree.hierarchy.campaign.toLowerCase()}.</p>}
      <BudgetSchedule
        values={g}
        currency={tree.campaign.currency}
        idPrefix="pg"
        noneLabel={campaignBudget ? `Use the ${tree.hierarchy.campaign.toLowerCase()} budget` : "No budget yet"}
        disabled={disabled}
        onChange={(changes) => set(changes)}
      />
      <TargetingEditor value={g.targeting} disabled={disabled} onChange={(changes) => set({ targeting: changes })} />
      {GROUP_FIELDS[tree.platform]
        .filter((spec) => visible(spec, g.fields))
        .map((spec) => (
          <FieldInput key={spec.key} spec={spec} idPrefix="pg" disabled={disabled} value={g.fields[spec.key]} onChange={(v) => set({ fields: { [spec.key]: v } })} />
        ))}
    </div>
  );
}
