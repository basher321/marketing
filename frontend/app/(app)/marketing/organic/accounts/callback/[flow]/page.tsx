"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { errorText } from "@/components/organic/shared";
import { oauthCallback, oauthSelect, socialKeys } from "@/lib/api/social";
import { FLOW_LABEL, type OAuthCallbackResult, type SocialFlow } from "@/lib/types/social";

const FLOWS: SocialFlow[] = ["meta", "tiktok", "linkedin"];
const BACK = "/marketing/organic/accounts";

// The platform's sign-in returns here with ?code&state (SPEC-FE-052 /
// SPEC-BE-080). The backend exchanges the code - the tokens are stored
// encrypted and never reach the browser - then the user picks the Page or
// company page (TikTok is saved directly).
export default function SocialCallbackPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const raw = String(useParams<{ flow: string }>().flow ?? "");
  const flow = (FLOWS as string[]).includes(raw) ? (raw as SocialFlow) : null;
  const [result, setResult] = useState<OAuthCallbackResult | null>(null);
  const [pick, setPick] = useState("");
  const [withInstagram, setWithInstagram] = useState(true);
  const started = useRef(false);
  const done = () => {
    void queryClient.invalidateQueries({ queryKey: socialKeys.accounts });
    router.replace(BACK);
  };
  const exchange = useMutation({
    mutationFn: ({ code, state }: { code: string; state: string }) => oauthCallback(flow as SocialFlow, code, state),
    onSuccess: (r) => {
      if (r.saved) {
        done();
        return;
      }
      setResult(r);
      setPick(r.choices[0]?.id ?? "");
    },
  });
  const select = useMutation({ mutationFn: () => oauthSelect(flow as SocialFlow, pick, withInstagram), onSuccess: done });
  const params = typeof window === "undefined" ? null : new URLSearchParams(window.location.search);
  const denied = params?.get("error_description") ?? params?.get("error");
  useEffect(() => {
    if (started.current || !params || !flow) return;
    const code = params.get("code");
    const state = params.get("state");
    if (code && state) {
      started.current = true;
      exchange.mutate({ code, state });
    }
  }, [params, flow, exchange]);

  const chosen = result?.choices.find((c) => c.id === pick);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    select.mutate();
  };
  const back = (
    <Link href={BACK} className="underline">
      Back to Connected Accounts
    </Link>
  );

  if (!flow) {
    return <p className="text-[13px] text-danger">Unknown sign-in. {back}</p>;
  }
  return (
    <div className="mx-auto max-w-[560px]">
      <h1 className="page-title">Connect {FLOW_LABEL[flow]}</h1>
      {denied ? (
        <p className="text-[13px] text-danger">
          {FLOW_LABEL[flow]} didn&apos;t connect: {denied}. {back}
        </p>
      ) : exchange.isError ? (
        <p className="text-[13px] text-danger">
          {errorText(exchange.error)} {back}
        </p>
      ) : !result ? (
        <p className="text-[13px] text-muted">
          {params && !params.get("code") ? <>Nothing to finish here. {back}</> : `Finishing the connection with ${FLOW_LABEL[flow]}…`}
        </p>
      ) : (
        <form className="card" onSubmit={submit} data-testid="oauth-choices">
          <p className="mt-0 text-[13px] text-muted">{flow === "meta" ? "Choose the Facebook Page to post as." : "Choose the company page to post as."}</p>
          <div className="mb-3 grid gap-2">
            {result.choices.map((c) => (
              <label key={c.id} className="flex cursor-pointer items-center gap-2 rounded-md border border-border p-2">
                <input type="radio" name="account" value={c.id} checked={pick === c.id} onChange={() => setPick(c.id)} />
                {c.avatar_url ? (
                  <img src={c.avatar_url} alt="" className="h-8 w-8 rounded-full object-cover" />
                ) : (
                  <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold">{c.name.slice(0, 1)}</span>
                )}
                <span className="min-w-0">
                  <span className="block font-medium">{c.name}</span>
                  <span className="block truncate text-xs text-muted">
                    {c.instagram ? `Instagram @${c.instagram.username ?? c.instagram.id}` : c.handle ? c.handle : c.id}
                  </span>
                </span>
              </label>
            ))}
          </div>
          {flow === "meta" && chosen?.instagram && (
            <label className="mb-3 flex items-center gap-2 text-[13px]">
              <input type="checkbox" checked={withInstagram} onChange={(e) => setWithInstagram(e.target.checked)} />
              Also connect Instagram @{chosen.instagram.username ?? chosen.instagram.id}
            </label>
          )}
          {result.scopes.length > 0 && <p className="m-0 mb-3 text-xs text-muted">Granted: {result.scopes.join(", ")}</p>}
          {select.isError && <p className="text-xs text-danger">{errorText(select.error)}</p>}
          <button type="submit" className="btn" disabled={!pick || select.isPending}>
            {select.isPending ? "Saving…" : "Use this"}
          </button>
        </form>
      )}
    </div>
  );
}
