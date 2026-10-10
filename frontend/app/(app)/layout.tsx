import type { ReactNode } from "react";

import Sidebar from "@/components/shell/sidebar";
import Topbar from "@/components/shell/topbar";

import Providers from "./providers";

// App shell (SPEC-FE-002): the mockup's .app grid (240px sidebar + main column),
// .main (flex column) and .content (padded, scrollable) around every page in
// the (app) route group. The group adds no URL segment; app/page.tsx sits
// outside it and only redirects, so "/" and the 404 page get no shell.
// SPEC-FE-003: the TanStack Query provider wraps the shell; markup unchanged.
// SPEC-FE-063: below 1024px the sidebar is a drawer, so the page is full width.
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <Providers>
      <div className="grid min-h-screen grid-cols-1 lg:grid-cols-[240px_1fr]">
        <Sidebar />
        <main className="flex min-w-0 flex-col overflow-hidden">
          <Topbar />
          <div className="flex-1 overflow-y-auto p-4 lg:p-6">{children}</div>
        </main>
      </div>
    </Providers>
  );
}
