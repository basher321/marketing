"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import ConnectPanel from "@/components/integrations/connect-panel";
import { fetchCatalog, fetchIntegrations, integrationKeys } from "@/lib/api/integrations";
import { fetchPlatformMe, platformKeys } from "@/lib/api/platform";
import type { IntegrationConnectionStatus, IntegrationStatus } from "@/lib/types/integrations";

// ============================================================================
// STATIC PROVIDER BLURBS - descriptive copy only, NOT tenant data: a generic
// line about what connecting each provider offers. All status data comes from
// the API.
// ============================================================================
const BLURBS: Readonly<Record<string, string>> = {
  facebook: "Publish posts and reply to Messenger",
  instagram: "Publish posts and reply to DMs",
  tiktok: "Publish videos to your business account",
  meta_ads: "Run Facebook & Instagram ad campaigns",
  tiktok_ads: "Run TikTok ad campaigns",
  google_ads: "Add search & display campaigns", // mockup copy
  linkedin_ads: "Run LinkedIn ad campaigns",
  x_ads: "Run X (Twitter) ad campaigns",
  snapchat_ads: "Run Snapchat ad campaigns",
  pinterest_ads: "Run Pinterest ad campaigns",
  shopify: "Sync products, inventory and orders",
  woocommerce: "Sync products, inventory and orders",
  whatsapp: "Message customers on WhatsApp",
  smtp: "Send email from your own mail server",
  sendgrid: "Send marketing and transactional email",
  hubspot: "Sync customer records", // mockup copy
  zoho: "Sync customer records",
  salesforce: "Sync customer records",
};
const CATEGORY_ORDER = ["Ads", "Social", "Messaging", "Email", "Commerce", "CRM"];

// Badge and button per backend status (the backend's only three values).
const STATUS_VIEW: Record<IntegrationConnectionStatus, { badgeClass: string; badge: string; button: string }> = {
  connected: { badgeClass: "badge-success", badge: "Connected", button: "Manage" },
  needs_reconnect: { badgeClass: "badge-warn", badge: "Reconnect", button: "Reconnect" },
  not_connected: { badgeClass: "badge-neutral", badge: "Not Connected", button: "Connect" },
};

function relativeTime(iso: string, now: number = Date.now()): string {
  const minutes = Math.floor((now - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.floor(hours / 24)} d ago`;
}

// The most useful true line for a card: the last error, else "no credentials
// saved" (rows marked connected without any saved keys, e.g. demo data), else
// verification / sync time, else the blurb.
function subtitle(i: IntegrationStatus): { text: string; tone: string } | null {
  if (i.status !== "not_connected" && i.last_error) return { text: i.last_error, tone: "text-danger" };
  if (i.status === "connected" && i.configured_fields.length === 0) return { text: "No credentials saved — click Manage to add them.", tone: "text-warn" };
  if (i.status === "connected" && i.verified_at) return { text: `Verified ${relativeTime(i.verified_at)}${i.account_name ? ` · ${i.account_name}` : ""}`, tone: "text-muted" };
  if (i.status === "connected" && i.last_synced_at) return { text: `Last synced: ${relativeTime(i.last_synced_at)}`, tone: "text-muted" };
  return BLURBS[i.provider] ? { text: BLURBS[i.provider], tone: "text-muted" } : null;
}

// SPEC-FE-080: an API-key integration a company can't edit (only the Super admin sets its keys).
const MANAGED_BUTTON: Record<IntegrationConnectionStatus, string> = {
  connected: "View",
  needs_reconnect: "View",
  not_connected: "Request setup",
};

function IntegrationCard({ integration, managed, onOpen }: { integration: IntegrationStatus; managed: boolean; onOpen: () => void }) {
  const view = STATUS_VIEW[integration.status];
  const line =
    managed && integration.status === "connected" && integration.configured_fields.length === 0
      ? { text: "Set up by PilotSonic.", tone: "text-muted" }
      : subtitle(integration);
  return (
    <div className="integration-card" data-provider={integration.provider}>
      <div className="integration-header">
        <div className="integration-name">{integration.name}</div>
        <span className={`badge ${view.badgeClass}`}>{view.badge}</span>
      </div>
      {line && <p className={`m-0 mb-2.5 text-xs ${line.tone}`}>{line.text}</p>}
      <button type="button" className="btn btn-secondary btn-sm" onClick={onOpen}>
        {managed ? MANAGED_BUTTON[integration.status] : view.button}
      </button>
    </div>
  );
}

// Platform connections (SPEC-FE-021, made functional by SPEC-FE-037): cards
// grouped by category; Connect / Manage / Reconnect open the side panel.
export default function IntegrationsGrid() {
  const integrations = useQuery({ queryKey: integrationKeys.list, queryFn: fetchIntegrations });
  const catalog = useQuery({ queryKey: integrationKeys.catalog, queryFn: fetchCatalog, staleTime: Infinity });
  const me = useQuery({ queryKey: platformKeys.me, queryFn: fetchPlatformMe });
  // Until /platform/me answers, treat the user as a company user: the safe (read-only) view.
  const managed = (provider: string) =>
    me.data?.super_admin !== true && catalog.data?.find((p) => p.provider === provider)?.admin_keys === true;
  const [open, setOpen] = useState<string | null>(null);

  if (integrations.isError || catalog.isError) {
    return (
      <p className="m-0 text-[13px] text-danger" role="alert">
        Failed to load integrations: {(integrations.error ?? catalog.error)?.message}
      </p>
    );
  }
  if (!integrations.data || !catalog.data) {
    return (
      <p className="m-0 text-[13px] text-muted" aria-busy="true">
        Loading…
      </p>
    );
  }
  const openSpec = open ? catalog.data.find((p) => p.provider === open) : undefined;
  const openStatus = open ? integrations.data.find((i) => i.provider === open) : undefined;
  return (
    <>
      <p className="m-0 mb-4 rounded-md border border-border bg-bg px-3 py-2 text-xs text-muted">
        Connecting verifies your credentials with the platform. Publishing ads and posts to these platforms isn&apos;t
        active yet.
      </p>
      {CATEGORY_ORDER.map((category) => {
        const items = integrations.data.filter((i) => i.category === category);
        if (items.length === 0) return null;
        return (
          <section key={category} className="mb-6">
            <h2 className="section-title">{category}</h2>
            <div className="integrations-grid">
              {items.map((i) => (
                <IntegrationCard key={i.provider} integration={i} managed={managed(i.provider)} onOpen={() => setOpen(i.provider)} />
              ))}
            </div>
          </section>
        );
      })}
      {openSpec && openStatus && (
        <ConnectPanel key={open} spec={openSpec} status={openStatus} readOnly={managed(openSpec.provider)} onClose={() => setOpen(null)} />
      )}
    </>
  );
}
