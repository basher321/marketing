"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { approvalKeys, fetchPendingApprovals } from "@/lib/api/approvals";
import { apiFetch } from "@/lib/api/client";
import { fetchPlatformMe, platformKeys } from "@/lib/api/platform";
import { fetchUser, tenantKeys } from "@/lib/api/tenant";
import { clearAuthToken, currentUser, getRefreshToken } from "@/lib/auth/token";
import type { OrgUser } from "@/lib/types/tenant";

import { Icon } from "./icons";
import { navSections, pageTitle } from "./nav";
import { openOverlay, setPrefs, usePrefs } from "./prefs";

// Top bar in the PilotSonic dashboard design: a floating glass bar with the
// sidebar toggle, the page title, the "Search pages or ask the agent" pill
// (opens the command palette, also Ctrl/⌘ K), notifications, preferences and
// the account menu.

// Logout (SPEC-FE-004 rule 8, SPEC-FE-047 G3): revoke the refresh token on the
// server (best effort; the backend always answers 204), clear it locally, then
// a full navigation to /login discards every cached tenant response.
async function logout(): Promise<void> {
  const refreshToken = getRefreshToken();
  if (refreshToken !== null) {
    try {
      await apiFetch<void>("/api/v1/auth/logout", { method: "POST", body: { refresh_token: refreshToken } });
    } catch {
      // Offline or server down: still sign out locally.
    }
  }
  clearAuthToken();
  window.location.replace("/login");
}

export function displayName(user: OrgUser | undefined): string {
  if (!user) return "";
  return [user.first_name, user.last_name].filter(Boolean).join(" ") || user.email;
}

function initials(user: OrgUser | undefined): string {
  if (!user) return "";
  const name = [user.first_name, user.last_name].filter((p): p is string => !!p?.trim());
  const letters = name.length > 0 ? name.map((p) => p.trim()[0]).join("") : user.email.slice(0, 2);
  return letters.slice(0, 2).toUpperCase();
}

/** The signed-in user (GET /users/{id}); shared with the Dashboard greeting. */
export function useSignedInUser() {
  const [userId, setUserId] = useState<string | null>(null);
  // localStorage/sessionStorage are browser-only, so the id is read after mount.
  useEffect(() => setUserId(currentUser()), []);
  return useQuery({
    queryKey: tenantKeys.user(userId ?? ""),
    queryFn: () => fetchUser(userId!),
    enabled: !!userId,
    staleTime: 5 * 60_000,
  });
}

// One popover open at a time; outside click and Escape close it.
function usePopover() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return { open, setOpen, ref };
}

function ago(seconds: number): string {
  if (seconds < 60) return "just now";
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} hour${h === 1 ? "" : "s"} ago`;
  const d = Math.floor(h / 24);
  return `${d} day${d === 1 ? "" : "s"} ago`;
}

// The design's notification bell. The backend has no notifications feed, so it
// lists what really waits for the user: pending approvals (the same query and
// cache as Command Chat's Pending Approvals panel).
function Notifications() {
  const { open, setOpen, ref } = usePopover();
  const pending = useQuery({ queryKey: approvalKeys.pending, queryFn: fetchPendingApprovals });
  const items = pending.data?.items ?? [];
  return (
    <div className="pop-wrap" ref={ref}>
      <button
        type="button"
        className="icon-btn"
        aria-label={items.length ? `Notifications: ${items.length} pending approvals` : "Notifications"}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <Icon name="bell" />
        {items.length > 0 && <i className="bell-dot" />}
      </button>
      <div className={`pop${open ? " open" : ""}`} role="dialog" aria-label="Notifications">
        <div className="pop-h">
          <b>Waiting for you</b>
          {items.length > 0 && <span className="ag-count">{items.length}</span>}
        </div>
        {pending.isPending ? (
          <div className="pop-f">Loading…</div>
        ) : pending.isError ? (
          <div className="pop-f">Couldn&apos;t load approvals.</div>
        ) : items.length === 0 ? (
          <div className="pop-f">You&apos;re all caught up. Nothing needs your approval.</div>
        ) : (
          <>
            {items.slice(0, 5).map((a) => (
              <Link key={a.id} href="/chat" className="nt" onClick={() => setOpen(false)}>
                <span className="nt-ico" style={{ ["--c" as string]: "var(--warn)" }}>
                  <Icon name="check" />
                </span>
                <span className="min-w-0">
                  <b className="truncate">{a.title}</b>
                  <small>
                    {a.engine ? `${a.engine} · ` : ""}
                    {ago(a.elapsed_seconds)}
                  </small>
                </span>
                <i className="nt-dot" />
              </Link>
            ))}
            <div className="pop-f">
              {items.length > 5 ? `${items.length - 5} more · ` : ""}
              <Link href="/chat" className="text-accent" onClick={() => setOpen(false)}>
                Review in Command Chat
              </Link>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function AccountMenu() {
  const { open, setOpen, ref } = usePopover();
  const user = useSignedInUser();
  const u = user.data;
  const name = displayName(u);
  return (
    <div className="pop-wrap" ref={ref}>
      <button
        type="button"
        className="avatar"
        title={u ? `Account: ${name}` : "Account"}
        aria-label="Account menu"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {initials(u) || "U"}
      </button>
      <div className={`pop acct${open ? " open" : ""}`} role="menu">
        {u ? (
          <div className="acct-who">
            <div className="avatar">{initials(u)}</div>
            <div className="min-w-0">
              <b className="truncate">{name}</b>
              <small>{u.email}</small>
              <small className="capitalize">Role: {u.role}</small>
            </div>
          </div>
        ) : (
          <div className="acct-who text-xs text-muted">{user.isError ? "Couldn't load your account." : "Loading…"}</div>
        )}
        <div className="grid gap-2">
          <Link href="/settings" role="menuitem" className="btn btn-secondary acct-btn" onClick={() => setOpen(false)}>
            <Icon name="gear" /> Settings
          </Link>
          <button type="button" role="menuitem" className="btn btn-secondary acct-btn text-danger" onClick={() => void logout()}>
            <Icon name="logout" /> Sign out
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Topbar() {
  const pathname = usePathname();
  const prefs = usePrefs();
  const me = useQuery({ queryKey: platformKeys.me, queryFn: fetchPlatformMe, staleTime: 5 * 60_000 });
  const title = pageTitle(pathname, navSections(me.data?.super_admin));
  const [mac, setMac] = useState(false);
  useEffect(() => setMac(/Mac|iPhone|iPad/.test(navigator.platform)), []);
  const toggleLabel = prefs.collapsed ? "Expand sidebar" : "Collapse sidebar";
  return (
    <header className="topbar">
      <button
        type="button"
        className="icon-btn desk-only"
        aria-label={toggleLabel}
        title={toggleLabel}
        aria-controls="app-sidebar"
        onClick={() => setPrefs({ collapsed: !prefs.collapsed })}
      >
        <Icon name="panel" />
      </button>
      <Link href="/dashboard" className="pl-mtile mob-only" aria-label="PilotSonic home" />
      <h2 key={title} className="tb-title swap">
        {title}
      </h2>
      <button type="button" className="search-pill" aria-label="Open command palette" onClick={() => openOverlay("palette")}>
        <Icon name="search" />
        <span>Search pages or ask the agent</span>
        <kbd>{mac ? "⌘ K" : "Ctrl K"}</kbd>
      </button>
      <div className="tb-right">
        <button type="button" className="icon-btn mob-only" aria-label="Search" onClick={() => openOverlay("palette")}>
          <Icon name="search" />
        </button>
        <Notifications />
        <button type="button" className="icon-btn desk-only" aria-label="Preferences" title="Preferences" onClick={() => openOverlay("prefs")}>
          <Icon name="sliders" />
        </button>
        <AccountMenu />
      </div>
    </header>
  );
}
