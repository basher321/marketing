"use client";

import { useRouter } from "next/navigation";
import { useRef } from "react";

/**
 * "One new tab per new thing" (SPEC-FE-058).
 *
 * - Entry buttons ("+ New campaign", "Create post", "Create with AI") are
 *   target="_blank" links to newTabHref(path). The new tab loads with nt=1 and
 *   rememberNewThingTab() marks it (per-tab sessionStorage).
 * - After a create, useCreatedItemTab() opens the created item in a new tab,
 *   except in a marked tab: that tab already belongs to the new thing, so the
 *   editor replaces the used form there and the mark is cleared.
 *
 * Browsers only allow window.open during a click, so begin() opens a blank
 * "Opening…" tab in the click handler, and open(path) points it at the item
 * once the server has created it.
 */
const MARK = "aio:new-thing-tab";
const PARAM = "nt";

export function newTabHref(path: string): string {
  return `${path}${path.includes("?") ? "&" : "?"}${PARAM}=1`;
}

export function rememberNewThingTab(): void {
  try {
    if (new URLSearchParams(window.location.search).get(PARAM) === "1") sessionStorage.setItem(MARK, "1");
  } catch {
    // storage blocked: every create then opens a new tab, which is still correct
  }
}

function marked(): boolean {
  try {
    return sessionStorage.getItem(MARK) === "1";
  } catch {
    return false;
  }
}

function unmark(): void {
  try {
    sessionStorage.removeItem(MARK);
  } catch {
    // nothing to clear
  }
}

function openBlankTab(): Window | null {
  const tab = window.open("", "_blank");
  if (!tab) return null; // pop-up blocked
  try {
    tab.opener = null;
    tab.document.title = "Opening…";
    tab.document.body.innerHTML = '<p style="font:14px system-ui,sans-serif;padding:24px;color:#64748b">Opening…</p>';
  } catch {
    // cosmetic only
  }
  return tab;
}

export function useCreatedItemTab() {
  const router = useRouter();
  const tab = useRef<Window | null>(null);
  const inPlace = useRef(false);
  return {
    /** Call in the click/submit handler, before mutate(). */
    begin(): void {
      inPlace.current = marked();
      tab.current = inPlace.current ? null : openBlankTab();
    },
    /** Call in onSuccess with the created item's path. */
    open(path: string): void {
      const target = tab.current;
      tab.current = null;
      if (inPlace.current) {
        unmark();
        router.replace(path);
      } else if (target && !target.closed) {
        target.location.href = new URL(path, window.location.origin).href;
      } else {
        router.push(path); // the browser blocked the new tab
      }
    },
    /** Call in onError: closes the blank tab so the error shows here. */
    cancel(): void {
      tab.current?.close();
      tab.current = null;
    },
  };
}
