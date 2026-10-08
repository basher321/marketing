"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import AdPreviewCard from "@/components/campaigns/ai/ad-preview-card";
import RunTimeline from "@/components/campaigns/ai/run-timeline";
import { errorText } from "@/components/campaigns/platform-builder/tree";
import { aiCampaignKeys, answerRun, cancelRun, fetchRun, publishRun, regenerateAd, retryRun } from "@/lib/api/ai-campaigns";
import type { AICampaignRun } from "@/lib/types/ai-campaigns";

const WORKING = new Set(["queued", "running", "publishing"]);
const STATUS_TEXT: Record<string, string> = {
  queued: "Starting…",
  running: "Working…",
  needs_input: "Needs your answer",
  ready_for_review: "Ready for your review",
  publishing: "Publishing…",
  awaiting_approval: "Waiting for owner approval",
  published: "Published",
  failed: "Failed",
  cancelled: "Discarded",
};
const STATUS_CLASS: Record<string, string> = {
  ready_for_review: "badge badge-warn",
  needs_input: "badge badge-warn",
  published: "badge badge-success",
  awaiting_approval: "badge badge-neutral",
  failed: "badge badge-danger",
  cancelled: "badge badge-neutral",
};

function Questions({ run, onDone }: { run: AICampaignRun; onDone: (r: AICampaignRun) => void }) {
  const [answers, setAnswers] = useState<string[]>(run.questions.map(() => ""));
  const send = useMutation({ mutationFn: () => answerRun(run.id, answers.map((a) => a.trim())), onSuccess: onDone });
  return (
    <div className="card mb-4">
      <h3 className="mt-0">A few questions first</h3>
      {run.questions.map((q, i) => (
        <div key={i} className="form-row">
          <label htmlFor={`ai_q_${i}`}>{q}</label>
          <input id={`ai_q_${i}`} value={answers[i]} onChange={(e) => setAnswers((cur) => cur.map((a, j) => (j === i ? e.target.value : a)))} />
        </div>
      ))}
      {send.isError && <p className="text-xs text-danger">{errorText(send.error)}</p>}
      <button type="button" className="btn btn-sm" disabled={send.isPending || answers.some((a) => !a.trim())} onClick={() => send.mutate()}>
        {send.isPending ? "Sending…" : "Continue"}
      </button>
    </div>
  );
}

// AI run page (SPEC-FE-046): live progress, then the review — every ad with
// its images, texts and safety issues. Publishing is the person's action and
// follows the normal approval rules.
export default function AIRunPage() {
  const { runId } = useParams<{ runId: string }>();
  const queryClient = useQueryClient();
  const run = useQuery({
    queryKey: aiCampaignKeys.run(runId),
    queryFn: () => fetchRun(runId),
    refetchInterval: (q) => (q.state.data && WORKING.has(q.state.data.status) ? 2000 : false),
  });
  const [ack, setAck] = useState(false);
  const store = (r: AICampaignRun) => queryClient.setQueryData(aiCampaignKeys.run(runId), r);
  const act = useMutation({ mutationFn: (fn: () => Promise<AICampaignRun>) => fn(), onSuccess: store });
  if (run.isPending) return <p className="text-[13px] text-muted">Loading run…</p>;
  if (run.isError) {
    return (
      <p className="text-[13px] text-danger" role="alert">
        {run.error.message}{" "}
        <Link href="/marketing/paid" className="underline">
          Back to campaigns
        </Link>
      </p>
    );
  }
  const r = run.data;
  const errors = r.safety.filter((i) => i.severity === "error");
  const warnings = r.safety.filter((i) => i.severity === "warning");
  const general = r.safety.filter((i) => !r.ads.some((a) => a.ref === i.ref));
  const reviewing = r.status === "ready_for_review";
  const reviewReached = ["ready_for_review", "publishing", "awaiting_approval", "published"].includes(r.status);
  const canPublish = r.can_publish && (warnings.length === 0 || ack) && !act.isPending;
  return (
    <div className="mx-auto max-w-[1150px]">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link href="/marketing/paid?tab=ai" className="text-xs text-muted underline">
            ← AI runs
          </Link>
          <h1 className="m-0 text-[22px] font-bold">AI campaign</h1>
          <p className="m-0 max-w-[700px] text-[13px] text-muted">“{r.prompt}”</p>
        </div>
        <span className={STATUS_CLASS[r.status] ?? "badge badge-neutral"} data-testid="run-status" data-status={r.status}>
          {STATUS_TEXT[r.status] ?? r.status}
        </span>
      </div>

      <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
        <aside className="card" style={{ padding: 12 }}>
          <RunTimeline stages={r.stages} reviewReached={reviewReached} />
          <p className="m-0 mt-2 text-xs text-muted">AI cost so far: about {(r.cost_cents / 100).toFixed(2)} USD</p>
        </aside>

        <div className="min-w-0">
          {r.status === "needs_input" && <Questions run={r} onDone={store} />}
          {r.status === "failed" && (
            <div className="card mb-4">
              <p className="m-0 mb-2 text-[13px] text-danger">{r.error}</p>
              <div className="flex gap-2">
                {r.error?.startsWith("publish") ? (
                  <button type="button" className="btn btn-sm" disabled={act.isPending} onClick={() => act.mutate(() => publishRun(r.id, true))}>
                    Retry publish
                  </button>
                ) : (
                  <button type="button" className="btn btn-sm" disabled={act.isPending} onClick={() => act.mutate(() => retryRun(r.id))}>
                    Retry
                  </button>
                )}
                <button type="button" className="btn btn-secondary btn-sm" disabled={act.isPending} onClick={() => act.mutate(() => cancelRun(r.id))}>
                  Discard
                </button>
              </div>
            </div>
          )}
          {r.summary && <p className="m-0 mb-3 text-[13px]">{r.summary}</p>}

          {r.campaigns.map((c) => (
            <section key={c.platform} className="mb-5" data-platform={c.platform}>
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <h2 className="m-0 text-[16px]">
                  {c.label} · {c.objective.replace(/_/g, " ").toLowerCase()}
                  {c.campaign_type ? ` · ${c.campaign_type.replace(/_/g, " ").toLowerCase()}` : ""}
                </h2>
                <div className="flex items-center gap-2 text-[13px]">
                  <span className="text-muted">
                    Budget {c.budget.toFixed(2)} ({c.budget_mode})
                  </span>
                  {c.status && <span className="badge badge-neutral">{c.status}</span>}
                  {c.campaign_id && (
                    <Link href={`/marketing/paid/${c.campaign_id}/edit`} className="text-accent underline">
                      {c.status === "draft" ? "Edit in builder" : "Open"}
                    </Link>
                  )}
                </div>
              </div>
              {c.groups.map((g, gi) => (
                <p key={gi} className="m-0 mb-2 text-xs text-muted">
                  Audience “{g.name}”:{" "}
                  {Object.entries(g.audience || {})
                    .map(([k, v]) => `${k.replace(/_/g, " ")}: ${Array.isArray(v) ? v.join(", ") : String(v)}`)
                    .join(" · ")}
                </p>
              ))}
              <div className="grid gap-3 md:grid-cols-2">
                {r.ads
                  .filter((a) => a.platform === c.platform)
                  .map((a) => (
                    <AdPreviewCard
                      key={a.ref}
                      ad={a}
                      issues={r.safety.filter((i) => i.ref === a.ref)}
                      busy={act.isPending}
                      onRegenerate={reviewing ? (what) => act.mutate(() => regenerateAd(r.id, a.ref, what)) : undefined}
                    />
                  ))}
              </div>
            </section>
          ))}

          {reviewReached && (
            <div className="card sticky bottom-0 z-10" style={{ padding: 12 }} data-testid="safety-report">
              <h3 className="mt-0 text-[14px]">Safety report</h3>
              {errors.length === 0 && warnings.length === 0 ? (
                <p className="m-0 text-xs text-success">All checks passed: brand words, price claims, policy review, landing page and each platform&apos;s validation.</p>
              ) : (
                <ul className="m-0 mb-2 max-h-40 overflow-y-auto pl-4 text-xs">
                  {general.map((i, k) => (
                    <li key={k} className={i.severity === "error" ? "text-danger" : "text-warn"}>
                      {i.message}
                    </li>
                  ))}
                  {r.safety.length > general.length && <li className="text-muted">Issues on single ads are shown on their cards.</li>}
                </ul>
              )}
              {reviewing && (
                <>
                  {warnings.length > 0 && errors.length === 0 && (
                    <label className="mb-2 flex items-center gap-2 text-[13px]">
                      <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
                      I&apos;ve read the {warnings.length} warning(s) and want to publish anyway.
                    </label>
                  )}
                  {r.publish_note && <p className="m-0 mb-2 text-xs text-muted">{r.publish_note}</p>}
                  {act.isError && <p className="m-0 mb-2 text-xs text-danger" role="alert">{errorText(act.error)}</p>}
                  <div className="flex flex-wrap gap-2">
                    <button type="button" className="btn btn-sm" disabled={!canPublish} onClick={() => act.mutate(() => publishRun(r.id, ack))}>
                      {act.isPending ? "Working…" : "Publish"}
                    </button>
                    <button type="button" className="btn btn-secondary btn-sm" disabled={act.isPending} onClick={() => act.mutate(() => publishRun(r.id, ack, "paused"))} hidden={!canPublish}>
                      Publish paused
                    </button>
                    <button type="button" className="btn btn-secondary btn-sm" disabled={act.isPending} onClick={() => act.mutate(() => retryRun(r.id, "plan"))}>
                      Start over
                    </button>
                    <button type="button" className="btn btn-ghost btn-sm" disabled={act.isPending} onClick={() => act.mutate(() => cancelRun(r.id))}>
                      Discard
                    </button>
                  </div>
                </>
              )}
              {r.status === "awaiting_approval" && <p className="m-0 text-xs text-muted">Sent to the owner — see Command Chat › Pending Approvals.</p>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
