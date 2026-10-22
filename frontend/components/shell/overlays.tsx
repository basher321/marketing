"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { fetchPlatformMe, platformKeys } from "@/lib/api/platform";
import { fetchMyProfile, userKeys } from "@/lib/api/users";

import { Icon, type IconName } from "./icons";
import { AGENT_PROMPTS, askHref, flatPages, forRole, isActive, NAV_SECTIONS, navSections, SUPER_ADMIN_SECTION, TAB_ITEMS } from "./nav";
import {
  ACCENTS,
  isDarkNow,
  OPEN_OVERLAY_EVENT,
  resetPrefs,
  setPrefs,
  usePrefs,
  type Overlay,
  type Prefs,
} from "./prefs";

// The PilotSonic design's overlays: the command palette (Ctrl/⌘ K), the
// Preferences sheet, and on phones the bottom tab bar with its More sheet.
// They open through openOverlay() (a window event) from the top bar and here.

function useSections() {
  const me = useQuery({ queryKey: platformKeys.me, queryFn: fetchPlatformMe, staleTime: 5 * 60_000 });
  const profile = useQuery({ queryKey: userKeys.me, queryFn: fetchMyProfile, staleTime: 5 * 60_000 });
  return forRole(navSections(me.data?.super_admin), profile.data?.role);
}

function iconFor(href: string): IconName {
  for (const s of [...NAV_SECTIONS, SUPER_ADMIN_SECTION]) {
    for (const i of s.items) if (i.href === href || i.children?.some((c) => c.href === href)) return i.icon;
  }
  return "grid";
}

type Cmd = { group: "Go to" | "Ask the agent" | "Options"; label: string; icon: IconName; run: () => void };

function Palette({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const sections = useSections();
  const prefs = usePrefs();
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  useEffect(() => {
    const t = setTimeout(() => inputRef.current?.focus(), 60);
    return () => clearTimeout(t);
  }, []);

  const all = useMemo<Cmd[]>(
    () => [
      ...flatPages(sections).map((p) => ({ group: "Go to" as const, label: p.label, icon: iconFor(p.href), run: () => router.push(p.href) })),
      ...AGENT_PROMPTS.map((t) => ({ group: "Ask the agent" as const, label: t, icon: "bolt" as const, run: () => router.push(askHref(t)) })),
      {
        group: "Options",
        label: isDarkNow() ? "Switch to light theme" : "Switch to dark theme",
        icon: "moon",
        run: () => setPrefs({ theme: isDarkNow() ? "light" : "dark" }),
      },
      { group: "Options", label: "Open preferences", icon: "sliders", run: () => window.setTimeout(() => window.dispatchEvent(new CustomEvent(OPEN_OVERLAY_EVENT, { detail: "prefs" })), 0) },
      { group: "Options", label: prefs.collapsed ? "Expand sidebar" : "Collapse sidebar", icon: "panel", run: () => setPrefs({ collapsed: !prefs.collapsed }) },
    ],
    [sections, router, prefs.collapsed],
  );
  const text = q.trim();
  const shown = useMemo(() => {
    const needle = text.toLowerCase();
    const list = all.filter((c) => !needle || `${c.label} ${c.group}`.toLowerCase().includes(needle));
    if (text && !list.some((c) => c.group === "Ask the agent")) {
      list.push({ group: "Ask the agent", label: `Ask: ${text}`, icon: "bolt", run: () => router.push(askHref(text)) });
    }
    return list;
  }, [all, text, router]);
  const active = Math.min(sel, Math.max(shown.length - 1, 0));

  const runAt = (i: number) => {
    const c = shown[i];
    if (!c) return;
    onClose();
    c.run();
  };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!shown.length) return;
      const next = (active + (e.key === "ArrowDown" ? 1 : -1) + shown.length) % shown.length;
      setSel(next);
      listRef.current?.querySelector(`#po${next}`)?.scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      e.preventDefault();
      runAt(active);
    } else if (e.key === "Tab") {
      e.preventDefault();
    }
  };

  let lastGroup = "";
  return (
    <div className="pal open" onKeyDown={onKey}>
      <div className="pal-bg" onClick={onClose} />
      <div className="pal-box" role="dialog" aria-modal="true" aria-label="Command palette">
        <div className="pal-in">
          <Icon name="search" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setSel(0);
            }}
            placeholder="Search pages, or type a request for the agent"
            autoComplete="off"
            spellCheck={false}
            aria-label="Search"
            aria-activedescendant={shown.length ? `po${active}` : undefined}
          />
          <kbd>Esc</kbd>
        </div>
        <ul className="pal-list" role="listbox" ref={listRef}>
          {shown.length === 0 && <li className="pal-empty">Nothing matches.</li>}
          {shown.map((c, i) => {
            const head = c.group !== lastGroup;
            lastGroup = c.group;
            return (
              <li key={`${c.group}:${c.label}`} role="presentation">
                {head && <div className="pal-g">{c.group}</div>}
                <div
                  id={`po${i}`}
                  role="option"
                  aria-selected={i === active}
                  className={`pal-it${i === active ? " sel" : ""}`}
                  onMouseMove={() => i !== active && setSel(i)}
                  onClick={() => runAt(i)}
                >
                  <Icon name={c.icon} />
                  <span>{c.label}</span>
                  <small>{c.group === "Go to" ? "Page" : c.group === "Options" ? "Option" : "Agent"}</small>
                </div>
              </li>
            );
          })}
        </ul>
        <div className="pal-foot">
          <span>↑ ↓ to move</span>
          <span>Enter to open</span>
          <span>Esc to close</span>
        </div>
      </div>
    </div>
  );
}

function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const t = setTimeout(() => closeRef.current?.focus(), 120);
    return () => clearTimeout(t);
  }, []);
  return (
    <div className="sheet open">
      <div className="sheet-bg" onClick={onClose} />
      <div className="sheet-panel" role="dialog" aria-modal="true" aria-label={title}>
        <div className="sheet-h">
          <span className="sheet-grip" />
          <h2>{title}</h2>
          <button ref={closeRef} type="button" className="icon-btn sm" aria-label="Close" onClick={onClose}>
            <Icon name="x" />
          </button>
        </div>
        <div className="sheet-body">{children}</div>
      </div>
    </div>
  );
}

function Seg<K extends keyof Prefs>({ k, options, value }: { k: K; options: { v: Prefs[K]; label: string }[]; value: Prefs[K] }) {
  return (
    <div className="seg" role="radiogroup">
      {options.map((o) => (
        <button
          key={String(o.v)}
          type="button"
          role="radio"
          aria-checked={value === o.v}
          className={value === o.v ? "on" : ""}
          onClick={() => setPrefs({ [k]: o.v } as Partial<Prefs>)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function Switch({ checked, label, onChange }: { checked: boolean; label: string; onChange: (v: boolean) => void }) {
  return (
    <label className="ag-switch">
      <input type="checkbox" checked={checked} aria-label={label} onChange={(e) => onChange(e.target.checked)} />
      <span />
    </label>
  );
}

function PrefsSheet({ onClose }: { onClose: () => void }) {
  const p = usePrefs();
  return (
    <Sheet title="Preferences" onClose={onClose}>
      <div className="opt">
        <h3>Theme</h3>
        <p>Match your device or pick one.</p>
        <Seg k="theme" value={p.theme} options={[{ v: "light", label: "Light" }, { v: "dark", label: "Dark" }, { v: "auto", label: "Auto" }]} />
      </div>
      <div className="opt">
        <h3>Accent colour</h3>
        <p>Buttons, highlights and charts follow it.</p>
        <div className="swatches">
          {ACCENTS.map((a) => (
            <button
              key={a.value}
              type="button"
              className="sw-btn"
              style={{ ["--c" as string]: a.value }}
              aria-label={a.label}
              aria-pressed={p.accent === a.value}
              onClick={() => setPrefs({ accent: a.value })}
            >
              <Icon name="check" />
            </button>
          ))}
        </div>
      </div>
      <div className="opt">
        <h3>Density</h3>
        <p>Compact fits more on each screen.</p>
        <Seg k="density" value={p.density} options={[{ v: "comfortable", label: "Comfortable" }, { v: "compact", label: "Compact" }]} />
      </div>
      <div className="opt">
        <div className="opt-row">
          <div>
            <h3>Smooth animations</h3>
            <p>Turn off to remove all motion.</p>
          </div>
          <Switch checked={p.motion === "full"} label="Smooth animations" onChange={(v) => setPrefs({ motion: v ? "full" : "off" })} />
        </div>
      </div>
      <div className="opt">
        <div className="opt-row">
          <div>
            <h3>Card spotlight</h3>
            <p>A soft glow follows your pointer.</p>
          </div>
          <Switch checked={p.spotlight} label="Card spotlight" onChange={(v) => setPrefs({ spotlight: v })} />
        </div>
      </div>
      <div className="opt desk-only-block">
        <div className="opt-row">
          <div>
            <h3>Compact sidebar</h3>
            <p>Show icons only.</p>
          </div>
          <Switch checked={p.collapsed} label="Compact sidebar" onChange={(v) => setPrefs({ collapsed: v })} />
        </div>
      </div>
      <div className="opt">
        <button type="button" className="btn btn-secondary btn-sm" onClick={resetPrefs}>
          Reset to defaults
        </button>
      </div>
    </Sheet>
  );
}

function MoreSheet({ onClose, onPrefs }: { onClose: () => void; onPrefs: () => void }) {
  const sections = useSections();
  const tabHrefs = new Set(TAB_ITEMS.map((t) => t.href));
  const rest = sections.flatMap((s) => s.items).filter((i) => !tabHrefs.has(i.href));
  const marketing = sections.flatMap((s) => s.items).find((i) => i.href === "/marketing")?.children ?? [];
  return (
    <Sheet title="More" onClose={onClose}>
      <div className="more-grid">
        {[...rest.map((i) => ({ label: i.label, href: i.href, icon: i.icon })), ...marketing.map((c) => ({ label: c.label, href: c.href, icon: "mega" as const }))].map(
          (i) => (
            <Link key={i.href} href={i.href} className="more-card" onClick={onClose}>
              <Icon name={i.icon} />
              {i.label}
            </Link>
          ),
        )}
        <button type="button" className="more-card" onClick={onPrefs}>
          <Icon name="sliders" />
          Preferences
        </button>
      </div>
    </Sheet>
  );
}

function Tabbar({ onMore }: { onMore: () => void }) {
  const pathname = usePathname();
  const inTab = TAB_ITEMS.some((t) => isActive(pathname, t.href));
  return (
    <nav className="tabbar" aria-label="Primary">
      {TAB_ITEMS.map((t) => {
        const active = isActive(pathname, t.href);
        return (
          <Link key={t.href} href={t.href} className={`tb-item${active ? " active" : ""}`} aria-current={active ? "page" : undefined}>
            <Icon name={t.icon} />
            <span>{t.label}</span>
          </Link>
        );
      })}
      <button type="button" className={`tb-item${inTab ? "" : " active"}`} onClick={onMore}>
        <Icon name="more" />
        <span>More</span>
      </button>
    </nav>
  );
}

export default function ShellOverlays() {
  const pathname = usePathname();
  const [open, setOpen] = useState<Overlay | null>(null);
  useEffect(() => {
    const onOpen = (e: Event) => setOpen((e as CustomEvent<Overlay>).detail);
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => (o === "palette" ? null : "palette"));
      } else if (e.key === "Escape") {
        setOpen(null);
      }
    };
    window.addEventListener(OPEN_OVERLAY_EVENT, onOpen);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener(OPEN_OVERLAY_EVENT, onOpen);
      window.removeEventListener("keydown", onKey);
    };
  }, []);
  useEffect(() => setOpen(null), [pathname]);
  const close = () => setOpen(null);
  return (
    <>
      <Tabbar onMore={() => setOpen("more")} />
      {open === "palette" && <Palette onClose={close} />}
      {open === "prefs" && <PrefsSheet onClose={close} />}
      {open === "more" && <MoreSheet onClose={close} onPrefs={() => setOpen("prefs")} />}
    </>
  );
}
