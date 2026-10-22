"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { errorText } from "@/components/campaigns/builder/tree";
import { integrationKeys } from "@/lib/api/integrations";
import { metaCallback, metaSelect } from "@/lib/api/meta";
import type { MetaChoices } from "@/lib/types/meta";

const ACCOUNT_STATUS: Record<number, string> = { 1: "active", 2: "disabled", 3: "unsettled", 7: "pending review", 9: "grace period", 101: "closed" };

// Facebook Login for Business returns here with ?code&state (SPEC-BE-054).
// The backend exchanges the code (the token is stored encrypted, never sent
// to the browser) and lists what it can reach; the user picks the ad account,
// Page, optional Instagram account and optional pixel.
export default function MetaCallbackPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [choices, setChoices] = useState<MetaChoices | null>(null);
  const [pick, setPick] = useState({ ad_account_id: "", page_id: "", instagram_id: "", pixel_id: "" });
  const started = useRef(false);
  const exchange = useMutation({
    mutationFn: ({ code, state }: { code: string; state: string }) => metaCallback(code, state),
    onSuccess: (c) => {
      setChoices(c);
      const page = c.pages[0];
      setPick({
        ad_account_id: c.ad_accounts.find((a) => a.account_status === 1)?.id ?? c.ad_accounts[0]?.id ?? "",
        page_id: page?.id ?? "",
        instagram_id: page?.instagram?.id ?? "",
        pixel_id: "",
      });
    },
  });
  const select = useMutation({
    mutationFn: () =>
      metaSelect({
        ad_account_id: pick.ad_account_id,
        page_id: pick.page_id,
        instagram_id: pick.instagram_id || null,
        pixel_id: pick.pixel_id || null,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: integrationKeys.all });
      router.replace("/integrations");
    },
  });
  const params = typeof window === "undefined" ? null : new URLSearchParams(window.location.search);
  const denied = params?.get("error_description") ?? params?.get("error");
  useEffect(() => {
    if (started.current || !params) return;
    const code = params.get("code");
    const state = params.get("state");
    if (code && state) {
      started.current = true;
      exchange.mutate({ code, state });
    }
  }, [params, exchange]);

  const page = choices?.pages.find((p) => p.id === pick.page_id);
  const pixels = choices?.pixels.filter((p) => !pick.ad_account_id || p.ad_account_id === pick.ad_account_id) ?? [];
  const submit = (e: FormEvent) => {
    e.preventDefault();
    select.mutate();
  };

  return (
    <div className="mx-auto max-w-[560px]">
      <h1 className="page-title">Connect Meta</h1>
      {denied ? (
        <p className="text-[13px] text-danger">
          Meta didn&apos;t connect: {denied}.{" "}
          <Link href="/integrations" className="underline">
            Back to Integrations
          </Link>
        </p>
      ) : exchange.isPending || (!choices && !exchange.isError) ? (
        <p className="text-[13px] text-muted">Finishing the connection with Meta…</p>
      ) : exchange.isError ? (
        <p className="text-[13px] text-danger">
          {errorText(exchange.error)}{" "}
          <Link href="/integrations" className="underline">
            Try again
          </Link>
        </p>
      ) : (
        choices && (
          <form className="card" onSubmit={submit}>
            <p className="mt-0 text-[13px] text-muted">Choose what this workspace advertises with.</p>
            <div className="form-row">
              <label htmlFor="mc_act">Ad account</label>
              <select id="mc_act" value={pick.ad_account_id} onChange={(e) => setPick((p) => ({ ...p, ad_account_id: e.target.value, pixel_id: "" }))}>
                {choices.ad_accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} · {a.currency} · {ACCOUNT_STATUS[a.account_status] ?? `status ${a.account_status}`}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-row">
              <label htmlFor="mc_page">Facebook Page (ads run as this Page)</label>
              <select
                id="mc_page"
                value={pick.page_id}
                onChange={(e) => {
                  const next = choices.pages.find((p) => p.id === e.target.value);
                  setPick((p) => ({ ...p, page_id: e.target.value, instagram_id: next?.instagram?.id ?? "" }));
                }}
              >
                {choices.pages.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-row">
              <label htmlFor="mc_ig">Instagram account (optional)</label>
              <select id="mc_ig" value={pick.instagram_id} onChange={(e) => setPick((p) => ({ ...p, instagram_id: e.target.value }))}>
                <option value="">None</option>
                {page?.instagram && <option value={page.instagram.id}>@{page.instagram.username ?? page.instagram.id}</option>}
              </select>
            </div>
            <div className="form-row">
              <label htmlFor="mc_px">Pixel / dataset (optional, needed for Sales and website Leads)</label>
              <select id="mc_px" value={pick.pixel_id} onChange={(e) => setPick((p) => ({ ...p, pixel_id: e.target.value }))}>
                <option value="">None</option>
                {pixels.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
            {select.isError && <p className="text-xs text-danger">{errorText(select.error)}</p>}
            <button type="submit" className="btn" disabled={!pick.ad_account_id || !pick.page_id || select.isPending}>
              {select.isPending ? "Saving…" : "Use these"}
            </button>
          </form>
        )
      )}
    </div>
  );
}
