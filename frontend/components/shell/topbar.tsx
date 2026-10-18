"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { apiFetch } from "@/lib/api/client";
import { fetchUser, tenantKeys } from "@/lib/api/tenant";
import { clearAuthToken, currentUser, getRefreshToken } from "@/lib/auth/token";
import type { OrgUser } from "@/lib/types/tenant";

import { TOGGLE_NAV_EVENT } from "./sidebar";

// Topbar (SPEC-FE-002), reproducing the mockup's .topbar/.search/.topbar-right/
// .icon-btn/.avatar rules. The search input does nothing and the two icon
// buttons have no click handler or dropdown.
//
// The avatar (the mockup's fixed "RB") shows the signed-in user's initials and
// opens an account menu: name, email, role, and Log out. Logout (SPEC-FE-004
// rule 8) clears
// the stored token and does a full navigation to /login, which also discards
// every cached tenant response (same path as the 401 handler in
// app/(app)/providers.tsx).
// SPEC-FE-047 G3: the refresh token is revoked on the server first (best effort;
// the backend always answers 204), so a copied token stops working too.
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

function initials(user: OrgUser | undefined): string {
  if (!user) return "";
  const name = [user.first_name, user.last_name].filter((p): p is string => !!p?.trim());
  const letters = name.length > 0 ? name.map((p) => p.trim()[0]).join("") : user.email.slice(0, 2);
  return letters.slice(0, 2).toUpperCase();
}

function AccountMenu() {
  const [open, setOpen] = useState(false);
  const [userId, setUserId] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  // localStorage/sessionStorage are browser-only, so the id is read after mount.
  useEffect(() => setUserId(currentUser()), []);
  const user = useQuery({
    queryKey: tenantKeys.user(userId ?? ""),
    queryFn: () => fetchUser(userId!),
    enabled: !!userId,
    staleTime: 5 * 60_000,
  });

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

  const u = user.data;
  const name = u ? [u.first_name, u.last_name].filter(Boolean).join(" ") || u.email : "";
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        title={u ? `Account: ${name}` : "Account"}
        aria-label="Account menu"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex h-[34px] w-[34px] cursor-pointer items-center justify-center rounded-full border-none bg-gradient-to-br from-indigo-500 to-chart-2 text-xs font-semibold text-white"
      >
        {initials(u) || "👤"}
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-[42px] z-50 w-[240px] rounded-md border border-border bg-panel p-3 text-text shadow-lg"
        >
          {u ? (
            <div className="mb-3 border-b border-border pb-3">
              <div className="truncate font-semibold">{name}</div>
              <div className="truncate text-xs text-muted">{u.email}</div>
              <div className="mt-1 text-xs capitalize text-muted">Role: {u.role}</div>
            </div>
          ) : (
            <div className="mb-3 border-b border-border pb-3 text-xs text-muted">
              {user.isError ? "Couldn't load your account." : "Loading…"}
            </div>
          )}
          <button
            type="button"
            role="menuitem"
            onClick={() => void logout()}
            className="w-full cursor-pointer rounded-md border border-border bg-bg px-3 py-2 text-left text-danger"
          >
            Log out
          </button>
        </div>
      )}
    </div>
  );
}

export default function Topbar() {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border bg-panel px-4 py-3 lg:px-6">
      {/* SPEC-FE-063: below 1024px the sidebar is a drawer this button opens. */}
      <button
        type="button"
        aria-label="Open menu"
        aria-controls="app-sidebar"
        onClick={() => window.dispatchEvent(new Event(TOGGLE_NAV_EVENT))}
        className="flex h-[34px] w-[34px] shrink-0 cursor-pointer items-center justify-center rounded-md border border-border bg-panel text-text lg:hidden"
      >
        ☰
      </button>
      <input
        className="min-w-0 max-w-[420px] flex-1 rounded-md border border-border bg-bg px-3 py-2 text-text"
        placeholder="Search products, orders, campaigns..."
        aria-label="Search"
      />
      <div className="flex shrink-0 items-center gap-2 lg:gap-3">
        <button
          type="button"
          title="Notifications"
          aria-label="Notifications"
          className="flex h-[34px] w-[34px] cursor-pointer items-center justify-center rounded-md border border-border bg-panel text-text"
        >
          ◔
        </button>
        {/* The mockup's settings icon, now opening Organization Settings (SPEC-FE-036). */}
        <Link
          href="/settings"
          title="Settings"
          aria-label="Settings"
          className="flex h-[34px] w-[34px] cursor-pointer items-center justify-center rounded-md border border-border bg-panel text-text no-underline"
        >
          ◈
        </Link>
        <AccountMenu />
      </div>
    </div>
  );
}
