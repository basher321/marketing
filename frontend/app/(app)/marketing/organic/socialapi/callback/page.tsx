"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { errorText } from "@/components/organic/shared";
import { finishConnect, SAPI_CHANNEL, sapiKeys, selectChoice } from "@/lib/api/socialapi";
import { sapiLabel, type CallbackRequest, type CallbackResult } from "@/lib/types/socialapi";

const BACK = "/marketing/organic/socialapi";
const STATUSES = ["success", "error", "selection_required"];

// SocialAPI's sign-in returns here with ?status&platform&state (+ account_id,
// or connection_id when a Facebook Page / Google location must be chosen).
// The backend checks the signed state; SocialAPI keeps the platform tokens.
export default function SocialApiCallbackPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const started = useRef(false);
  const [result, setResult] = useState<CallbackResult | null>(null);
  const [pick, setPick] = useState("");
  const [req, setReq] = useState<CallbackRequest | null>(null);
  const done = () => {
    void qc.invalidateQueries({ queryKey: sapiKeys.accounts });
    // Sign-in runs in its own tab (opened by Connect): tell the SocialAPI page,
    // then close this tab. A tab the browser won't close goes back to the page.
    try {
      const ch = new BroadcastChannel(SAPI_CHANNEL);
      ch.postMessage("changed");
      ch.close();
    } catch {
      /* no BroadcastChannel: the page refreshes on its next load */
    }
    window.close();
    window.setTimeout(() => router.replace(BACK), 300);
  };
  const finish = useMutation({
    mutationFn: finishConnect,
    onSuccess: (r) => {
      if (r.status === "connected") return done();
      setResult(r);
      setPick(r.choices.find((c) => c.assignable)?.id ?? "");
    },
  });
  const select = useMutation({
    mutationFn: () => selectChoice({ platform: result!.platform, connection_id: result!.connection_id!, choice_id: pick, state: req!.state }),
    onSuccess: done,
  });
  useEffect(() => {
    if (started.current) return;
    const p = new URLSearchParams(window.location.search);
    const status = p.get("status") ?? "";
    const state = p.get("state") ?? "";
    if (!STATUSES.includes(status) || !state) return;
    started.current = true;
    const q: CallbackRequest = {
      status: status as CallbackRequest["status"],
      state,
      platform: p.get("platform"),
      account_id: p.get("account_id"),
      connection_id: p.get("connection_id"),
      error: p.get("error"),
      error_description: p.get("error_description"),
    };
    setReq(q);
    finish.mutate(q);
  }, [finish]);

  const back = (
    <Link href={BACK} className="underline">
      Back to SocialAPI
    </Link>
  );
  const submit = (e: FormEvent) => {
    e.preventDefault();
    select.mutate();
  };
  return (
    <div className="mx-auto max-w-[560px]">
      <h1 className="page-title">Connect {sapiLabel(result?.platform ?? req?.platform)} via SocialAPI</h1>
      {finish.isError ? (
        <p className="text-[13px] text-danger">
          {errorText(finish.error)} {back}
        </p>
      ) : !req ? (
        <p className="text-[13px] text-muted">Nothing to finish here. {back}</p>
      ) : !result ? (
        <p className="text-[13px] text-muted">Finishing the connection…</p>
      ) : (
        <form className="card" onSubmit={submit} data-testid="sapi-choices">
          <p className="mt-0 text-[13px] text-muted">{result.platform === "google" ? "Choose the business location." : "Choose the Facebook Page to post as."}</p>
          <div className="mb-3 grid gap-2">
            {result.choices.map((c) => (
              <label key={c.id} className={`flex items-center gap-2 rounded-md border border-border p-2 ${c.assignable ? "cursor-pointer" : "opacity-60"}`}>
                <input type="radio" name="choice" value={c.id} checked={pick === c.id} disabled={!c.assignable} onChange={() => setPick(c.id)} />
                {c.picture_url ? (
                  <img src={c.picture_url} alt="" className="h-8 w-8 rounded-full object-cover" />
                ) : (
                  <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold">{c.name.slice(0, 1)}</span>
                )}
                <span className="min-w-0">
                  <span className="block font-medium">{c.name}</span>
                  <span className="block truncate text-xs text-muted">
                    {c.detail ?? c.id}
                    {c.assigned_account_id ? " · already connected" : ""}
                    {!c.assignable ? " · can't be connected with this login" : ""}
                  </span>
                </span>
              </label>
            ))}
          </div>
          {select.isError && <p className="text-xs text-danger">{errorText(select.error)}</p>}
          <button type="submit" className="btn" disabled={!pick || select.isPending}>
            {select.isPending ? "Saving…" : "Use this"}
          </button>
        </form>
      )}
    </div>
  );
}
