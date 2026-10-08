"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

import CreativeVariants from "@/components/campaigns/creative-variants";
import { approvalKeys } from "@/lib/api/approvals";
import {
  campaignKeys,
  createAudience,
  createDraft,
  fetchAudiences,
  fetchCampaign,
  fetchDrafts,
  launchCampaign,
  updateDraft,
} from "@/lib/api/campaigns";
import { fetchCreative } from "@/lib/api/content";
import { marketingKeys, marketingListKeys } from "@/lib/api/marketing";
import type { Audience, CampaignDetail, CampaignDraftUpdate, WizardStep } from "@/lib/types/campaigns";
import { ApiError } from "@/lib/types/common";
import type { CampaignObjective } from "@/lib/types/content";
import { formatMoney } from "@/lib/format/money";

// The mockup's 6 steps (SPEC-FE-016 named them; SPEC-FE-030 builds them).
const STEPS = ["Objective", "Audience", "Creative", "Budget & Schedule", "Channels", "Review & Launch"] as const;
const FIRST_STEP_FOR: Record<WizardStep, number> = { audience: 2, creative: 3, budget: 4, channels: 5 };

const OBJECTIVES: { value: CampaignObjective; label: string }[] = [
  { value: "conversions", label: "Conversions — get purchases" },
  { value: "traffic", label: "Traffic — visits to your shop" },
  { value: "awareness", label: "Awareness — be remembered" },
  { value: "reach", label: "Reach — show to the most people" },
  { value: "engagement", label: "Engagement — likes, comments, shares" },
  { value: "message_replies", label: "Messages — start conversations" },
];
const OBJECTIVE_LABEL = Object.fromEntries(OBJECTIVES.map((o) => [o.value, o.label.split(" — ")[0]]));

const CHANNELS: { value: string; label: string }[] = [
  { value: "facebook", label: "Facebook" },
  { value: "instagram", label: "Instagram" },
  { value: "tiktok", label: "TikTok" },
  { value: "messenger", label: "Messenger" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "email", label: "Email" },
  { value: "sms", label: "SMS" },
  { value: "web", label: "Web" },
];
const CHANNEL_LABEL = Object.fromEntries(CHANNELS.map((c) => [c.value, c.label]));

// Inline controls share the .form-row input look (mockup).
const CONTROL = "rounded-md border border-border bg-panel px-3 py-2 text-[13.5px] text-text";
const FORBIDDEN = "Only managers and above can create or launch campaigns.";

/** A readable message: 403 in plain words; FastAPI 422 field errors joined; else the backend's text. */
export function errorText(err: Error, forbidden = FORBIDDEN): string {
  if (err instanceof ApiError) {
    if (err.status === 403) return forbidden;
    const detail = (err.body as { detail?: unknown } | undefined)?.detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d: { msg?: string }) => (d.msg ?? "").replace(/^Value error, /, ""))
        .filter(Boolean)
        .join(" ");
    }
  }
  return err.message;
}

export function money(amount: number, currency: string): string {
  return formatMoney(amount, currency);
}

// "daily spend 285714 > cap 5000 (BDT cents)" -> the two amounts, for a plain sentence.
function capAmounts(reason: string): { daily: number; cap: number } | null {
  const m = reason.match(/daily spend (\d+) > cap (\d+)/);
  return m ? { daily: Number(m[1]) / 100, cap: Number(m[2]) / 100 } : null;
}

// ISO (UTC) <-> <input type="datetime-local"> value in the viewer's local time.
function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function formatDateTime(iso: string | null): string {
  return iso
    ? new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
    : "—";
}

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function ErrorLine({ text }: { text: string | null | undefined }) {
  if (!text) return null;
  return (
    <p className="mb-0 mt-3 text-xs text-danger" role="alert">
      {text}
    </p>
  );
}

/**
 * "← Back" / "Continue to … →" row, the mockup's layout. `hint` says why
 * Continue is disabled (SPEC-FE-030 Amendment A); shown only while it is.
 */
export function StepNav({
  onBack,
  backLabel = "← Back",
  next,
  busy,
  disabled,
  hint,
}: {
  onBack: () => void;
  backLabel?: string;
  next: ReactNode;
  busy?: boolean;
  disabled?: boolean;
  hint?: string;
}) {
  return (
    <div className="mt-6 flex justify-between">
      <button type="button" className="btn btn-secondary" onClick={onBack} disabled={busy}>
        {backLabel}
      </button>
      <div className="flex items-center gap-3">
        {disabled && !busy && hint && (
          <span className="text-xs text-muted" role="note">
            {hint}
          </span>
        )}
        <button type="submit" className="btn" disabled={busy || disabled}>
          {busy ? "Saving…" : next}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- drafts list
function DraftsList({ onOpen, onNew }: { onOpen: (d: CampaignDetail) => void; onNew: () => void }) {
  const drafts = useQuery({ queryKey: campaignKeys.drafts, queryFn: fetchDrafts });
  return (
    <div className="card">
      <div className="flex items-center justify-between">
        <h3 className="m-0">Your drafts</h3>
        <button type="button" className="btn btn-sm" onClick={onNew}>
          + New campaign
        </button>
      </div>
      {drafts.isPending ? (
        <p className="text-[13px] text-muted">Loading drafts…</p>
      ) : drafts.isError ? (
        <p className="text-[13px] text-danger" role="alert">
          Failed to load drafts: {drafts.error.message}
        </p>
      ) : drafts.data.length === 0 ? (
        <p className="text-[13px] text-muted">No drafts yet — start a new campaign.</p>
      ) : (
        <table className="mt-3">
          <thead>
            <tr>
              <th>Campaign</th>
              <th>Objective</th>
              <th>Next step</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {drafts.data.map((d) => (
              <tr key={d.id}>
                <td>{d.name}</td>
                <td>{OBJECTIVE_LABEL[d.objective] ?? d.objective}</td>
                <td>
                  {d.pending_approval_id ? (
                    <span className="badge badge-warn">Awaiting owner approval</span>
                  ) : d.missing.length ? (
                    STEPS[FIRST_STEP_FOR[d.missing[0]] - 1]
                  ) : (
                    "Review & Launch"
                  )}
                </td>
                <td>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => onOpen(d)}>
                    Continue
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- step 1
function StepObjective({
  draft,
  onBack,
  onSaved,
}: {
  draft: CampaignDetail | null;
  onBack: () => void;
  onSaved: (d: CampaignDetail) => void;
}) {
  const [name, setName] = useState(draft?.name ?? "");
  const [objective, setObjective] = useState<CampaignObjective>(draft?.objective ?? "conversions");
  const [description, setDescription] = useState(draft?.description ?? "");
  const save = useMutation({
    mutationFn: () => {
      const body = { name: name.trim(), objective, description: description.trim() || null };
      return draft ? updateDraft(draft.id, body) : createDraft(body);
    },
    onSuccess: onSaved,
  });
  return (
    <form
      className="card"
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <h3 className="mt-0">What's the goal of this campaign?</h3>
      <div className="form-row">
        <label htmlFor="cw_name">Campaign name</label>
        <input id="cw_name" required maxLength={255} placeholder="e.g. Eid Sale 2026" value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <fieldset className="form-row border-none p-0">
        <legend className="mb-1.5 text-[13px] font-medium">Objective</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {OBJECTIVES.map((o) => (
            <label
              key={o.value}
              className={`flex cursor-pointer items-center gap-2 rounded-md border p-3 text-[13px] font-normal ${
                objective === o.value ? "border-accent bg-accent-soft" : "border-border"
              }`}
            >
              <input type="radio" name="cw_objective" checked={objective === o.value} onChange={() => setObjective(o.value)} />
              {o.label}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="form-row">
        <label htmlFor="cw_desc">Description (optional)</label>
        <textarea id="cw_desc" rows={2} maxLength={2000} value={description} onChange={(e) => setDescription(e.target.value)} />
      </div>
      <ErrorLine text={save.error && errorText(save.error)} />
      <StepNav onBack={onBack} backLabel="← Drafts" next="Continue to Audience →" busy={save.isPending} />
    </form>
  );
}

// ---------------------------------------------------------------- step 2
function audienceSummary(a: Audience): string {
  const t = a.targeting;
  const where = [t.countries.join(", "), t.regions.length ? t.regions.join(", ") : null].filter(Boolean).join(" · ");
  const gender = t.genders.length === 1 ? (t.genders[0] === "male" ? "Men" : "Women") : "All genders";
  const extra = t.interests.length ? ` · Interests: ${t.interests.join(", ")}` : "";
  return `${where} · Age ${t.age_min}–${t.age_max} · ${gender}${extra}`;
}

function NewAudienceForm({ onCreated, onCancel }: { onCreated: (a: Audience) => void; onCancel: () => void }) {
  const queryClient = useQueryClient();
  const [f, setF] = useState({ name: "", countries: "BD", regions: "", age_min: "18", age_max: "65", gender: "all", interests: "", languages: "" });
  const set = (k: keyof typeof f, v: string) => setF((cur) => ({ ...cur, [k]: v }));
  const create = useMutation({
    mutationFn: () =>
      createAudience({
        name: f.name.trim(),
        description: null,
        targeting: {
          countries: splitList(f.countries).map((c) => c.toUpperCase()),
          regions: splitList(f.regions),
          age_min: Number(f.age_min),
          age_max: Number(f.age_max),
          genders: f.gender === "all" ? [] : [f.gender as "male" | "female"],
          interests: splitList(f.interests),
          languages: splitList(f.languages),
        },
      }),
    onSuccess: (a) => {
      void queryClient.invalidateQueries({ queryKey: campaignKeys.audiences });
      onCreated(a);
    },
  });
  // A nested form isn't allowed, so this block submits through its own button.
  return (
    <div className="mt-3 rounded-md border border-border p-4">
      <div className="form-grid-2">
        <div className="form-row">
          <label htmlFor="au_name">Audience name</label>
          <input id="au_name" maxLength={255} placeholder="e.g. Dhaka women 18–35" value={f.name} onChange={(e) => set("name", e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor="au_countries">Countries (comma-separated codes)</label>
          <input id="au_countries" value={f.countries} onChange={(e) => set("countries", e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor="au_regions">Regions / cities (optional)</label>
          <input id="au_regions" placeholder="Dhaka, Chattogram" value={f.regions} onChange={(e) => set("regions", e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor="au_gender">Gender</label>
          <select id="au_gender" value={f.gender} onChange={(e) => set("gender", e.target.value)}>
            <option value="all">All</option>
            <option value="female">Women</option>
            <option value="male">Men</option>
          </select>
        </div>
        <div className="form-row">
          <label htmlFor="au_age_min">Age from</label>
          <input id="au_age_min" type="number" min={13} max={65} value={f.age_min} onChange={(e) => set("age_min", e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor="au_age_max">Age to</label>
          <input id="au_age_max" type="number" min={13} max={65} value={f.age_max} onChange={(e) => set("age_max", e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor="au_interests">Interests (optional, comma-separated)</label>
          <input id="au_interests" placeholder="Fashion, Modest wear" value={f.interests} onChange={(e) => set("interests", e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor="au_languages">Languages (optional, e.g. bn, en)</label>
          <input id="au_languages" value={f.languages} onChange={(e) => set("languages", e.target.value)} />
        </div>
      </div>
      <p className="m-0 mb-3 text-xs text-muted">Estimated size: — (no ad-platform data connected to estimate reach)</p>
      <div className="flex gap-2">
        <button type="button" className="btn btn-sm" disabled={create.isPending || !f.name.trim()} onClick={() => create.mutate()}>
          {create.isPending ? "Saving…" : "Save audience"}
        </button>
        <button type="button" className="btn btn-secondary btn-sm" disabled={create.isPending} onClick={onCancel}>
          Cancel
        </button>
      </div>
      <ErrorLine text={create.error && errorText(create.error)} />
    </div>
  );
}

function StepAudience({ draft, onBack, onSaved }: { draft: CampaignDetail; onBack: () => void; onSaved: (d: CampaignDetail) => void }) {
  const audiences = useQuery({ queryKey: campaignKeys.audiences, queryFn: fetchAudiences });
  const [selected, setSelected] = useState<string | null>(draft.audience_id);
  const [adding, setAdding] = useState(false);
  // With no saved audiences there is nothing to pick, so the new-audience form
  // opens by itself, once (Cancel keeps it closed). SPEC-FE-030 Amendment A.
  const autoOpened = useRef(false);
  useEffect(() => {
    if (!autoOpened.current && audiences.data && audiences.data.items.length === 0) {
      autoOpened.current = true;
      setAdding(true);
    }
  }, [audiences.data]);
  const save = useMutation({ mutationFn: () => updateDraft(draft.id, { audience_id: selected }), onSuccess: onSaved });
  // A newly saved audience is attached to the draft right away, so Back (which
  // doesn't save) can't drop it (SPEC-FE-030 Amendment C).
  const queryClient = useQueryClient();
  const attach = useMutation({
    mutationFn: (audienceId: string) => updateDraft(draft.id, { audience_id: audienceId }),
    onSuccess: (d) => queryClient.setQueryData(campaignKeys.detail(d.id), d),
  });
  return (
    <form
      className="card"
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <h3 className="mt-0">Who should see your ads?</h3>
      {audiences.isPending ? (
        <p className="text-[13px] text-muted">Loading audiences…</p>
      ) : audiences.isError ? (
        <p className="text-[13px] text-danger" role="alert">
          Failed to load audiences: {audiences.error.message}
        </p>
      ) : audiences.data.items.length === 0 && !adding ? (
        <p className="text-[13px] text-muted">No saved audiences yet — create one below.</p>
      ) : (
        <div className="grid gap-2">
          {audiences.data.items.map((a) => (
            <label
              key={a.id}
              className={`flex cursor-pointer items-start gap-2 rounded-md border p-3 text-[13px] font-normal ${
                selected === a.id ? "border-accent bg-accent-soft" : "border-border"
              }`}
            >
              <input type="radio" name="cw_audience" className="mt-1" checked={selected === a.id} onChange={() => setSelected(a.id)} />
              <span>
                <b>{a.name}</b>
                <br />
                <span className="text-xs text-muted">{audienceSummary(a)}</span>
              </span>
            </label>
          ))}
        </div>
      )}
      {adding ? (
        <NewAudienceForm
          onCreated={(a) => {
            setSelected(a.id);
            setAdding(false);
            attach.mutate(a.id);
          }}
          onCancel={() => setAdding(false)}
        />
      ) : (
        <button type="button" className="btn btn-secondary btn-sm mt-3" onClick={() => setAdding(true)}>
          + New audience
        </button>
      )}
      <ErrorLine text={(attach.error && errorText(attach.error)) || (save.error && errorText(save.error))} />
      <StepNav
        onBack={onBack}
        next="Continue to Creative →"
        busy={save.isPending}
        disabled={!selected}
        hint={adding ? "Save the new audience to continue" : "Select an audience to continue"}
      />
    </form>
  );
}

// ---------------------------------------------------------------- step 4
function StepBudget({ draft, onBack, onSaved }: { draft: CampaignDetail; onBack: () => void; onSaved: (d: CampaignDetail) => void }) {
  const [current, setCurrent] = useState(draft);
  const [budget, setBudget] = useState(draft.total_budget ? String(draft.total_budget) : "");
  const [start, setStart] = useState(toLocalInput(draft.starts_at));
  const [end, setEnd] = useState(toLocalInput(draft.ends_at));
  const body = (): CampaignDraftUpdate => ({
    total_budget: Number(budget),
    starts_at: new Date(start).toISOString(),
    ends_at: new Date(end).toISOString(),
  });
  const valid = Number(budget) > 0 && !!start && !!end;

  // The daily amount and approval note are the backend's own numbers: the
  // entries are saved (debounced) whenever all three are filled in.
  const estimate = useMutation({ mutationFn: () => updateDraft(draft.id, body()), onSuccess: setCurrent });
  const lastSent = useRef("");
  useEffect(() => {
    if (!valid) return;
    const key = `${budget}|${start}|${end}`;
    if (key === lastSent.current) return;
    const id = setTimeout(() => {
      lastSent.current = key;
      estimate.mutate();
    }, 600);
    return () => clearTimeout(id);
    // Intentionally keyed on the inputs only (estimate/body are recreated each render).
  }, [budget, start, end, valid]);

  const save = useMutation({ mutationFn: () => updateDraft(draft.id, body()), onSuccess: onSaved });
  const over = current.approval?.required ? capAmounts(current.approval.reason) : null;
  const showEstimate = !estimate.isError && current.duration_days && current.total_budget > 0;

  return (
    <form
      className="card"
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <h3 className="mt-0">Budget & schedule</h3>
      <div className="form-grid-2">
        <div className="form-row">
          <label htmlFor="cw_budget">Total budget ({current.currency})</label>
          <input id="cw_budget" type="number" required min={1} step="0.01" value={budget} onChange={(e) => setBudget(e.target.value)} />
        </div>
        <div />
        <div className="form-row">
          <label htmlFor="cw_start">Start</label>
          <input id="cw_start" type="datetime-local" required value={start} onChange={(e) => setStart(e.target.value)} />
        </div>
        <div className="form-row">
          <label htmlFor="cw_end">End</label>
          <input id="cw_end" type="datetime-local" required value={end} onChange={(e) => setEnd(e.target.value)} />
        </div>
      </div>
      {showEstimate && (
        <p className="m-0 text-[13px]" data-testid="budget-estimate">
          {/* The backend counts calendar days in the tenant timezone, inclusive
              (SPEC-BE-044), so 10:00 → 10:00 a week later is 8 calendar days. */}
          ≈ <b>{money(current.daily_budget, current.currency)}/day</b> over {current.duration_days}{" "}
          {current.duration_days === 1 ? "calendar day" : "calendar days"}
        </p>
      )}
      {showEstimate && over && (
        <p className="mb-0 mt-2 text-[13px] text-warn" role="note">
          Launch needs owner approval: daily spend {money(over.daily, current.currency)} exceeds your{" "}
          {money(over.cap, current.currency)}/day cap. (When the owner launches, that counts as approval.)
        </p>
      )}
      <ErrorLine text={(estimate.error && errorText(estimate.error)) || (save.error && errorText(save.error))} />
      <StepNav
        onBack={onBack}
        next="Continue to Channels →"
        busy={save.isPending}
        disabled={!valid}
        hint="Enter a total budget and both dates to continue"
      />
    </form>
  );
}

// ---------------------------------------------------------------- step 5
function StepChannels({ draft, onBack, onSaved }: { draft: CampaignDetail; onBack: () => void; onSaved: (d: CampaignDetail) => void }) {
  // Facebook + Instagram are pre-checked on a draft with no channels yet.
  const [channels, setChannels] = useState<string[]>(draft.channels.length ? draft.channels : ["facebook", "instagram"]);
  const toggle = (c: string) => setChannels((cur) => (cur.includes(c) ? cur.filter((x) => x !== c) : [...cur, c]));
  const save = useMutation({ mutationFn: () => updateDraft(draft.id, { channels }), onSuccess: onSaved });
  return (
    <form
      className="card"
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <h3 className="mt-0">Where should the ads run?</h3>
      <div className="flex flex-wrap gap-3 text-[13px]">
        {CHANNELS.map((c) => (
          <label key={c.value} className="flex items-center gap-1.5 font-normal">
            <input type="checkbox" checked={channels.includes(c.value)} onChange={() => toggle(c.value)} />
            {c.label}
          </label>
        ))}
      </div>
      <ErrorLine text={save.error && errorText(save.error)} />
      <StepNav
        onBack={onBack}
        next="Continue to Review →"
        busy={save.isPending}
        disabled={channels.length === 0}
        hint="Pick at least one channel to continue"
      />
    </form>
  );
}

// ---------------------------------------------------------------- step 6
function ReviewRow({ label, value, onEdit }: { label: string; value: ReactNode; onEdit: () => void }) {
  return (
    <tr>
      <td className="w-40 align-top text-muted">{label}</td>
      <td>{value}</td>
      <td className="w-16 text-right align-top">
        <button type="button" className="btn btn-ghost btn-sm" onClick={onEdit}>
          Edit
        </button>
      </td>
    </tr>
  );
}

function StepReview({
  draft,
  onBack,
  goTo,
  onLaunched,
}: {
  draft: CampaignDetail;
  onBack: () => void;
  goTo: (step: number) => void;
  onLaunched: (d: CampaignDetail) => void;
}) {
  const audiences = useQuery({ queryKey: campaignKeys.audiences, queryFn: fetchAudiences });
  const creative = useQuery({
    queryKey: ["content", "creative", draft.creative_asset_id],
    queryFn: () => fetchCreative(draft.creative_asset_id!),
    enabled: !!draft.creative_asset_id,
  });
  const launch = useMutation({ mutationFn: () => launchCampaign(draft.id), onSuccess: onLaunched });
  const audience = audiences.data?.items.find((a) => a.id === draft.audience_id);
  const variant =
    creative.data && creative.data.selected_variant_index !== null
      ? creative.data.variants[creative.data.selected_variant_index]
      : null;
  const over = draft.approval?.required ? capAmounts(draft.approval.reason) : null;

  return (
    <div className="card">
      <h3 className="mt-0">Review & launch</h3>
      <table>
        <tbody>
          <ReviewRow
            label="Objective"
            value={
              <>
                <b>{draft.name}</b> · {OBJECTIVE_LABEL[draft.objective] ?? draft.objective}
                {draft.description && <div className="text-xs text-muted">{draft.description}</div>}
              </>
            }
            onEdit={() => goTo(1)}
          />
          <ReviewRow
            label="Audience"
            value={audience ? <>{audience.name} <div className="text-xs text-muted">{audienceSummary(audience)}</div></> : "—"}
            onEdit={() => goTo(2)}
          />
          <ReviewRow
            label="Creative"
            value={variant ? <>&ldquo;{variant.headline}&rdquo; <div className="text-xs text-muted">{variant.description}</div></> : "—"}
            onEdit={() => goTo(3)}
          />
          <ReviewRow
            label="Budget & schedule"
            value={
              draft.duration_days ? (
                <>
                  {money(draft.total_budget, draft.currency)} total · ≈ {money(draft.daily_budget, draft.currency)}/day
                  <div className="text-xs text-muted">
                    {formatDateTime(draft.starts_at)} → {formatDateTime(draft.ends_at)} ({draft.duration_days}{" "}
                    {draft.duration_days === 1 ? "calendar day" : "calendar days"})
                  </div>
                </>
              ) : (
                "—"
              )
            }
            onEdit={() => goTo(4)}
          />
          <ReviewRow
            label="Channels"
            value={draft.channels.length ? draft.channels.map((c) => CHANNEL_LABEL[c] ?? c).join(", ") : "—"}
            onEdit={() => goTo(5)}
          />
        </tbody>
      </table>

      {over && (
        <p className="mb-0 mt-4 text-[13px] text-warn" role="note">
          Needs owner approval: daily spend {money(over.daily, draft.currency)} exceeds your {money(over.cap, draft.currency)}/day cap.
          If you're the owner, launching counts as approval; otherwise it's sent to the Approvals panel.
        </p>
      )}
      <p className="mb-0 mt-3 text-xs text-muted">
        This records the campaign as live in AI Orchestrator. Publishing to Facebook/Instagram/TikTok ad accounts isn&apos;t
        connected yet.
      </p>
      {draft.missing.length > 0 && (
        <p className="mb-0 mt-3 text-[13px] text-danger">
          Still missing: {draft.missing.map((m) => STEPS[FIRST_STEP_FOR[m] - 1]).join(", ")}
        </p>
      )}
      {draft.pending_approval_id && (
        <p className="mb-0 mt-3 text-[13px]">
          <span className="badge badge-warn">Awaiting owner approval</span> The owner can approve it in Command Chat › Approvals.
        </p>
      )}
      <ErrorLine text={launch.error && errorText(launch.error)} />
      <div className="mt-6 flex justify-between">
        <button type="button" className="btn btn-secondary" onClick={onBack} disabled={launch.isPending}>
          ← Back
        </button>
        <button
          type="button"
          className="btn"
          disabled={launch.isPending || draft.missing.length > 0 || !!draft.pending_approval_id}
          onClick={() => launch.mutate()}
        >
          {launch.isPending ? "Launching…" : "Launch campaign"}
        </button>
      </div>
    </div>
  );
}

function LaunchResult({ campaign, onDone }: { campaign: CampaignDetail; onDone: () => void }) {
  const live = campaign.status !== "draft";
  return (
    <div className="card">
      <h3 className="mt-0">{live ? "Campaign launched" : "Sent for owner approval"}</h3>
      {live ? (
        <p className="text-[13px]">
          <b>{campaign.name}</b> is now <span className="badge badge-success">{campaign.status}</span>. It appears in{" "}
          <Link href="/marketing" className="text-accent">
            Marketing › Active Campaigns
          </Link>
          .
        </p>
      ) : (
        <p className="text-[13px]">
          <b>{campaign.name}</b> is over the daily ad cap, so the owner must approve it. It&apos;s waiting in{" "}
          <Link href="/chat" className="text-accent">
            Command Chat › Approvals
          </Link>
          ; approving it launches the campaign.
        </p>
      )}
      <button type="button" className="btn btn-secondary btn-sm" onClick={onDone}>
        Back to drafts
      </button>
    </div>
  );
}

// ---------------------------------------------------------------- wizard
// Campaign Wizard (SPEC-FE-030): 1 Objective → 2 Audience → 3 Creative →
// 4 Budget & Schedule → 5 Channels → 6 Review & Launch. Every Continue saves
// the step to the draft (backend SPEC-BE-044); the draft id lives in the URL
// (?draft=<id>) so a reload resumes the same draft.
export default function CampaignWizard() {
  const router = useRouter();
  const params = useSearchParams();
  const queryClient = useQueryClient();
  const draftId = params.get("draft");
  const [step, setStep] = useState(0);
  const [launched, setLaunched] = useState<CampaignDetail | null>(null);
  const draft = useQuery({ queryKey: campaignKeys.detail(draftId ?? ""), queryFn: () => fetchCampaign(draftId!), enabled: !!draftId });

  // Opening a draft (or reloading with ?draft=) jumps to its first missing step.
  const opened = useRef<string | null>(null);
  useEffect(() => {
    if (!draft.data || opened.current === draft.data.id) return;
    opened.current = draft.data.id;
    setStep(draft.data.missing.length ? FIRST_STEP_FOR[draft.data.missing[0]] : 6);
  }, [draft.data]);

  const setDraftParam = (id: string | null) => router.replace(id ? `/marketing/paid?draft=${id}` : "/marketing/paid");
  const saved = (d: CampaignDetail, next: number) => {
    queryClient.setQueryData(campaignKeys.detail(d.id), d);
    void queryClient.invalidateQueries({ queryKey: campaignKeys.drafts });
    if (d.id !== draftId) {
      opened.current = d.id; // a fresh draft: stay on the flow, don't re-jump
      setDraftParam(d.id);
    }
    setStep(next);
  };
  const toList = () => {
    opened.current = null;
    setLaunched(null);
    setStep(0);
    setDraftParam(null);
  };

  const current = draft.data ?? null;
  const subtitle = step === 0 || launched ? "Plan, create and launch an ad campaign." : `Step ${step} of 6 — ${STEPS[step - 1]}`;

  let body: ReactNode;
  if (launched) {
    body = <LaunchResult campaign={launched} onDone={toList} />;
  } else if (step === 0 && !draftId) {
    body = (
      <DraftsList
        onOpen={(d) => {
          opened.current = null;
          setDraftParam(d.id);
        }}
        onNew={() => setStep(1)}
      />
    );
  } else if (draftId && (draft.isPending || (step === 0 && !draft.isError))) {
    body = <p className="text-[13px] text-muted">Loading campaign…</p>;
  } else if (draftId && draft.isError) {
    body = (
      <p className="text-[13px] text-danger" role="alert">
        Failed to load the campaign: {draft.error.message}
      </p>
    );
  } else if (current && current.status !== "draft") {
    body = <LaunchResult campaign={current} onDone={toList} />;
  } else if (step === 1 || !current) {
    body = <StepObjective key={current?.id ?? "new"} draft={current} onBack={toList} onSaved={(d) => saved(d, 2)} />;
  } else if (step === 2) {
    body = <StepAudience draft={current} onBack={() => setStep(1)} onSaved={(d) => saved(d, 3)} />;
  } else if (step === 3) {
    body = <CreativeVariants draft={current} onBack={() => setStep(2)} onSaved={(d) => saved(d, 4)} />;
  } else if (step === 4) {
    body = <StepBudget draft={current} onBack={() => setStep(3)} onSaved={(d) => saved(d, 5)} />;
  } else if (step === 5) {
    body = <StepChannels draft={current} onBack={() => setStep(4)} onSaved={(d) => saved(d, 6)} />;
  } else {
    body = (
      <StepReview
        draft={current}
        onBack={() => setStep(5)}
        goTo={setStep}
        onLaunched={(d) => {
          queryClient.setQueryData(campaignKeys.detail(d.id), d);
          void queryClient.invalidateQueries({ queryKey: campaignKeys.drafts });
          void queryClient.invalidateQueries({ queryKey: marketingListKeys.campaigns });
          void queryClient.invalidateQueries({ queryKey: marketingKeys.all });
          void queryClient.invalidateQueries({ queryKey: approvalKeys.all });
          setLaunched(d);
        }}
      />
    );
  }

  const filled = launched || step === 0 ? 0 : step;
  return (
    <>
      <h1 className="m-0 mb-1 text-[22px] font-bold">{"Campaign Wizard"}</h1>
      <p className="m-0 mb-5 text-muted">{subtitle}</p>
      <div className="mb-6 flex gap-1">
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <div key={i} className={`h-1 flex-1 rounded-sm ${i < filled ? "bg-accent" : "bg-border"}`} />
        ))}
      </div>
      {body}
    </>
  );
}
