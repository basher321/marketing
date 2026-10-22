"use client";

import { useEffect, useRef, type ReactNode } from "react";

import { Icon } from "@/components/shell/icons";

// A right-hand sheet (the shell's `.sheet` design, SPEC-FE-072) for forms such as
// "New order" (SPEC-FE-073) and "Add product" (SPEC-FE-075). Esc and the backdrop close it.
export default function SideSheet({
  title,
  onClose,
  children,
  wide = false,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const t = setTimeout(() => closeRef.current?.focus(), 120);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      clearTimeout(t);
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);
  return (
    <div className="sheet open">
      <div className="sheet-bg" onClick={onClose} />
      <div className="sheet-panel" role="dialog" aria-modal="true" aria-label={title} style={wide ? { width: 560 } : undefined}>
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
