import type { ReactNode } from "react";

// A template (unlike a layout) remounts on every navigation, so each page gets
// the PilotSonic design's rise-in entrance (.page-in in globals.css).
export default function PageTemplate({ children }: { children: ReactNode }) {
  return <div className="page-in">{children}</div>;
}
