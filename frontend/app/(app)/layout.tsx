import type { ReactNode } from "react";

import ShellFrame from "@/components/shell/frame";
import ShellOverlays from "@/components/shell/overlays";
import Sidebar from "@/components/shell/sidebar";
import Topbar from "@/components/shell/topbar";

import Providers from "./providers";

// App shell in the PilotSonic dashboard design: a floating sidebar panel and a
// main column (glass top bar + scrolling content) filling the viewport, plus
// the command palette, Preferences and (below 900px) the bottom tab bar. The
// (app) group adds no URL segment; "/" (the website) and the auth pages sit
// outside it and get no shell. The TanStack Query provider (SPEC-FE-003) and
// the route guard (SPEC-FE-004) wrap it all.
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <Providers>
      <ShellFrame sidebar={<Sidebar />} topbar={<Topbar />}>
        {children}
      </ShellFrame>
      <ShellOverlays />
    </Providers>
  );
}
