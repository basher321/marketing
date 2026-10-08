"use client";

import { useMutation } from "@tanstack/react-query";
import { useEffect, type ReactNode } from "react";

import { errorText } from "@/components/campaigns/builder/tree";
import { validatePlatformCampaign } from "@/lib/api/ads";
import { validateCampaign } from "@/lib/api/meta";
import { formatMoney } from "@/lib/format/money";
import type { Platform, PlatformTree } from "@/lib/types/ads";
import type { BuilderTree } from "@/lib/types/meta";

// Ads Manager-style stepper + Review step (SPEC-FE-049). The steps mirror the
// builder's levels; Review is a read-only summary of every level plus a real
// backend validation run. Publishing stays in the builder footer, which calls
// the backend - nothing here changes state on its own.
export type Step = "campaign" | "group" | "ad" | "review";

export function Stepper({
  labels,
  current,
  onStep,
  disabled,
}: {
  labels: Record<Step, string>;
  current: Step;
  onStep: (s: Step) => void;
  disabled?: Partial<Record<Step, boolean>>;
}) {
  const order: Step[] = ["campaign", "group", "ad", "review"];
  return (
    <ol className="m-0 mb-4 flex list-none flex-wrap items-center gap-1 p-0 text-[13px]" aria-label="Campaign steps" data-testid="builder-stepper">
      {order.map((s, i) => (
        <li key={s} className="flex items-center gap-1">
          {i > 0 && <span className="text-muted">→</span>}
          <button
            type="button"
            aria-current={current === s ? "step" : undefined}
            disabled={disabled?.[s]}
            onClick={() => onStep(s)}
            className={`rounded-md px-3 py-1.5 ${current === s ? "bg-accent text-white" : "bg-accent-soft text-text"} disabled:opacity-50`}
          >
            {i + 1}. {labels[s]}
          </button>
        </li>
      ))}
    </ol>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[180px_1fr] gap-2 border-b border-border py-1.5 text-[13px] last:border-0">
      <dt className="text-muted">{label}</dt>
      <dd className="m-0 break-words">{children}</dd>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="card mb-3" style={{ padding: 14 }}>
      <h3 className="m-0 mb-2 text-[14px]">{title}</h3>
      <dl className="m-0">{children}</dl>
    </section>
  );
}

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : "—");
const list = (xs: (string | null | undefined)[]) => xs.filter(Boolean).join(", ") || "—";
const label = (s: string | null | undefined) => (s ? s.replace(/_/g, " ").toLowerCase() : "—");

function ValidationResult({
  pending,
  error,
  issues,
}: {
  pending: boolean;
  error: unknown;
  issues: { where: string; message: string; warn?: boolean }[] | null;
}) {
  return (
    <section className="card mb-3" style={{ padding: 14 }} data-testid="review-validation">
      <h3 className="m-0 mb-2 text-[14px]">Validation</h3>
      {pending && <p className="m-0 text-xs text-muted">Checking with the platform…</p>}
      {Boolean(error) && <p className="m-0 text-xs text-danger">{errorText(error)}</p>}
      {issues && issues.length === 0 && <p className="m-0 text-xs text-success">Ready to publish: local checks and the platform&apos;s own checks passed.</p>}
      {issues && issues.length > 0 && (
        <ul className="m-0 pl-4 text-xs">
          {issues.map((i, k) => (
            <li key={k} className={i.warn ? "text-warn" : "text-danger"}>
              {i.where}: {i.message}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function MetaReview({ tree, objectiveLabel }: { tree: BuilderTree; objectiveLabel: string }) {
  const c = tree.campaign;
  const draft = c.status === "draft";
  const validate = useMutation({ mutationFn: () => validateCampaign(c.id) });
  const { mutate } = validate;
  useEffect(() => {
    if (draft) mutate();
  }, [draft, mutate]);
  const money = (v: number | null) => (v === null ? "—" : formatMoney(v, c.currency));
  return (
    <div data-testid="review-step">
      <ValidationResult
        pending={validate.isPending}
        error={validate.error}
        issues={draft ? (validate.data?.errors.map((i) => ({ where: label(i.level), message: i.message })) ?? null) : []}
      />
      <Section title="Campaign">
        <Row label="Name">{c.name}</Row>
        <Row label="Objective">{objectiveLabel}</Row>
        <Row label="Buying type">{c.buying_type}</Row>
        <Row label="Budget">{c.budget_mode === "campaign" ? `${money(c.budget)} ${c.budget_type} (campaign budget)` : "Set per ad set"}</Row>
        <Row label="Bid strategy">{label(c.bid_strategy)}</Row>
        <Row label="Special ad category">{c.special_ad_categories.length ? `${list(c.special_ad_categories.map(label))} (${list(c.special_ad_category_country)})` : "None"}</Row>
      </Section>
      {tree.ad_sets.map((s) => (
        <div key={s.id}>
          <Section title={`Ad set · ${s.name}`}>
            <Row label="Budget">{c.budget_mode === "campaign" ? "Campaign budget" : `${money(s.budget)} ${s.budget_type}`}</Row>
            <Row label="Schedule">{`${when(s.starts_at)} → ${s.ends_at ? when(s.ends_at) : "no end"}`}</Row>
            <Row label="Location">{list([...s.targeting.countries, ...s.targeting.regions.map((r) => r.name), ...s.targeting.cities.map((r) => r.name)])}</Row>
            <Row label="Audience">
              {`Age ${s.targeting.age_min}–${s.targeting.age_max}, ${s.targeting.genders}`}
              {s.targeting.detailed.length ? `, interests: ${list(s.targeting.detailed.map((d) => d.name))}` : ""}
              {s.targeting.custom_audiences.length ? `, custom: ${list(s.targeting.custom_audiences.map((d) => d.name))}` : ""}
              {s.targeting.advantage_audience ? " (Advantage+ audience)" : ""}
            </Row>
            <Row label="Placements">{s.placements.mode === "advantage" ? "Advantage+ placements" : list(s.placements.platforms)}</Row>
            <Row label="Performance goal">{label(s.optimization_goal)}</Row>
            <Row label="Conversion location">{label(s.conversion_location)}</Row>
          </Section>
          {s.ads.map((a) => (
            <Section key={a.id} title={`Ad · ${a.name}`}>
              <Row label="Identity">{a.use_instagram ? "Facebook Page + Instagram account" : "Facebook Page"}</Row>
              <Row label="Creative">{`${a.format} · ${a.format === "carousel" ? `${a.cards.length} cards` : `${a.media.length} media`}`}</Row>
              <Row label="Primary text">{a.primary_text || "—"}</Row>
              <Row label="Headline">{a.headline || "—"}</Row>
              <Row label="Call to action">{label(a.call_to_action)}</Row>
              <Row label="Destination">{a.destination.url || a.destination.app_store_url || label(a.destination.type)}</Row>
              <Row label="Tracking">{list([a.url_tags ? `URL parameters: ${a.url_tags}` : null, s.pixel_id ? `Pixel ${s.pixel_id}` : null])}</Row>
            </Section>
          ))}
        </div>
      ))}
    </div>
  );
}

function fieldRows(fields: Record<string, unknown>) {
  return Object.entries(fields)
    .filter(([, v]) => v !== null && v !== "" && !(Array.isArray(v) && v.length === 0) && typeof v !== "object")
    .map(([k, v]) => (
      <Row key={k} label={label(k)}>
        {String(v)}
      </Row>
    ));
}

export function PlatformReview({ tree, platform }: { tree: PlatformTree; platform: Platform }) {
  const c = tree.campaign;
  const draft = c.status === "draft";
  const validate = useMutation({ mutationFn: () => validatePlatformCampaign(c.id) });
  const { mutate } = validate;
  useEffect(() => {
    if (draft) mutate();
  }, [draft, mutate]);
  const money = (v: number | null) => (v === null ? "—" : formatMoney(v, c.currency));
  return (
    <div data-testid="review-step">
      <ValidationResult
        pending={validate.isPending}
        error={validate.error}
        issues={draft ? (validate.data?.issues.map((i) => ({ where: i.path, message: i.message, warn: i.severity === "warning" })) ?? null) : []}
      />
      <Section title={`Campaign · ${platform.label}`}>
        <Row label="Name">{c.name}</Row>
        <Row label="Objective">{c.objective_label}</Row>
        <Row label="Budget">{c.budget_mode === "none" ? `Set per ${platform.hierarchy.group.toLowerCase()}` : `${money(c.budget)} ${c.budget_mode}`}</Row>
        <Row label="Schedule">{`${when(c.starts_at)} → ${c.ends_at ? when(c.ends_at) : "no end"}`}</Row>
        {fieldRows(c.fields)}
      </Section>
      {tree.groups.map((g) => (
        <div key={g.id}>
          <Section title={`${platform.hierarchy.group} · ${g.name}`}>
            <Row label="Budget">{g.budget_mode === "none" || g.budget === null ? "Campaign budget" : `${money(g.budget)} ${g.budget_mode}`}</Row>
            <Row label="Schedule">{`${when(g.starts_at)} → ${g.ends_at ? when(g.ends_at) : "no end"}`}</Row>
            <Row label="Targeting">{list(Object.entries(g.targeting).map(([k, v]) => (Array.isArray(v) && v.length ? `${label(k)}: ${v.map(String).join("/")}` : null)))}</Row>
            {fieldRows(g.fields)}
          </Section>
          {g.ads.map((a) => (
            <Section key={a.id} title={`${platform.hierarchy.ad} · ${a.name}`}>
              {fieldRows(a.creative)}
            </Section>
          ))}
        </div>
      ))}
    </div>
  );
}
