"use client";

import { useSyncExternalStore } from "react";

// Display preferences from the PilotSonic design's Preferences sheet. They are
// per-browser conveniences only (localStorage, guarded: storage can be missing
// in private mode or blocked), applied as attributes / CSS variables on <html>.
// The same key and rules are read by the boot script in app/layout.tsx so the
// first paint already has the right theme and accent.
export type Prefs = {
  theme: "light" | "dark" | "auto";
  accent: string;
  density: "comfortable" | "compact";
  motion: "full" | "off";
  spotlight: boolean;
  collapsed: boolean;
};

export const PREFS_KEY = "pilotsonic.prefs";

export const DEFAULT_PREFS: Prefs = {
  theme: "auto",
  accent: "#4f46e5",
  density: "comfortable",
  motion: "full",
  spotlight: true,
  collapsed: false,
};

// The design's five accent swatches.
export const ACCENTS: { label: string; value: string }[] = [
  { label: "Indigo", value: "#4f46e5" },
  { label: "Violet", value: "#7c3aed" },
  { label: "Teal", value: "#0d9488" },
  { label: "Rose", value: "#e11d48" },
  { label: "Orange", value: "#ea580c" },
];

function read(): Prefs {
  try {
    const raw = window.localStorage.getItem(PREFS_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : {};
    return { ...DEFAULT_PREFS, ...(parsed && typeof parsed === "object" ? parsed : {}) } as Prefs;
  } catch {
    return DEFAULT_PREFS;
  }
}

let current: Prefs | null = null;
const listeners = new Set<() => void>();

export function applyPrefs(p: Prefs): void {
  const html = document.documentElement;
  if (p.theme === "auto") html.removeAttribute("data-theme");
  else html.dataset.theme = p.theme;
  html.dataset.density = p.density;
  html.dataset.motion = p.motion;
  html.dataset.spot = p.spotlight ? "on" : "off";
  for (const v of ["--accent", "--chart-1", "--sidebar-active"]) html.style.setProperty(v, p.accent);
}

export function getPrefs(): Prefs {
  if (current === null) current = read();
  return current;
}

export function setPrefs(patch: Partial<Prefs>): void {
  current = { ...getPrefs(), ...patch };
  try {
    window.localStorage.setItem(PREFS_KEY, JSON.stringify(current));
  } catch {
    // Not remembered; still applied for this visit.
  }
  applyPrefs(current);
  listeners.forEach((l) => l());
}

export function resetPrefs(): void {
  setPrefs(DEFAULT_PREFS);
}

function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function usePrefs(): Prefs {
  return useSyncExternalStore(subscribe, getPrefs, () => DEFAULT_PREFS);
}

/** Dark right now: an explicit theme, else the device setting. */
export function isDarkNow(): boolean {
  const t = document.documentElement.dataset.theme;
  return t ? t === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
}

// Overlays (palette, sheets) are opened from several components; a window
// event avoids a shared provider, as the old drawer toggle did.
export const OPEN_OVERLAY_EVENT = "shell:open-overlay";
export type Overlay = "palette" | "prefs" | "more";

export function openOverlay(which: Overlay): void {
  window.dispatchEvent(new CustomEvent<Overlay>(OPEN_OVERLAY_EVENT, { detail: which }));
}
