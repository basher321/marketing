"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { addAd, addAdSet, deleteAd, deleteAdSet, duplicateAd, duplicateAdSet, metaKeys } from "@/lib/api/meta";
import { ApiError } from "@/lib/types/common";
import type { BuilderTree, Issue, ObjectivesResult } from "@/lib/types/meta";

export type Selection = { level: "campaign" | "ad_set" | "ad"; id: string };

type Ctx = {
  tree: BuilderTree;
  objectives: ObjectivesResult | undefined;
  selected: Selection;
  select: (s: Selection) => void;
  /** Runs a call that returns the new tree and stores it (all builder writes do). */
  run: (fn: () => Promise<BuilderTree>) => Promise<void>;
  busy: boolean;
  error: string | null;
  setDirty: (dirty: boolean) => void;
  editable: boolean;
};

const BuilderContext = createContext<Ctx | null>(null);

export function useBuilder(): Ctx {
  const ctx = useContext(BuilderContext);
  if (!ctx) throw new Error("useBuilder outside BuilderProvider");
  return ctx;
}

export function errorText(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 403) return "Only managers and above can edit campaigns.";
    const detail = (err.body as { detail?: unknown } | undefined)?.detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d: { msg?: string; loc?: unknown[] }) => `${(d.loc ?? []).slice(1).join(".")}: ${(d.msg ?? "").replace(/^Value error, /, "")}`)
        .join(" ");
    }
  }
  return err instanceof Error ? err.message : String(err);
}

export function BuilderProvider({
  tree,
  objectives,
  children,
}: {
  tree: BuilderTree;
  objectives: ObjectivesResult | undefined;
  children: ReactNode;
}) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<Selection>({ level: "campaign", id: tree.campaign.id });
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const mutation = useMutation({
    mutationFn: (fn: () => Promise<BuilderTree>) => fn(),
    onMutate: () => setError(null),
    onSuccess: (next) => queryClient.setQueryData(metaKeys.tree(tree.campaign.id), next),
    onError: (err) => setError(errorText(err)),
  });
  // Unsaved-changes guard (SPEC-FE-039).
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  // A deleted node falls back to the campaign.
  useEffect(() => {
    const exists =
      selected.level === "campaign" ||
      (selected.level === "ad_set" && tree.ad_sets.some((s) => s.id === selected.id)) ||
      (selected.level === "ad" && tree.ad_sets.some((s) => s.ads.some((a) => a.id === selected.id)));
    if (!exists) setSelected({ level: "campaign", id: tree.campaign.id });
  }, [tree, selected]);

  const value: Ctx = {
    tree,
    objectives,
    selected,
    select: setSelected,
    run: async (fn) => {
      await mutation.mutateAsync(fn).catch(() => undefined);
    },
    busy: mutation.isPending,
    error,
    setDirty,
    editable: tree.campaign.status === "draft" || Boolean(tree.meta?.published),
  };
  return <BuilderContext.Provider value={value}>{children}</BuilderContext.Provider>;
}

/** Issues for one node; `field` prefix-matches (e.g. "targeting"). */
export function issuesFor(issues: Issue[], level: Issue["level"], id: string, field?: string): Issue[] {
  return issues.filter((i) => i.level === level && i.id === id && (!field || i.field === field || i.field.startsWith(`${field}.`)));
}

export function FieldIssues({ level, id, field }: { level: Issue["level"]; id: string; field: string }) {
  const { tree } = useBuilder();
  const list = issuesFor(tree.missing, level, id, field);
  if (!list.length) return null;
  return (
    <span className="text-xs text-danger" role="alert">
      {list.map((i) => i.message).join(" ")}
    </span>
  );
}

/**
 * Autosave: local edits are PATCHed ~1.2 s after the last change (only the
 * changed fields), so the backend's own validation and roll-ups stay current.
 * `pending()` returns edits not sent yet: a form that resyncs from a newer
 * tree lays them over it, so typing during a save isn't wiped out.
 */
export function useAutosave<T extends Record<string, unknown>>(
  save: (changes: Partial<T>) => Promise<BuilderTree>,
  resetKey: string,
): ((changes: Partial<T>) => void) & { pending: () => Partial<T> } {
  const { run, setDirty } = useBuilder();
  const pending = useRef<Partial<T>>({});
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const flush = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    const changes = pending.current;
    pending.current = {};
    if (Object.keys(changes).length) {
      void run(() => save(changes)).finally(() => setDirty(false));
    }
  };
  useEffect(() => () => flush(), [resetKey]);
  const queue = (changes: Partial<T>) => {
    pending.current = { ...pending.current, ...changes };
    setDirty(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(flush, 1200);
  };
  return Object.assign(queue, { pending: () => pending.current });
}

function Dot({ show }: { show: boolean }) {
  return show ? <span className="ml-1 inline-block h-2 w-2 rounded-full bg-danger" aria-label="has issues" /> : null;
}

function statusText(status: string, effective: string | null): string {
  if (effective && effective !== "ACTIVE" && effective !== "PAUSED") return effective.replace(/_/g, " ").toLowerCase();
  return status;
}

// Left tree (Campaign -> Ad sets -> Ads) with add / duplicate / delete and
// keyboard navigation (arrow keys move, Enter selects).
export default function BuilderTreeView() {
  const { tree, selected, select, run, busy } = useBuilder();
  const draft = tree.campaign.status === "draft";
  const nodes: Selection[] = [
    { level: "campaign", id: tree.campaign.id },
    ...tree.ad_sets.flatMap((s) => [{ level: "ad_set" as const, id: s.id }, ...s.ads.map((a) => ({ level: "ad" as const, id: a.id }))]),
  ];
  const onKey = (e: KeyboardEvent) => {
    const i = nodes.findIndex((n) => n.id === selected.id);
    if (e.key === "ArrowDown" && i < nodes.length - 1) select(nodes[i + 1]);
    if (e.key === "ArrowUp" && i > 0) select(nodes[i - 1]);
  };
  const has = (level: Issue["level"], id: string) => issuesFor(tree.missing, level, id).length > 0;
  const item = (s: Selection, label: ReactNode, indent: number) => (
    <div
      role="treeitem"
      aria-selected={selected.id === s.id}
      tabIndex={selected.id === s.id ? 0 : -1}
      className={`cursor-pointer rounded px-2 py-1.5 text-[13px] ${selected.id === s.id ? "bg-accent-soft font-semibold" : "hover:bg-bg"}`}
      style={{ paddingLeft: 8 + indent * 14 }}
      onClick={() => select(s)}
      onKeyDown={(e) => e.key === "Enter" && select(s)}
    >
      {label}
    </div>
  );

  return (
    <div className="card" style={{ padding: 10 }} role="tree" aria-label="Campaign structure" onKeyDown={onKey}>
      {item(
        { level: "campaign", id: tree.campaign.id },
        <>
          📣 {tree.campaign.name}
          <Dot show={has("campaign", tree.campaign.id)} />
        </>,
        0,
      )}
      {tree.ad_sets.map((s) => (
        <div key={s.id}>
          {item(
            { level: "ad_set", id: s.id },
            <span className="flex items-center justify-between gap-1">
              <span>
                🎯 {s.name}
                <Dot show={has("ad_set", s.id)} />
                <span className="ml-1 text-[11px] text-muted">{statusText(s.status, s.effective_status)}</span>
              </span>
              {draft && (
                <span className="flex gap-1 text-[11px]">
                  <button type="button" className="text-muted hover:text-text" disabled={busy} title="Duplicate ad set" onClick={(e) => { e.stopPropagation(); void run(() => duplicateAdSet(s.id)); }}>
                    ⧉
                  </button>
                  <button
                    type="button"
                    className="text-muted hover:text-danger"
                    disabled={busy || tree.ad_sets.length === 1}
                    title="Delete ad set"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (window.confirm(`Delete ad set “${s.name}” and its ads?`)) void run(() => deleteAdSet(s.id));
                    }}
                  >
                    ✕
                  </button>
                </span>
              )}
            </span>,
            1,
          )}
          {s.ads.map((a) => (
            <div key={a.id}>
              {item(
                { level: "ad", id: a.id },
                <span className="flex items-center justify-between gap-1">
                  <span>
                    🖼 {a.name}
                    <Dot show={has("ad", a.id)} />
                    <span className="ml-1 text-[11px] text-muted">{statusText(a.status, a.effective_status)}</span>
                  </span>
                  {draft && (
                    <span className="flex gap-1 text-[11px]">
                      <button type="button" className="text-muted hover:text-text" disabled={busy} title="Duplicate ad" onClick={(e) => { e.stopPropagation(); void run(() => duplicateAd(a.id)); }}>
                        ⧉
                      </button>
                      <button
                        type="button"
                        className="text-muted hover:text-danger"
                        disabled={busy || s.ads.length === 1}
                        title="Delete ad"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (window.confirm(`Delete ad “${a.name}”?`)) void run(() => deleteAd(a.id));
                        }}
                      >
                        ✕
                      </button>
                    </span>
                  )}
                </span>,
                2,
              )}
            </div>
          ))}
          {draft && (
            <button type="button" className="ml-[36px] mt-0.5 text-xs text-accent" disabled={busy || s.ads.length >= 10} onClick={() => void run(() => addAd(s.id))}>
              + Ad
            </button>
          )}
        </div>
      ))}
      {draft && (
        <button type="button" className="ml-[22px] mt-1 text-xs text-accent" disabled={busy || tree.ad_sets.length >= 10} onClick={() => void run(() => addAdSet(tree.campaign.id))}>
          + Ad set
        </button>
      )}
    </div>
  );
}
