"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { apiErrorText } from "@/components/settings/users-roles";
import { resetCompanyData } from "@/lib/api/tenant";
import type { ResetResult, Tenant } from "@/lib/types/tenant";

// What POST /tenants/me/reset deletes and keeps (SPEC-BE-051), in plain words.
const DELETED = [
  "Products, variants, categories, inventory and stock history",
  "Orders, customers and abandoned carts",
  "Conversations and messages",
  "Campaigns, ad sets, ads, audiences, creatives, templates and scheduled posts",
  "Workflows and their run history",
  "Knowledge base: FAQs, macros, policies, documents, brand voice",
  "Pricing rules, shipping zones and rates",
  "Analytics data, approvals, notifications and AI chat history",
];
const KEPT = [
  "The company, its users and roles",
  "Integrations and API / AI-model keys",
  "Company settings and branding",
  "The audit log (the reset itself is recorded)",
];

// Data tab (SPEC-FE-036): owner-only "Reset company data", confirmed by
// typing the workspace name and the owner's password. Irreversible.
export default function DangerZone({ tenant }: { tenant: Tenant }) {
  const queryClient = useQueryClient();
  const [slug, setSlug] = useState("");
  const [password, setPassword] = useState("");
  const [result, setResult] = useState<ResetResult | null>(null);
  const reset = useMutation({
    mutationFn: () => resetCompanyData({ confirm_slug: slug.trim(), password }),
    onSuccess: (r) => {
      setResult(r);
      setSlug("");
      setPassword("");
      // Every cached page's data is now stale.
      void queryClient.invalidateQueries();
    },
  });
  const total = result ? Object.values(result.deleted).reduce((a, b) => a + b, 0) : 0;

  return (
    <div className="card border-danger">
      <h3 className="mt-0 text-danger">Reset company data</h3>
      <p className="text-[13px]">
        Permanently deletes all of <b>{tenant.name}</b>&apos;s business data. <b>This can&apos;t be undone.</b>
      </p>
      <div className="form-grid-2 text-[13px]">
        <div>
          <b>Deleted</b>
          <ul className="mt-1 pl-5">
            {DELETED.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        </div>
        <div>
          <b>Kept</b>
          <ul className="mt-1 pl-5">
            {KEPT.map((k) => (
              <li key={k}>{k}</li>
            ))}
          </ul>
        </div>
      </div>
      <form
        className="mt-3"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          setResult(null);
          reset.mutate();
        }}
      >
        <div className="form-grid-2">
          <div className="form-row">
            <label htmlFor="rz_slug">
              Type the workspace name <b>{tenant.slug}</b> to confirm
            </label>
            <input id="rz_slug" autoComplete="off" value={slug} onChange={(e) => setSlug(e.target.value)} />
          </div>
          <div className="form-row">
            <label htmlFor="rz_password">Your password</label>
            <input id="rz_password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
        </div>
        <button type="submit" className="btn bg-danger" disabled={reset.isPending || slug.trim() !== tenant.slug || !password}>
          {reset.isPending ? "Resetting…" : "Reset company data"}
        </button>
      </form>
      {reset.isError && (
        <p className="mb-0 mt-3 text-xs text-danger" role="alert">
          {apiErrorText(reset.error, "Only the owner can reset company data.")}
        </p>
      )}
      {result && (
        <p className="mb-0 mt-3 text-[13px] text-success" role="status">
          Done — {total.toLocaleString("en-US")} records deleted (
          {Object.entries(result.deleted)
            .filter(([, n]) => n > 0)
            .map(([t, n]) => `${t.replace(/_/g, " ")} ${n}`)
            .join(", ") || "nothing to delete"}
          ).
        </p>
      )}
    </div>
  );
}
