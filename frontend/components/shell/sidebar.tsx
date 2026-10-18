"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { fetchPlatformMe, platformKeys } from "@/lib/api/platform";
import { fetchTenant, tenantKeys } from "@/lib/api/tenant";

// Sidebar (SPEC-FE-002). Sections, labels, routes and icon glyphs are copied
// from the reference mockup's <aside class="sidebar"> (the glyphs are the
// literal Unicode characters, not an icon font). Styling reproduces the
// mockup's .sidebar/.brand/.brand-logo/.nav-section/.nav-item/.nav-icon rules
// with SPEC-FE-001 tokens plus Tailwind default colors whose values equal the
// mockup's non-token colors exactly: white = #fff, slate-500 = #64748b,
// indigo-500 = #6366f1 (sidebar-hover = #1e293b and chart-2 = #06b6d4 are tokens).
type NavItem = { label: string; href: string; icon: string; children?: { label: string; href: string }[] };

// Marketing is a group (SPEC-FE-049): Paid Marketing (the former top-level
// "Campaigns") and Organic Marketing.
const NAV_SECTIONS: { title: string; items: NavItem[] }[] = [
  {
    title: "Main",
    items: [
      { label: "Dashboard", href: "/dashboard", icon: "◉" },
      { label: "Command Chat", href: "/chat", icon: "◈" },
    ],
  },
  {
    title: "Engines",
    items: [
      { label: "E-Commerce", href: "/ecommerce", icon: "▤" },
      {
        label: "Marketing",
        href: "/marketing",
        icon: "◍",
        children: [
          { label: "Paid Marketing", href: "/marketing/paid" },
          { label: "Organic Marketing", href: "/marketing/organic" },
          { label: "SocialAPI", href: "/marketing/organic/socialapi" }, // SPEC-FE-054
        ],
      },
      { label: "Customer Service", href: "/customer", icon: "◐" },
    ],
  },
  {
    title: "Configuration",
    items: [
      { label: "Knowledge Base", href: "/kb", icon: "▦" },
      { label: "Workflows", href: "/workflows", icon: "◇" },
      { label: "Analytics", href: "/analytics", icon: "▨" },
      { label: "Integrations", href: "/integrations", icon: "◎" },
      // Organization Settings (SPEC-FE-036); not in the mockup.
      { label: "Settings", href: "/settings", icon: "⚙" },
    ],
  },
];

// SPEC-FE-068: only PilotSonic's Super admin sees this section (GET /platform/me).
const SUPER_ADMIN_SECTION: { title: string; items: NavItem[] } = {
  title: "PilotSonic",
  items: [{ label: "Super admin", href: "/admin", icon: "★" }],
};

// SPEC-FE-063: the top bar's ☰ button (a separate client component) opens the
// drawer through this window event; no shared provider is needed.
export const TOGGLE_NAV_EVENT = "shell:toggle-nav";

function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function itemClass(active: boolean): string {
  return `flex cursor-pointer items-center gap-[10px] rounded-md px-3 py-[9px] text-[13.5px] transition-[background] duration-150 ${
    active ? "bg-sidebar-active text-white" : "text-sidebar-text hover:bg-sidebar-hover hover:text-white"
  }`;
}

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

export default function Sidebar() {
  const pathname = usePathname();
  // The company logo (SPEC-FE-036), when one is uploaded; otherwise the
  // mockup's "AI" mark. Shares the Settings page's cache key.
  const tenant = useQuery({ queryKey: tenantKeys.me, queryFn: fetchTenant, staleTime: 60_000 });
  const logo = tenant.data?.branding.logo_url ?? null;
  const me = useQuery({ queryKey: platformKeys.me, queryFn: fetchPlatformMe, staleTime: 5 * 60_000 });
  const sections = me.data?.super_admin ? [...NAV_SECTIONS, SUPER_ADMIN_SECTION] : NAV_SECTIONS;
  const [openGroups, setOpenGroups] = useState<string[]>([]);
  useEffect(() => setOpenGroups(readOpenGroups()), []);
  // Below 1024px the sidebar is a drawer (SPEC-FE-063): ☰ opens it; the
  // backdrop, ✕, Escape or choosing a page closes it.
  const [drawer, setDrawer] = useState(false);
  useEffect(() => {
    const toggle = () => setDrawer((v) => !v);
    window.addEventListener(TOGGLE_NAV_EVENT, toggle);
    return () => window.removeEventListener(TOGGLE_NAV_EVENT, toggle);
  }, []);
  useEffect(() => setDrawer(false), [pathname]);
  useEffect(() => {
    if (!drawer) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDrawer(false);
    };
    window.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
    };
  }, [drawer]);
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
    <>
      {drawer && (
        <div
          className="fixed inset-0 z-40 lg:hidden"
          style={{ background: "color-mix(in srgb, var(--sidebar-bg) 60%, transparent)" }}
          onClick={() => setDrawer(false)}
          aria-hidden="true"
          data-testid="sidebar-backdrop"
        />
      )}
    {/* From 1024px: pinned to the viewport (the page scrolls, the sidebar stays
        put; its own list scrolls if taller than the screen). Below: a drawer,
        invisible to keyboard and screen readers while closed. */}
    <nav
      id="app-sidebar"
      aria-label="Main navigation"
      className={`fixed inset-y-0 left-0 z-50 flex h-screen w-[260px] flex-col gap-1 overflow-y-auto bg-sidebar-bg px-3 py-5 text-sidebar-text transition-[transform,visibility] duration-200 lg:sticky lg:top-0 lg:z-auto lg:w-auto lg:translate-x-0 lg:self-start ${
        drawer ? "translate-x-0 shadow-2xl" : "max-lg:invisible max-lg:-translate-x-full"
      }`}
    >
      <div className="mb-3 flex items-center gap-[10px] border-b border-sidebar-hover px-3 pb-5 pt-2 text-base font-bold text-white">
        {logo ? (
          // A data: URL, so next/image optimisation doesn't apply.

          <img src={logo} alt={`${tenant.data?.name ?? "Company"} logo`} className="h-7 w-7 rounded-md object-cover" data-testid="sidebar-logo" />
        ) : (
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-gradient-to-br from-indigo-500 to-chart-2 text-sm">
            AI
          </div>
        )}
        {/* Two-tone like the logo (SPEC-FE-043); sky-400 is the closest default to its blue. */}
        <div className="flex-1">
          Pilot<span className="text-sky-400">Sonic</span>
        </div>
        <button
          type="button"
          aria-label="Close menu"
          onClick={() => setDrawer(false)}
          className="rounded px-2 py-1 text-sm font-normal text-sidebar-text hover:bg-sidebar-hover hover:text-white lg:hidden"
        >
          ✕
        </button>
      </div>
      {sections.map((section) => (
        <div key={section.title} className="contents">
          <div className="px-3 pb-[6px] pt-[14px] text-[11px] uppercase tracking-[.05em] text-slate-500">
            {section.title}
          </div>
          {section.items.map((item) => {
            if (!item.children) {
              const active = isActive(pathname, item.href);
              return (
                <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined} data-active={active ? "true" : undefined} className={itemClass(active)}>
                  <span className="w-4 text-center text-sm">{item.icon}</span> {item.label}
                </Link>
              );
            }
            // A group: the parent is active only on its own page (the overview);
            // it opens automatically on any route under it, or when toggled.
            const inGroup = isActive(pathname, item.href);
            const open = inGroup || openGroups.includes(item.href);
            const active = pathname === item.href;
            return (
              <div key={item.href} className="contents">
                <div className={`${itemClass(active)} pr-1`} data-active={active ? "true" : undefined}>
                  <Link href={item.href} aria-current={active ? "page" : undefined} className="flex flex-1 items-center gap-[10px] text-inherit no-underline">
                    <span className="w-4 text-center text-sm">{item.icon}</span> {item.label}
                  </Link>
                  <button
                    type="button"
                    aria-label={open ? `Collapse ${item.label}` : `Expand ${item.label}`}
                    aria-expanded={open}
                    disabled={inGroup}
                    onClick={() => toggleGroup(item.href)}
                    className="rounded px-1.5 text-xs text-inherit disabled:cursor-default"
                  >
                    {open ? "▾" : "▸"}
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
                        className={`${itemClass(childActive)} pl-[38px] text-[13px]`}
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
    </>
  );
}
