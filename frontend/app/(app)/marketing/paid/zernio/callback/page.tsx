"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { errorText } from "@/components/organic/shared";
import { ZERNIO_CHANNEL, finishConnect, zernioKeys } from "@/lib/api/zernio";
import type { ZCallbackRequest } from "@/lib/types/zernio";

const BACK = "/marketing/paid/zernio/new";

// Zernio's hosted sign-in returns here with ?zs (our single-use nonce) plus
// connected/accountId on success or error/error_message on failure. The backend
// checks the nonce; Zernio keeps the platform tokens. This runs in the tab that
// Connect opened: it tells the wizard, then closes itself.
export default function ZernioCallbackPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const started = useRef(false);
  const [req, setReq] = useState<ZCallbackRequest | null>(null);
  const finish = useMutation({
    mutationFn: finishConnect,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: zernioKeys.platforms });
      try {
        const ch = new BroadcastChannel(ZERNIO_CHANNEL);
        ch.postMessage("changed");
        ch.close();
      } catch {
        /* no BroadcastChannel: the wizard refreshes on its next load */
      }
      window.setTimeout(() => {
        window.close();
        window.setTimeout(() => router.replace(BACK), 300);
      }, 1500);
    },
  });
  useEffect(() => {
    if (started.current) return;
    const p = new URLSearchParams(window.location.search);
    const zs = p.get("zs") ?? "";
    if (!zs) return;
    started.current = true;
    const q: ZCallbackRequest = {
      zs,
      connected: p.get("connected"),
      account_id: p.get("accountId"),
      error: p.get("error"),
      error_message: p.get("error_message"),
      error_reason: p.get("error_reason"),
    };
    setReq(q);
    finish.mutate(q);
  }, [finish]);

  const back = (
    <Link href={BACK} className="underline">
      Back to the campaign wizard
    </Link>
  );
  return (
    <div className="mx-auto max-w-[560px]">
      <h1 className="m-0 mb-1 text-[22px] font-bold">Connecting through Zernio</h1>
      {finish.isError ? (
        <p className="text-[13px] text-danger">
          {errorText(finish.error)} {back}
        </p>
      ) : !req ? (
        <p className="text-[13px] text-muted">Nothing to finish here. {back}</p>
      ) : finish.data ? (
        <p className="text-[13px] text-success">{finish.data.message} This tab closes by itself.</p>
      ) : (
        <p className="text-[13px] text-muted">Finishing the connection…</p>
      )}
    </div>
  );
}
