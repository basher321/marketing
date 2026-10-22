"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { errorText } from "@/components/organic/shared";
import { disconnectWhatsApp, fetchWhatsAppConnect, fetchWhatsAppStatus, inboxKeys, postWhatsAppCallback } from "@/lib/api/inbox";
import { fetchSmsSettings, smsKeys } from "@/lib/api/sms";
import type { WhatsAppConnectInfo } from "@/lib/types/inbox";

type FBLoginResponse = { authResponse?: { code?: string } | null };
type FBSdk = {
  init: (o: { appId: string; autoLogAppEvents: boolean; xfbml: boolean; version: string }) => void;
  login: (cb: (r: FBLoginResponse) => void, o: Record<string, unknown>) => void;
};

// Meta's JS SDK, loaded only when someone clicks Connect (official Embedded Signup).
function loadSdk(): Promise<FBSdk> {
  const w = window as unknown as { FB?: FBSdk };
  if (w.FB) return Promise.resolve(w.FB);
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://connect.facebook.net/en_US/sdk.js";
    s.async = true;
    s.crossOrigin = "anonymous";
    s.onload = () => (w.FB ? resolve(w.FB) : reject(new Error("Facebook's sign-in didn't load.")));
    s.onerror = () => reject(new Error("Facebook's sign-in couldn't load (blocked by the browser?)."));
    document.body.appendChild(s);
  });
}

// Embedded Signup: FB.login with the WhatsApp configuration gives a code; Meta's
// window message (WA_EMBEDDED_SIGNUP, FINISH) gives the WABA and phone number ids.
// Both go to the backend, which exchanges the code. No token reaches the browser.
async function embeddedSignup(info: WhatsAppConnectInfo): Promise<{ code: string; waba_id: string; phone_number_id: string }> {
  const FB = await loadSdk();
  FB.init({ appId: info.app_id, autoLogAppEvents: true, xfbml: false, version: info.graph_version });
  return new Promise((resolve, reject) => {
    let ids: { waba_id: string; phone_number_id: string } | null = null;
    let code: string | null = null;
    const finish = () => {
      if (code && ids) {
        window.removeEventListener("message", onMessage);
        resolve({ code, ...ids });
      }
    };
    const onMessage = (e: MessageEvent) => {
      if (!/(^|\.)facebook\.com$/.test(new URL(e.origin).hostname)) return;
      try {
        const data = typeof e.data === "string" ? JSON.parse(e.data) : e.data;
        if (data?.type !== "WA_EMBEDDED_SIGNUP") return;
        if (data.event === "FINISH" && data.data?.phone_number_id && data.data?.waba_id) {
          ids = { waba_id: String(data.data.waba_id), phone_number_id: String(data.data.phone_number_id) };
          finish();
        } else if (data.event === "CANCEL" || data.event === "ERROR") {
          window.removeEventListener("message", onMessage);
          reject(new Error(data.data?.error_message ?? "WhatsApp sign-up was cancelled."));
        }
      } catch {
        /* not Meta's message */
      }
    };
    window.addEventListener("message", onMessage);
    FB.login(
      (r) => {
        code = r.authResponse?.code ?? null;
        if (!code) {
          window.removeEventListener("message", onMessage);
          reject(new Error("WhatsApp sign-up was cancelled."));
          return;
        }
        // The FINISH message may arrive just after the login callback.
        setTimeout(() => {
          if (!ids) {
            window.removeEventListener("message", onMessage);
            reject(new Error("Meta didn't return the WhatsApp number. Try again."));
          }
        }, 8000);
        finish();
      },
      {
        config_id: info.config_id,
        response_type: "code",
        override_default_response_type: true,
        extras: { setup: {}, featureType: "", sessionInfoVersion: "3" },
      },
    );
  });
}

function WhatsAppCard() {
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: inboxKeys.whatsapp, queryFn: fetchWhatsAppStatus });
  const [busy, setBusy] = useState(false);
  const connect = useMutation({
    mutationFn: async () => {
      setBusy(true);
      try {
        const info = await fetchWhatsAppConnect();
        const result = await embeddedSignup(info);
        return await postWhatsAppCallback({ ...result, state: info.state });
      } finally {
        setBusy(false);
      }
    },
    onSuccess: (s) => {
      queryClient.setQueryData(inboxKeys.whatsapp, s);
      void queryClient.invalidateQueries({ queryKey: inboxKeys.channels });
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => disconnectWhatsApp(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: inboxKeys.whatsapp });
      void queryClient.invalidateQueries({ queryKey: inboxKeys.channels });
    },
  });
  const s = status.data;
  return (
    <div className="integration-card">
      <div className="integration-header">
        <span className="integration-name">WhatsApp Business</span>
        <span className={s?.accounts.some((a) => a.status === "connected") ? "badge badge-success" : "badge badge-neutral"}>
          {s?.accounts.some((a) => a.status === "connected") ? "Connected" : "Not connected"}
        </span>
      </div>
      {status.isError && <p className="text-danger">{status.error.message}</p>}
      {s && !s.available && <p className="text-[13px] text-muted">{s.reason}</p>}
      {s?.accounts.map((a) => (
        <div key={a.id} className="mt-2 flex items-center justify-between text-[13px]">
          <span>
            {a.phone_number ?? a.name} <span className="text-muted">· {a.status}</span>
            {a.last_error && <span className="text-danger"> · {a.last_error}</span>}
          </span>
          <button type="button" className="btn btn-secondary btn-sm" disabled={remove.isPending}
            onClick={() => { if (window.confirm("Disconnect this WhatsApp number?")) remove.mutate(a.id); }}>
            Disconnect
          </button>
        </div>
      ))}
      {s?.available && (
        <button type="button" className="btn mt-3" disabled={busy} onClick={() => connect.mutate()}>
          {busy ? "Waiting for Facebook…" : s.accounts.length ? "Connect another number" : "Connect with Facebook"}
        </button>
      )}
      <p className="mt-2 text-[12px] text-muted">Messages arrive in Command Chat → Inbox. Free replies within 24 hours of the customer&apos;s last message.</p>
      {connect.isError && <p className="mt-2 text-danger">{errorText(connect.error, "Only managers and owners can connect WhatsApp.")}</p>}
      {remove.isError && <p className="mt-2 text-danger">{errorText(remove.error)}</p>}
    </div>
  );
}

function SmsCard() {
  const sms = useQuery({ queryKey: smsKeys.settings, queryFn: fetchSmsSettings });
  const s = sms.data;
  return (
    <div className="integration-card">
      <div className="integration-header">
        <span className="integration-name">SMS (order confirmations)</span>
        <span className={s?.status === "ready" ? "badge badge-success" : "badge badge-neutral"}>
          {s?.status === "ready" ? "Ready" : "Not ready"}
        </span>
      </div>
      {sms.isError && <p className="text-danger">{sms.error.message}</p>}
      {s && (
        <p className="text-[13px]">
          {s.number ? `Sending number ${s.number}.` : (s.reason ?? "Ask PilotSonic for a number.")}{" "}
          <Link href="/settings" className="text-accent">SMS settings →</Link>
        </p>
      )}
    </div>
  );
}

// Integrations → Messaging channels (SPEC-FE-076): WhatsApp Business (Embedded
// Signup, no pasted tokens) and the SMS number PilotSonic assigned.
export default function MessagingChannels() {
  return (
    <div className="mt-4">
      <h2 className="section-title">Messaging channels</h2>
      <div className="integrations-grid">
        <WhatsAppCard />
        <SmsCard />
      </div>
    </div>
  );
}
