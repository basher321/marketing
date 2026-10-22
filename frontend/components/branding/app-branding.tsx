"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { fetchAppBranding, platformKeys } from "@/lib/api/platform";
import type { AppBranding } from "@/lib/types/platform";

const DEFAULT_NAME = "PilotSonic";

/** The app's name and logo (SPEC-FE-077 / SPEC-BE-113), loaded once and cached; null until loaded. */
export function useAppBranding(): AppBranding | null {
  const q = useQuery({ queryKey: platformKeys.branding, queryFn: fetchAppBranding, staleTime: 5 * 60_000, retry: 1 });
  return q.data ?? null;
}

/** True when the Super admin renamed the app (then the built-in word mark is replaced by text). */
export function isCustomName(b: AppBranding | null): b is AppBranding {
  return !!b && b.app_name !== DEFAULT_NAME;
}

/**
 * Puts the app name in the browser title ("Dashboard · PilotSonic" → "… · <name>")
 * and the Super admin's favicon in the tab. Renders nothing.
 */
export function AppBrandingEffects() {
  const b = useAppBranding();
  useEffect(() => {
    if (!b) return;
    if (b.favicon_url) {
      let link = document.querySelector<HTMLLinkElement>("link[rel='icon'][data-app-branding]");
      if (!link) {
        link = document.createElement("link");
        link.rel = "icon";
        link.dataset.appBranding = "1";
        document.head.appendChild(link);
      }
      link.href = b.favicon_url;
    }
    if (isCustomName(b) && document.title.includes(DEFAULT_NAME)) {
      document.title = document.title.replaceAll(DEFAULT_NAME, b.app_name);
    }
  }, [b]);
  return null;
}

/**
 * The same branding for pages outside the app shell (sign-in), which have no
 * TanStack Query provider: one plain request, the built-in brand if it fails.
 */
export function useAppBrandingStandalone(): AppBranding | null {
  const [b, setB] = useState<AppBranding | null>(null);
  useEffect(() => {
    let live = true;
    fetchAppBranding()
      .then((x) => live && setB(x))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);
  return b;
}
