"use client";

import type { RunStage } from "@/lib/types/ai-campaigns";

const LABEL: Record<string, string> = {
  context: "Context",
  plan: "Plan",
  targeting: "Targeting",
  copy: "Copy",
  visuals: "Visuals",
  safety: "Safety review",
  assemble: "Drafts",
};
const DOT: Record<RunStage["status"], string> = {
  pending: "bg-border",
  running: "bg-accent animate-pulse",
  done: "bg-success",
  failed: "bg-danger",
  skipped: "bg-border",
};

function seconds(a: string | null, b: string | null): string | null {
  if (!a || !b) return null;
  const s = (new Date(b).getTime() - new Date(a).getTime()) / 1000;
  return s < 1 ? "<1 s" : `${Math.round(s)} s`;
}

// SPEC-FE-046: the pipeline's stages with status, time and the provider used;
// a final "Review" step reminds that a person publishes.
export default function RunTimeline({ stages, reviewReached }: { stages: RunStage[]; reviewReached: boolean }) {
  return (
    <ol className="m-0 list-none p-0" aria-label="AI run progress">
      {stages.map((st) => (
        <li key={st.name} className="flex gap-3 pb-3" data-stage={st.name} data-status={st.status}>
          <span className={`mt-1 inline-block h-2.5 w-2.5 flex-none rounded-full ${DOT[st.status]}`} aria-hidden />
          <div className="min-w-0 text-[13px]">
            <div className="font-semibold">
              {LABEL[st.name] ?? st.name}
              <span className="ml-2 text-xs font-normal text-muted">
                {st.status === "running" ? "working…" : st.status}
                {seconds(st.started_at, st.ended_at) ? ` · ${seconds(st.started_at, st.ended_at)}` : ""}
                {st.provider ? ` · ${st.provider}` : ""}
              </span>
            </div>
            {st.note && <div className="text-xs text-muted">{st.note}</div>}
            {st.error && <div className="text-xs text-danger">{st.error}</div>}
          </div>
        </li>
      ))}
      <li className="flex gap-3" data-stage="review">
        <span className={`mt-1 inline-block h-2.5 w-2.5 flex-none rounded-full ${reviewReached ? "bg-accent" : "bg-border"}`} aria-hidden />
        <div className="text-[13px]">
          <div className="font-semibold">Your review</div>
          <div className="text-xs text-muted">AI never publishes by itself — you check the ads and publish.</div>
        </div>
      </li>
    </ol>
  );
}
