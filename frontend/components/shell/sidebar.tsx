"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { AppBrandingEffects, isCustomName, useAppBranding } from "@/components/branding/app-branding";
import { fetchPlatformMe, platformKeys } from "@/lib/api/platform";
import { fetchTenant, tenantKeys } from "@/lib/api/tenant";
import { fetchMyProfile, userKeys } from "@/lib/api/users";
import { fetchWorkflows, workflowKeys } from "@/lib/api/workflows";

import { Icon } from "./icons";
import { forRole, isActive, navSections } from "./nav";
import { usePrefs } from "./prefs";

// Sidebar in the PilotSonic dashboard design: a floating rounded panel with the
// PilotSonic logo tile, the Main / Engines / Configuration sections, line icons
// and an accent pill on the active page. "Compact sidebar" (Preferences or the
// top bar's panel button) collapses it to icons. Below 900px it is hidden and
// the mobile tab bar takes over (components/shell/mobile-nav.tsx).

// Manually opened groups, remembered per browser. Storage can be unavailable
// (private mode, blocked site data), so every access is guarded.
const OPEN_GROUPS_KEY = "sidebar.openGroups";

function readOpenGroups(): string[] {
  try {
    const raw = window.localStorage.getItem(OPEN_GROUPS_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === "string") : [];
  } catch {
    return [];
  }
}

// The design's "Autopilot" card, with the real number of enabled workflows
// (the same list and rule as the Dashboard's "Active workflows"). There is no
// global autopilot switch in the backend, so the card links to Workflows
// instead of showing a toggle.
function AutopilotCard() {
  const workflows = useQuery({ queryKey: workflowKeys.list, queryFn: fetchWorkflows });
  const enabled = workflows.data?.filter((w) => w.status === "Enabled").length ?? 0;
  const sub = workflows.isPending
    ? "Loading…"
    : workflows.isError
      ? "Couldn't load workflows"
      : enabled === 0
        ? "No workflows running"
        : `${enabled} workflow${enabled === 1 ? "" : "s"} running`;
  return (
    <Link href="/workflows" className={`sb-card${enabled === 0 ? " off" : ""}`} title="Autopilot: your enabled workflows">
      <span className="sb-orb" aria-hidden="true" />
      <span className="tx">
        <b>Autopilot</b>
        <small>{sub}</small>
      </span>
    </Link>
  );
}

export default function Sidebar() {
  const pathname = usePathname();
  const prefs = usePrefs();
  // The company logo (SPEC-FE-036) replaces the PilotSonic mark when uploaded.
  const tenant = useQuery({ queryKey: tenantKeys.me, queryFn: fetchTenant, staleTime: 60_000 });
  // SPEC-FE-077: then the Super admin's app logo, then the built-in mark.
  const app = useAppBranding();
  const logo = tenant.data?.branding.logo_url ?? app?.logo_url ?? null;
  const me = useQuery({ queryKey: platformKeys.me, queryFn: fetchPlatformMe, staleTime: 5 * 60_000 });
  const profile = useQuery({ queryKey: userKeys.me, queryFn: fetchMyProfile, staleTime: 5 * 60_000 });
  const sections = forRole(navSections(me.data?.super_admin), profile.data?.role);
  const [openGroups, setOpenGroups] = useState<string[]>([]);
  useEffect(() => setOpenGroups(readOpenGroups()), []);
  const toggleGroup = (href: string) =>
    setOpenGroups((prev) => {
      const next = prev.includes(href) ? prev.filter((h) => h !== href) : [...prev, href];
      try {
        window.localStorage.setItem(OPEN_GROUPS_KEY, JSON.stringify(next));
      } catch {
        // Not remembered; the toggle still works for this page view.
      }
      return next;
    });

  return (
    <aside className="sidebar" aria-label="Main navigation" id="app-sidebar">
      <div className="sb">
        <AppBrandingEffects />
        <Link href="/dashboard" className="brand" aria-label={`${app?.app_name ?? "PilotSonic"} home`}>
          {logo ? (
            // A data: URL, so next/image optimisation doesn't apply.
            <img src={logo} alt={`${tenant.data?.name ?? "Company"} logo`} className="brand-img" data-testid="sidebar-logo" />
          ) : (
            <span className="pl-m" role="img" aria-label="PilotSonic logo" />
          )}
          <span className="lbl">
            {isCustomName(app) ? (
              <span className="font-bold">{app.app_name}</span>
            ) : (
              <span className="pl-w" role="img" aria-label="PilotSonic" />
            )}
          </span>
        </Link>
        <nav className="nav">
          {sections.map((section) => (
            <div key={section.title} className="contents">
              <div className="nav-section">
                <span className="lbl">{section.title}</span>
              </div>
              {section.items.map((item) => {
                if (!item.children) {
                  const active = isActive(pathname, item.href);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      title={item.label}
                      aria-current={active ? "page" : undefined}
                      data-active={active ? "true" : undefined}
                      className={`nav-item${active ? " active" : ""}`}
                    >
                      <Icon name={item.icon} />
                      <span className="lbl">{item.label}</span>
                    </Link>
                  );
                }
                // A group: the parent is active only on its own page (the
                // overview); it opens on any route under it, or when toggled.
                const inGroup = isActive(pathname, item.href);
                const open = !prefs.collapsed && (inGroup || openGroups.includes(item.href));
                const active = pathname === item.href || (prefs.collapsed && inGroup);
                return (
                  <div key={item.href} className="contents">
                    <div className={`nav-item has-sub${active ? " active" : ""}`} data-active={active ? "true" : undefined}>
                      <Link href={item.href} title={item.label} aria-current={pathname === item.href ? "page" : undefined} className="nav-link">
                        <Icon name={item.icon} />
                        <span className="lbl">{item.label}</span>
                      </Link>
                      <button
                        type="button"
                        className="nav-caret lbl"
                        aria-label={open ? `Collapse ${item.label}` : `Expand ${item.label}`}
                        aria-expanded={open}
                        disabled={inGroup}
                        onClick={() => toggleGroup(item.href)}
                      >
                        <Icon name="chevron" className={`ic ic-sm${open ? " rot" : ""}`} />
                      </button>
                    </div>
                    {open &&
                      item.children.map((child) => {
                        const childActive = isActive(pathname, child.href);
                        return (
                          <Link
                            key={child.href}
                            href={child.href}
                            aria-current={childActive ? "page" : undefined}
                            data-active={childActive ? "true" : undefined}
                            className={`nav-sub${childActive ? " active" : ""}`}
                          >
                            {child.label}
                          </Link>
                        );
                      })}
                  </div>
                );
              })}
            </div>
          ))}
        </nav>
        <AutopilotCard />
      </div>
    </aside>
  );
}
