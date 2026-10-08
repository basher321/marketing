import type { Config } from "tailwindcss";

// Every color resolves to the mockup's CSS custom property (defined in
// app/globals.css), never a hardcoded hex, so dark mode keeps working through
// the variable overrides rather than duplicated Tailwind config (SPEC-FE-001).
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        panel: "var(--panel)",
        border: "var(--border)",
        text: "var(--text)",
        muted: "var(--muted)",
        accent: "var(--accent)",
        "accent-soft": "var(--accent-soft)",
        success: "var(--success)",
        warn: "var(--warn)",
        danger: "var(--danger)",
        "sidebar-bg": "var(--sidebar-bg)",
        "sidebar-text": "var(--sidebar-text)",
        "sidebar-hover": "var(--sidebar-hover)",
        "sidebar-active": "var(--sidebar-active)",
        "chart-1": "var(--chart-1)",
        "chart-2": "var(--chart-2)",
        "chart-3": "var(--chart-3)",
        "chart-4": "var(--chart-4)",
        "chart-5": "var(--chart-5)",
      },
    },
  },
  plugins: [],
};

export default config;
