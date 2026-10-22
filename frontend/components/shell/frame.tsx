"use client";

import { useEffect, type PointerEvent, type ReactNode } from "react";

import { applyPrefs, getPrefs, usePrefs } from "./prefs";

// The cards that get the design's pointer "spotlight" glow.
const SPOT = ".card, .engine-card, .integration-card, .kb-item, .qa-card, .wf-node";

// The .app frame: sidebar + main column, sized to the viewport so only
// .content scrolls. Applies the saved display preferences once mounted (the
// boot script in app/layout.tsx already set them before first paint).
export default function ShellFrame({ sidebar, topbar, children }: { sidebar: ReactNode; topbar: ReactNode; children: ReactNode }) {
  const prefs = usePrefs();
  useEffect(() => applyPrefs(getPrefs()), []);

  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!prefs.spotlight || e.pointerType === "touch") return;
    const el = (e.target as Element).closest<HTMLElement>(SPOT);
    if (!el) return;
    const r = el.getBoundingClientRect();
    el.style.setProperty("--mx", `${e.clientX - r.left}px`);
    el.style.setProperty("--my", `${e.clientY - r.top}px`);
  };

  return (
    <div className={`app${prefs.collapsed ? " collapsed" : ""}`}>
      {sidebar}
      <main className="main">
        {topbar}
        <div className="content" onPointerMove={onPointerMove}>
          {children}
        </div>
      </main>
    </div>
  );
}
