"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import BrandingForm from "@/components/settings/branding-form";
import CompanyForm from "@/components/settings/company-form";
import DangerZone from "@/components/settings/danger-zone";
import UsersRoles from "@/components/settings/users-roles";
import { fetchTenant, fetchUsers, tenantKeys } from "@/lib/api/tenant";

const TABS = ["Company", "Branding", "Users & Roles", "API & AI keys", "Data"] as const;
type Tab = (typeof TABS)[number];

// Organization Settings (SPEC-FE-036). The user API is owner-only, so a
// successful user list is how the page knows the viewer is the owner: only
// then is the "Data" (reset) tab offered. The backend enforces every rule.
export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>("Company");
  const tenant = useQuery({ queryKey: tenantKeys.me, queryFn: fetchTenant });
  const users = useQuery({ queryKey: tenantKeys.users, queryFn: fetchUsers, retry: false });
  const isOwner = users.isSuccess;
  const tabs = TABS.filter((t) => t !== "Data" || isOwner);

  return (
    <>
      <h1 className="m-0 mb-1 text-[22px] font-bold">{"Organization Settings"}</h1>
      <p className="m-0 mb-5 text-muted">{"Company profile, branding, people and data."}</p>
      <div className="tabs" role="tablist">
        {tabs.map((t) => (
          <div
            key={t}
            role="tab"
            aria-selected={tab === t}
            tabIndex={0}
            className={tab === t ? "tab active" : "tab"}
            onClick={() => setTab(t)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") setTab(t);
            }}
          >
            {t}
          </div>
        ))}
      </div>
      {tenant.isPending ? (
        <p className="text-[13px] text-muted">Loading settings…</p>
      ) : tenant.isError ? (
        <p className="text-[13px] text-danger" role="alert">
          Failed to load settings: {tenant.error.message}
        </p>
      ) : tab === "Company" ? (
        <CompanyForm key={tenant.data.id} tenant={tenant.data} />
      ) : tab === "Branding" ? (
        <BrandingForm tenant={tenant.data} />
      ) : tab === "Users & Roles" ? (
        <UsersRoles />
      ) : tab === "API & AI keys" ? (
        <div className="card">
          <h3 className="mt-0">API & AI keys</h3>
          <p className="text-[13px]">
            Every key — AI models (Claude, GPT, Gemini, Groq) and platform connections (Meta, TikTok, Google Ads,
            WhatsApp, email, Shopify, CRMs) — is managed in one place.
          </p>
          <Link href="/integrations" className="btn no-underline">
            Open Integrations →
          </Link>
        </div>
      ) : (
        <DangerZone tenant={tenant.data} />
      )}
    </>
  );
}
