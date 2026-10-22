import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "PilotSonic · AI Autopilot for Your Business",
  description: "Store, ads, content, support and shipping, run by AI agents that wait for your OK.",
  icons: { icon: "/brand/favicon.png" },
};

// Applies the saved display preferences (components/shell/prefs.ts, same key
// and rules) before first paint, so the theme and accent never flash.
const BOOT = `try{var p=JSON.parse(localStorage.getItem("pilotsonic.prefs")||"{}"),h=document.documentElement;
if(p.theme==="light"||p.theme==="dark")h.dataset.theme=p.theme;
if(p.density)h.dataset.density=p.density;if(p.motion)h.dataset.motion=p.motion;h.dataset.spot=p.spotlight===false?"off":"on";
if(typeof p.accent==="string"&&/^#[0-9a-f]{6}$/i.test(p.accent))["--accent","--chart-1","--sidebar-active"].forEach(function(v){h.style.setProperty(v,p.accent)});}catch(e){}`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet" />
        <script dangerouslySetInnerHTML={{ __html: BOOT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
