"use client";

import { useState, type FormEvent } from "react";

import type { JobSchedule, PlanAction, PlanItem, PlanRead, RunMode } from "@/lib/types/orchestrator";

// Job list editing (SPEC-FE-065): job / item forms, "+ Add job", the run
// settings panel and the submit sheet. Times are typed and shown in the
// company's timezone (the backend reads a time without offset as company time).

const NUMERIC = new Set([
  "price", "compare_at_price", "count", "budget", "duration_s", "duration_days", "weight_grams", "value", "threshold",
  "rate", "free_over", "new_on_hand", "age_min", "age_max",
]);

export function fmtTime(iso: string | null | undefined, tz: string | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  try {
    return new Intl.DateTimeFormat(undefined, { timeZone: tz, month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(d);
  } catch {
    return d.toLocaleString();
  }
}

/** ISO instant -> "YYYY-MM-DDTHH:MM" in the company timezone (for datetime-local). */
export function toLocalInput(iso: string | null | undefined, tz: string | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  try {
    const parts = Object.fromEntries(
      new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
        .formatToParts(d)
        .map((p) => [p.type, p.value]),
    );
    return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
  } catch {
    return "";
  }
}

function asText(v: unknown): string {
  if (v === null || v === undefined) return "";
  return typeof v === "object" ? JSON.stringify(v) : String(v);
}

function parseValue(key: string, raw: string, original: unknown): unknown {
  const t = raw.trim();
  if (t === "") return undefined;
  if (typeof original === "number" || (original === undefined && NUMERIC.has(key))) {
    const n = Number(t);
    return Number.isFinite(n) ? n : t;
  }
  if (typeof original === "boolean") return t === "true";
  if ((typeof original === "object" && original !== null) || /^[[{]/.test(t)) {
    try {
      return JSON.parse(t);
    } catch {
      throw new SyntaxError(`“${key.replace(/_/g, " ")}” isn't valid JSON.`);
    }
  }
  return t;
}

/** Edit one job: its params (missing fields added and highlighted) and its run time. */
export function JobForm({
  job,
  tz,
  busy,
  error,
  onSave,
  onCancel,
  saveLabel = "Save job",
}: {
  job: Pick<PlanAction, "params" | "missing" | "run_at" | "type" | "label">;
  tz: string | undefined;
  busy: boolean;
  error: string | null;
  onSave: (params: Record<string, unknown>, runAt: string | null) => void;
  onCancel: () => void;
  /** SPEC-FE-067: "Save & retry" for a failed job. */
  saveLabel?: string;
}) {
  const missing = (job.missing ?? []).map((m) => m.field.split(".")[0]);
  const keys = Array.from(new Set([...Object.keys(job.params), ...missing]));
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(keys.map((k) => [k, asText(job.params[k])])));
  const [runAt, setRunAt] = useState(toLocalInput(job.run_at, tz));
  const [localErr, setLocalErr] = useState<string | null>(null);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    try {
      const params: Record<string, unknown> = {};
      for (const k of keys) {
        const v = parseValue(k, values[k] ?? "", job.params[k]);
        if (v !== undefined) params[k] = v;
      }
      setLocalErr(null);
      onSave(params, runAt || null);
    } catch (err) {
      setLocalErr(err instanceof Error ? err.message : String(err));
    }
  };
  return (
    <form onSubmit={submit} className="cc-job-form" data-testid="job-form">
      {keys.map((k) => {
        const need = job.missing?.find((m) => m.field.split(".")[0] === k);
        const long = (values[k] ?? "").length > 60 || ["brief", "details", "prompt", "message", "caption"].includes(k);
        return (
          <label key={k} className={`grid gap-1 text-xs ${need ? "cc-need" : ""}`}>
            <span className="text-muted">
              {k.replace(/_/g, " ")}
              {need && <b className="ml-1 text-warn">· {need.question}</b>}
            </span>
            {long ? (
              <textarea rows={3} value={values[k] ?? ""} onChange={(e) => setValues((v) => ({ ...v, [k]: e.target.value }))} />
            ) : (
              <input value={values[k] ?? ""} onChange={(e) => setValues((v) => ({ ...v, [k]: e.target.value }))} />
            )}
          </label>
        );
      })}
      <label className="grid gap-1 text-xs">
        <span className="text-muted">run at (company time; empty = by the list's schedule)</span>
        <input type="datetime-local" value={runAt} onChange={(e) => setRunAt(e.target.value)} />
      </label>
      {(localErr || error) && (
        <p className="m-0 text-xs text-danger" role="alert">
          {localErr || error}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <button type="button" className="btn btn-secondary btn-sm" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="btn btn-sm" disabled={busy}>
          {busy ? "Saving…" : saveLabel}
        </button>
      </div>
    </form>
  );
}

/** Edit an item's fields; its jobs are rebuilt by the backend. */
export function ItemForm({ item, busy, error, onSave, onCancel }: {
  item: PlanItem;
  busy: boolean;
  error: string | null;
  onSave: (fields: Record<string, unknown>) => void;
  onCancel: () => void;
}) {
  const [rows, setRows] = useState<[string, string][]>(() => Object.entries(item.fields).map(([k, v]) => [k, asText(v)]));
  return (
    <form
      className="cc-job-form"
      onSubmit={(e) => {
        e.preventDefault();
        onSave(Object.fromEntries(rows.filter(([k]) => k.trim()).map(([k, v]) => [k.trim(), typeof item.fields[k] === "number" && v.trim() !== "" && Number.isFinite(Number(v)) ? Number(v) : v])));
      }}
    >
      {rows.map(([k, v], i) => (
        <div key={i} className="grid grid-cols-[minmax(90px,30%)_1fr_auto] items-center gap-1.5 text-xs">
          <input value={k} aria-label="Field name" onChange={(e) => setRows((r) => r.map((x, j) => (j === i ? [e.target.value, x[1]] : x)))} />
          <input value={v} aria-label={`${k} value`} onChange={(e) => setRows((r) => r.map((x, j) => (j === i ? [x[0], e.target.value] : x)))} />
          <button type="button" className="cc-link" aria-label="Remove field" onClick={() => setRows((r) => r.filter((_, j) => j !== i))}>
            ✕
          </button>
        </div>
      ))}
      <button type="button" className="cc-link self-start text-accent" onClick={() => setRows((r) => [...r, ["", ""]])}>
        + Add field
      </button>
      {error && <p className="m-0 text-xs text-danger" role="alert">{error}</p>}
      <div className="flex justify-end gap-2">
        <button type="button" className="btn btn-secondary btn-sm" onClick={onCancel}>Cancel</button>
        <button type="submit" className="btn btn-sm" disabled={busy}>{busy ? "Saving…" : "Save item"}</button>
      </div>
    </form>
  );
}

// The actions people add most often, with starter params. The backend validates
// every job against the action's strict schema, so any action works.
const ADDABLE: { type: string; label: string; params: Record<string, unknown> }[] = [
  { type: "create_product_listing", label: "Create product listing", params: { name: "", details: "", price: "", media_ids: [] } },
  { type: "publish_product", label: "Publish product on website", params: { product: "" } },
  { type: "generate_photo", label: "Generate a photo", params: { prompt: "", style: "", audience: "", background: "" } },
  { type: "generate_video", label: "Generate a video", params: { prompt: "", duration_s: 8, audience: "", background: "", voiceover_text: "" } },
  { type: "create_organic_posts", label: "Draft organic posts", params: { count: 1, brief: "", platforms: ["facebook"] } },
  { type: "schedule_organic_posts", label: "Schedule organic posts", params: { content_ids: "", time_local: "19:00" } },
  { type: "create_ai_campaign", label: "Create ad campaign with AI", params: { prompt: "", platforms: ["meta"], budget: "", landing_url: "" } },
  { type: "notify_owner", label: "Notify the owner", params: { message: "" } },
];

export function AddJobForm({ items, tz, busy, error, onAdd, onCancel }: {
  items: PlanItem[];
  tz: string | undefined;
  busy: boolean;
  error: string | null;
  onAdd: (job: { type: string; params: Record<string, unknown>; item_key: string | null; run_at: string | null }) => void;
  onCancel: () => void;
}) {
  const [type, setType] = useState(ADDABLE[0].type);
  const [itemKey, setItemKey] = useState<string>("");
  const starter = ADDABLE.find((a) => a.type === type) ?? ADDABLE[0];
  return (
    <div className="cc-job-form" data-testid="add-job">
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="grid gap-1 text-xs">
          <span className="text-muted">Action</span>
          <select value={type} onChange={(e) => setType(e.target.value)}>
            {ADDABLE.map((a) => (
              <option key={a.type} value={a.type}>{a.label}</option>
            ))}
          </select>
        </label>
        <label className="grid gap-1 text-xs">
          <span className="text-muted">For</span>
          <select value={itemKey} onChange={(e) => setItemKey(e.target.value)}>
            <option value="">The whole list (once)</option>
            {items.map((it) => (
              <option key={it.key} value={it.key}>{it.label}</option>
            ))}
          </select>
        </label>
      </div>
      <JobForm
        key={type}
        job={{ type, label: starter.label, params: starter.params, missing: [], run_at: null }}
        tz={tz}
        busy={busy}
        error={error}
        onCancel={onCancel}
        onSave={(params, runAt) => onAdd({ type, params, item_key: itemKey || null, run_at: runAt })}
      />
    </div>
  );
}

/** "When should these run?" (SPEC-FE-065 FR3). */
export function SchedulePanel({ plan, tz, busy, error, onSave, onCancel }: {
  plan: PlanRead;
  tz: string | undefined;
  busy: boolean;
  error: string | null;
  onSave: (s: JobSchedule) => void;
  onCancel: () => void;
}) {
  const sched = plan.schedule ?? {};
  const [mode, setMode] = useState<RunMode>((plan.mode as RunMode) || "sequential");
  const [start, setStart] = useState(toLocalInput(plan.start_at ?? sched.start_at ?? null, tz));
  const [concurrency, setConcurrency] = useState(plan.concurrency ?? 3);
  const [pattern, setPattern] = useState<"daily" | "every" | "start">(sched.item_daily_time ? "daily" : sched.item_every_minutes ? "every" : "daily");
  const [daily, setDaily] = useState(sched.item_daily_time ?? "10:00");
  const [every, setEvery] = useState(sched.item_every_minutes ?? 60);
  const times = plan.actions.map((a) => a.run_at).filter(Boolean).sort() as string[];
  return (
    <form
      className="cc-job-form"
      data-testid="schedule-panel"
      onSubmit={(e) => {
        e.preventDefault();
        const s: JobSchedule = { mode, start_at: start || null };
        if (mode === "parallel") s.concurrency = concurrency;
        if (mode === "scheduled") {
          if (pattern === "daily") s.item_daily_time = daily;
          if (pattern === "every") s.item_every_minutes = every;
        }
        onSave(s);
      }}
    >
      <div className="text-[13px] font-semibold">When should these run?</div>
      <div className="grid gap-1.5 text-[13px]">
        {([["sequential", "One after another, now"], ["parallel", "Several at once"], ["scheduled", "On a schedule"]] as const).map(([m, label]) => (
          <label key={m} className="flex items-center gap-2">
            <input type="radio" name="mode" checked={mode === m} onChange={() => setMode(m)} /> {label}
          </label>
        ))}
      </div>
      {mode === "parallel" && (
        <label className="flex items-center gap-2 text-xs">
          <span className="text-muted">At a time</span>
          <select value={concurrency} onChange={(e) => setConcurrency(Number(e.target.value))}>
            {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
      )}
      {mode === "scheduled" && (
        <div className="grid gap-1.5 text-xs">
          <label className="flex flex-wrap items-center gap-2">
            <input type="radio" name="pattern" checked={pattern === "daily"} onChange={() => setPattern("daily")} /> One item per day at
            <input type="time" value={daily} onChange={(e) => setDaily(e.target.value)} disabled={pattern !== "daily"} />
          </label>
          <label className="flex flex-wrap items-center gap-2">
            <input type="radio" name="pattern" checked={pattern === "every"} onChange={() => setPattern("every")} /> Space items by
            <input type="number" min={1} max={10080} value={every} onChange={(e) => setEvery(Number(e.target.value))} disabled={pattern !== "every"} className="w-20" /> minutes
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" name="pattern" checked={pattern === "start"} onChange={() => setPattern("start")} /> All at the start time
          </label>
        </div>
      )}
      <label className="grid gap-1 text-xs">
        <span className="text-muted">Start (company time{tz ? `, ${tz}` : ""}; empty = now)</span>
        <input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} />
      </label>
      {times.length > 0 && (
        <p className="m-0 text-[11.5px] text-muted">
          Now: first job {fmtTime(times[0], tz)} · last job {fmtTime(times[times.length - 1], tz)}
        </p>
      )}
      {error && <p className="m-0 text-xs text-danger" role="alert">{error}</p>}
      <div className="flex justify-end gap-2">
        <button type="button" className="btn btn-secondary btn-sm" onClick={onCancel}>Close</button>
        <button type="submit" className="btn btn-sm" disabled={busy}>{busy ? "Saving…" : "Save schedule"}</button>
      </div>
    </form>
  );
}

/** "Review & submit" (FR4): what will run, who must approve, the schedule. */
export function SubmitSheet({ plan, tz, busy, error, onConfirm, onCancel }: {
  plan: PlanRead;
  tz: string | undefined;
  busy: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const jobs = plan.actions;
  const manager = jobs.filter((a) => a.approval_mode === "approval").length;
  const owner = jobs.filter((a) => a.approval_mode === "owner").length;
  const publishing = jobs.filter((a) => a.risk === "change" || a.risk === "spend").length;
  const spending = jobs.filter((a) => a.risk === "spend").length;
  const times = jobs.map((a) => a.run_at).filter(Boolean).sort() as string[];
  const when = plan.mode === "parallel" ? `several at once (${plan.concurrency ?? 3} at a time)`
    : plan.mode === "scheduled" && times.length ? `on a schedule: ${fmtTime(times[0], tz)} → ${fmtTime(times[times.length - 1], tz)}`
      : "one after another, starting now";
  return (
    <div className="cc-job-form cc-submit-sheet" role="dialog" aria-label="Review and submit" data-testid="submit-sheet">
      <div className="text-[14px] font-semibold">Submit {jobs.length} job(s)?</div>
      <ul className="m-0 grid gap-1 pl-4 text-[13px]">
        <li>They run {when}.</li>
        <li>{jobs.length - manager - owner} run without approval{manager || owner ? "" : " (your own command counts as approval)"}.</li>
        {manager > 0 && <li>{manager} wait for a manager's approval.</li>}
        {owner > 0 && <li>{owner} wait for the owner (they spend money).</li>}
        {publishing > 0 && <li>{publishing} publish or change something{spending ? `, ${spending} spend money` : ""}.</li>}
      </ul>
      {error && <p className="m-0 text-xs text-danger" role="alert">{error}</p>}
      <div className="flex justify-end gap-2">
        <button type="button" className="btn btn-secondary btn-sm" onClick={onCancel}>Back to the list</button>
        <button type="button" className="btn btn-sm" disabled={busy} onClick={onConfirm} data-testid="submit-confirm">
          {busy ? "Submitting…" : "Submit"}
        </button>
      </div>
    </div>
  );
}
