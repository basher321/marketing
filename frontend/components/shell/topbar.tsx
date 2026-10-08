"use client";

import Link from "next/link";

import { apiFetch } from "@/lib/api/client";
import { clearAuthToken, getRefreshToken } from "@/lib/auth/token";

// Topbar (SPEC-FE-002), reproducing the mockup's .topbar/.search/.topbar-right/
// .icon-btn/.avatar rules. The search input does nothing and the two icon
// buttons have no click handler or dropdown; "RB" is fixed text, not derived
// from any user data.
//
// Logout (SPEC-FE-004 rule 8): the mockup has no logout control, so the
// previously decorative avatar is repurposed as the logout button. It clears
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

export default function Topbar() {
  return (
    <div className="flex items-center justify-between border-b border-border bg-panel px-6 py-3">
      <input
        className="max-w-[420px] flex-1 rounded-md border border-border bg-bg px-3 py-2 text-text"
        placeholder="Search products, orders, campaigns..."
        aria-label="Search"
      />
      <div className="flex items-center gap-3">
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
        <button
          type="button"
          title="Log out"
          aria-label="Log out"
          onClick={() => void logout()}
          className="flex h-[34px] w-[34px] cursor-pointer items-center justify-center rounded-full border-none bg-gradient-to-br from-indigo-500 to-chart-2 text-xs font-semibold text-white"
        >
          RB
        </button>
      </div>
    </div>
  );
}
