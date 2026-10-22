"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { errorText } from "@/components/organic/shared";
import { useCompanyCurrency } from "@/hooks/use-tenant";
import { formatMoney } from "@/lib/format/money";
import { fetchSmsSettings, saveSmsSettings, smsKeys } from "@/lib/api/sms";
import type { SmsSettings } from "@/lib/types/sms";

const INPUT = "w-full rounded-md border border-border bg-panel px-3 py-2 text-[13.5px] text-text";
const STATUS_TEXT: Record<SmsSettings["status"], { label: string; className: string }> = {
  ready: { label: "Ready", className: "badge badge-success" },
  no_number: { label: "No number yet", className: "badge badge-warn" },
  not_configured: { label: "Not set up", className: "badge badge-neutral" },
  blocked: { label: "Switched off", className: "badge badge-danger" },
};

// SMS segments, as the backend counts them: GSM text 160 (153 when split), other
// scripts (Bengali) 70 (67). Only a live hint; the backend checks the real limit.
function segments(text: string): number {
  const gsm = [...text].every((ch) => ch.charCodeAt(0) < 128);
  const [single, multi] = gsm ? [160, 153] : [70, 67];
  return text.length <= single ? 1 : Math.ceil(text.length / multi);
}

function Editor({ s }: { s: SmsSettings }) {
  const queryClient = useQueryClient();
  const currency = useCompanyCurrency() ?? "USD";
  const [template, setTemplate] = useState(s.template ?? "");
  const save = useMutation({
    mutationFn: (body: Parameters<typeof saveSmsSettings>[0]) => saveSmsSettings(body),
    onSuccess: (next) => queryClient.setQueryData(smsKeys.settings, next),
  });
  const text = template.trim() || s.default_template;
  const sample = text
    .replaceAll("{shop}", "Your shop")
    .replaceAll("{order_number}", "1001")
    .replaceAll("{total}", formatMoney(1500, currency))
    .replaceAll("{items}", "2 items");
  const parts = segments(sample);
  return (
    <div className="flex flex-col gap-3">
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={s.auto_confirm}
          disabled={save.isPending}
          onChange={(e) => save.mutate({ auto_confirm: e.target.checked })}
        />
        Send the confirmation SMS automatically when an order is created
      </label>
      <label className="text-[12.5px] text-muted">
        Language
        <select
          className={INPUT}
          value={s.language}
          disabled={save.isPending}
          onChange={(e) => save.mutate({ language: e.target.value as SmsSettings["language"] })}
        >
          <option value="auto">Same as the brand language</option>
          <option value="en">English</option>
          <option value="bn">বাংলা (Bengali)</option>
        </select>
      </label>
      <label className="text-[12.5px] text-muted">
        Message text — placeholders {"{shop}"} {"{order_number}"} {"{total}"} {"{items}"}; leave empty for the default
        <textarea
          className={INPUT}
          rows={3}
          maxLength={480}
          placeholder={s.default_template}
          value={template}
          onChange={(e) => setTemplate(e.target.value)}
        />
      </label>
      <p className={parts > 3 ? "text-[13px] text-danger" : "text-[13px] text-muted"}>
        Preview: “{sample}” — {parts} SMS part{parts === 1 ? "" : "s"} (at most 3)
      </p>
      <button
        type="button"
        className="btn self-start"
        disabled={save.isPending || parts > 3}
        onClick={() => save.mutate({ template: template.trim() })}
      >
        {save.isPending ? "Saving…" : "Save text"}
      </button>
      {save.isError && <p className="text-danger">{errorText(save.error)}</p>}
    </div>
  );
}

// Settings → SMS (SPEC-FE-073 / SPEC-BE-108 FR2): the company's sending number
// (assigned by PilotSonic), auto-confirm, language and the message text.
export default function SmsCard() {
  const query = useQuery({ queryKey: smsKeys.settings, queryFn: fetchSmsSettings });
  if (query.isPending) return <p className="text-muted">Loading SMS settings…</p>;
  if (query.isError) return <p className="text-danger">Couldn&apos;t load SMS settings: {query.error.message}</p>;
  const s = query.data;
  const st = STATUS_TEXT[s.status];
  return (
    <div className="card">
      <h3 className="mt-0">Order confirmation SMS</h3>
      <p className="mb-3">
        <span className={st.className}>{st.label}</span>{" "}
        {s.number && <span className="text-muted">Sending number {s.number}</span>}
      </p>
      {s.reason && <p className="mb-3 text-[13px] text-muted">{s.reason}</p>}
      <p className="mb-3 text-[13px] text-muted">
        Customers reply YES or NO with the order number. A reply only changes an order when it&apos;s clear which order it
        means; anything else is shown on the order for you to check.
      </p>
      <Editor s={s} />
    </div>
  );
}
